"""intent_router 混合路由单测：语义 + 核心关键词 + 模糊带 LLM + 阶梯回退。

嵌入模型用 FakeEmbed 注入确定向量（各 skill 取正交基向量），
query 向量由测试显式构造，从而对相似度/gap/floor 做确定性断言。
LLM 经路同样 monkeypatch 隔离，不触发真实模型。
"""

from __future__ import annotations

import asyncio

import pytest

from app.agent import intent_router
from app.agent.intent_router import route_skills
from app.core.background_init import init_manager


def _run(coro):
    return asyncio.run(coro)


# 候选 skill 全集（与真实 registry 的 id 对齐）
ALL = [
    "knowledge_research",
    "mcp_smoke_test",
    "memory_cleanup",
    "memory_read",
    "memory_write",
    "note_research",
    "note_writer",
    "public_info_lookup",
    "review_planner",
    "system_context",
]

# 给每个 skill 分配一个正交基方向；query 命中谁就贴近谁。
_BASIS = {sid: i for i, sid in enumerate(ALL)}
_DIM = len(ALL)


def _onehot(sid: str) -> list[float]:
    vec = [0.0] * _DIM
    vec[_BASIS[sid]] = 1.0
    return vec


class FakeEmbed:
    """按 skill_id 文本里出现的 id 关键字返回对应正交向量。"""

    def __init__(self, query_target: str | None = None, blend: dict[str, float] | None = None):
        self.query_target = query_target
        self.blend = blend

    def embed_documents(self, texts):
        # 测试里 _embed_text 返回 "label。description"，这里改用 monkeypatch 让
        # _embed_text 直接返回 skill_id，故 texts 即 skill_id 列表。
        return [_onehot(t) for t in texts]

    def embed_query(self, text):
        if self.blend is not None:
            vec = [0.0] * _DIM
            for sid, w in self.blend.items():
                vec[_BASIS[sid]] += w
            return vec
        if self.query_target:
            return _onehot(self.query_target)
        return [0.0] * _DIM


@pytest.fixture(autouse=True)
def _reset_index(monkeypatch):
    # 每个用例前清空模块级语义索引，并让 _embed_text 返回纯 skill_id
    intent_router._skill_vectors.clear()
    intent_router._index_signature = None
    monkeypatch.setattr(intent_router, "_embed_text", lambda sid: sid)
    # 让 _registry_signature 不依赖真实 registry 内容
    monkeypatch.setattr(intent_router, "_registry_signature", lambda ids: ",".join(sorted(ids)))
    yield
    init_manager.embed_model = None
    init_manager.chat_model = None


def test_single_candidate_passthrough():
    assert _run(route_skills("随便问问", ["memory_read"])) == ["memory_read"]


def test_empty_query_passthrough():
    assert _run(route_skills("   ", ALL)) == ALL


def test_keyword_strong_cleanup(monkeypatch):
    # 关键词强信号：'删了' → memory_cleanup，即使语义不可用也命中
    init_manager.embed_model = None

    async def _boom(*a, **k):
        raise AssertionError("strong keyword path must not call LLM")

    monkeypatch.setattr(intent_router, "_llm_route", _boom)
    result = _run(route_skills("把昨天那条事项删了", ALL))
    assert "memory_cleanup" in result
    # always_on 常驻
    assert "system_context" in result


def test_keyword_strong_write(monkeypatch):
    init_manager.embed_model = None
    result = _run(route_skills("帮我记一下明天开会", ALL))
    assert "memory_write" in result


def test_semantic_direct_hit(monkeypatch):
    # 语义直选：query 贴近 knowledge_research，gap 足够 → 直选；不应碰 LLM
    init_manager.embed_model = FakeEmbed(query_target="knowledge_research")

    async def _boom(*a, **k):
        raise AssertionError("clear semantic hit must not call LLM")

    monkeypatch.setattr(intent_router, "_llm_route", _boom)
    # 用不含关键词的 query，避免触发关键词强信号
    result = _run(route_skills("这份资料讲了啥", ALL))
    assert "knowledge_research" in result
    assert "system_context" in result


def test_ambiguous_band_triggers_llm(monkeypatch):
    # 两个 skill 相似度接近（gap < SIM_GAP）→ 进模糊带 → LLM 仲裁
    init_manager.embed_model = FakeEmbed(
        blend={"note_research": 0.6, "note_writer": 0.58}
    )
    captured = {}

    async def _fake_llm(query, candidates, hints):
        captured["hints"] = hints
        return ["note_writer"]

    monkeypatch.setattr(intent_router, "_llm_route", _fake_llm)
    result = _run(route_skills("处理一下我那些东西", ALL))
    assert "note_writer" in result
    # 模糊带两者都作为先验传给 LLM
    assert "note_research" in captured["hints"]
    assert "note_writer" in captured["hints"]


def test_embed_not_ready_falls_back_to_keyword(monkeypatch):
    init_manager.embed_model = None

    async def _empty(*a, **k):
        return []

    monkeypatch.setattr(intent_router, "_llm_route", _empty)
    # embed 未就绪 + 有关键词 → 走关键词
    result = _run(route_skills("查一下今天的待办", ALL))
    assert "memory_read" in result


def test_no_signal_falls_back_to_full(monkeypatch):
    # embed 就绪但所有相似度为 0（query 正交于所有 skill），且无关键词、LLM 空 → 全集
    init_manager.embed_model = FakeEmbed(blend={})

    async def _empty(*a, **k):
        return []

    monkeypatch.setattr(intent_router, "_llm_route", _empty)
    result = _run(route_skills("嗯嗯啊啊哦哦", ALL))
    assert result == ALL


def test_cap_limits_skill_count(monkeypatch):
    init_manager.embed_model = FakeEmbed(blend={})

    async def _greedy(query, candidates, hints):
        return [c for c in candidates if c != "system_context"]

    monkeypatch.setattr(intent_router, "_llm_route", _greedy)
    # 制造模糊带：让多个 skill 同分，触发 LLM，再被贪心返回一堆
    init_manager.embed_model = FakeEmbed(
        blend={"memory_read": 0.5, "memory_write": 0.49, "note_research": 0.48, "review_planner": 0.47}
    )
    result = _run(route_skills("处理一下我那些东西", ALL))
    non_always = [s for s in result if s != "system_context"]
    assert len(non_always) <= intent_router.MAX_SKILLS


def test_never_introduces_unselected(monkeypatch):
    init_manager.embed_model = FakeEmbed(
        blend={"memory_read": 0.5, "note_research": 0.49}
    )

    async def _hallucinate(*a, **k):
        return ["memory_cleanup", "review_planner"]

    monkeypatch.setattr(intent_router, "_llm_route", _hallucinate)
    candidates = ["memory_read", "note_research"]
    result = _run(route_skills("处理一下", candidates))
    assert set(result).issubset(set(candidates))

