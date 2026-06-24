"""intent_router 混合路由单测：语义 + 核心关键词 + 模糊带 LLM + 阶梯回退。

嵌入模型用 FakeEmbed 注入确定向量（各 skill 取正交基向量），
query 向量由测试显式构造，从而对相似度/gap/floor 做确定性断言。
LLM 经路同样 monkeypatch 隔离，不触发真实模型。
"""

from __future__ import annotations

import asyncio

import pytest

from app.agent import intent_router
from app.agent import routing_calibration
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

    def __init__(
        self,
        query_target: str | None = None,
        blend: dict[str, float] | None = None,
        model_name: str = "fake-embed",
    ):
        self.query_target = query_target
        self.blend = blend
        self.model = model_name

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


class ScaledFakeEmbed(FakeEmbed):
    def __init__(
        self,
        query_target: str,
        scale: float,
        model_name: str = "scaled-fake-embed",
    ):
        super().__init__(query_target=query_target, model_name=model_name)
        self.scale = scale

    def embed_documents(self, texts):
        vectors = []
        for text in texts:
            if isinstance(text, str) and text.startswith("cal:"):
                vectors.append(self._low_score_query_vec(text.removeprefix("cal:")))
            else:
                vectors.append(_onehot(text))
        return vectors

    def embed_query(self, text):
        return self._low_score_query_vec(self.query_target)

    def _low_score_query_vec(self, sid: str) -> list[float]:
        vec = [0.0] * (_DIM + 1)
        vec[_BASIS[sid]] = self.scale
        vec[-1] = (1 - self.scale**2) ** 0.5
        return vec


class NoiseAttractorFakeEmbed(FakeEmbed):
    """Simulate a 4b-style chatter attractor: noise strongly raw-top1s knowledge."""

    def __init__(self):
        super().__init__(model_name="noise-attractor-embed")

    def embed_documents(self, texts):
        vectors = []
        for text in texts:
            if text == "noise":
                vectors.append(self._noise_vec())
            else:
                vectors.append(_onehot(text))
        return vectors

    def embed_query(self, text):
        if "闲聊" in text:
            return self._noise_vec()
        return [0.0] * _DIM

    def _noise_vec(self) -> list[float]:
        vec = [0.0] * (_DIM + 1)
        vec[_BASIS["knowledge_research"]] = 0.56
        vec[_BASIS["note_research"]] = 0.49
        vec[-1] = (1 - 0.56**2 - 0.49**2) ** 0.5
        return vec


class ScatteredNoiseFakeEmbed(FakeEmbed):
    """模拟 0.6b：闲聊四散，public 只偶发 top-1（占比 < 主导门槛），不该被锚定。

    复现并锁住「噪声锚定误杀 public 真实 query」的回归：
    - public 正例打分 0.60 → floor=0.60-0.27=0.33
    - public 真实 query 打分 0.37（> floor 0.33，但 < public 噪声天花板 0.44）
    - 噪声池 4 条只有 1 条 top-1 落 public（25% < 50% 门槛）→ 不锚定 → 真实 query 仍直选
    """

    # 噪声样本 → (落点 skill, 该噪声在落点上的相似度)
    _NOISE_MAP = {
        "n_public": ("public_info_lookup", 0.44),
        "n_know": ("knowledge_research", 0.50),
        "n_note": ("note_research", 0.48),
        "n_mem": ("memory_read", 0.46),
    }

    def __init__(self):
        super().__init__(model_name="scattered-noise-embed")

    def _scaled(self, sid: str, scale: float) -> list[float]:
        vec = [0.0] * (_DIM + 1)
        vec[_BASIS[sid]] = scale
        vec[-1] = (1 - scale**2) ** 0.5
        return vec

    def embed_documents(self, texts):
        vectors = []
        for text in texts:
            if text.startswith("pos:"):
                vectors.append(self._scaled(text.removeprefix("pos:"), 0.60))
            elif text in self._NOISE_MAP:
                sid, scale = self._NOISE_MAP[text]
                vectors.append(self._scaled(sid, scale))
            else:
                vectors.append(_onehot(text))
        return vectors

    def embed_query(self, text):
        # 真实 public query：分数低于 public 噪声天花板，但高于其 floor。
        return self._scaled("public_info_lookup", 0.37)


@pytest.fixture(autouse=True)
def _reset_index(monkeypatch, tmp_path):
    # 每个用例前清空模块级语义索引，并让 _embed_text 返回纯 skill_id
    intent_router._skill_vectors.clear()
    intent_router._index_signature = None
    intent_router._index_vector_dim = None
    routing_calibration.clear_calibration_cache()
    monkeypatch.setattr(routing_calibration, "_calibration_dir", lambda: str(tmp_path))
    monkeypatch.setattr(intent_router, "_embed_text", lambda sid: sid)
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


def test_embedding_switch_rebuilds_semantic_index(monkeypatch):
    first = FakeEmbed(query_target="knowledge_research", model_name="fake-a")
    second = FakeEmbed(query_target="note_writer", model_name="fake-b")

    async def _boom(*a, **k):
        raise AssertionError("clear semantic hit must not call LLM")

    monkeypatch.setattr(intent_router, "_llm_route", _boom)
    init_manager.embed_model = first
    first_result = _run(route_skills("处理一下我那些东西", ALL))
    first_signature = intent_router._index_signature

    init_manager.embed_model = second
    second_result = _run(route_skills("处理一下我那些东西", ALL))

    assert "knowledge_research" in first_result
    assert "note_writer" in second_result
    assert intent_router._index_signature != first_signature


def test_dynamic_calibration_allows_model_specific_low_scores(monkeypatch):
    init_manager.embed_model = ScaledFakeEmbed(
        query_target="knowledge_research",
        scale=0.30,
        model_name="low-score-embed",
    )
    monkeypatch.setattr(
        routing_calibration,
        "_positive_examples",
        lambda skill: [f"cal:{skill.id}"],
    )

    async def _boom(*a, **k):
        raise AssertionError("calibrated semantic hit must not call LLM")

    monkeypatch.setattr(intent_router, "_llm_route", _boom)
    result = _run(route_skills("这份资料讲了啥", ALL))

    assert "knowledge_research" in result
    # 默认 floor=0.35 本会拒掉 0.30 的真实命中；能直选必然来自自适应校准。
    # 直接断言校准产物：knowledge_research 的 per-skill floor 已被压到 0.30 之下。
    routable = [
        sid
        for sid in ALL
        if (skill := intent_router.skill_registry.get(sid))
        and skill.routable
        and not skill.always_on
    ]
    signature = routing_calibration.calibration_signature(
        routable, init_manager.embed_model, intent_router._index_vector_dim
    )
    calibration = routing_calibration._calibration_cache[signature]
    calibrated_floor = calibration.floor_for("knowledge_research")
    assert calibrated_floor < 0.30
    assert calibrated_floor < intent_router.SIM_FLOOR


def test_noise_attractor_does_not_direct_hit_or_promote_runner_up(monkeypatch):
    init_manager.embed_model = NoiseAttractorFakeEmbed()
    monkeypatch.setattr(
        routing_calibration,
        "_positive_examples",
        lambda skill: [skill.id],
    )
    monkeypatch.setattr(
        routing_calibration,
        "_noise_pool",
        lambda skills: ["noise"],
    )
    captured = {}

    async def _fake_llm(query, candidates, hints):
        captured["hints"] = hints
        return []

    monkeypatch.setattr(intent_router, "_llm_route", _fake_llm)
    result = _run(route_skills("闲聊一下", ALL))

    assert "knowledge_research" not in result
    assert "note_research" not in result
    assert captured["hints"] == []
    assert result == ["system_context"]


def test_generic_lookup_phrase_does_not_force_memory_read(monkeypatch):
    init_manager.embed_model = FakeEmbed(query_target="public_info_lookup")

    async def _boom(*a, **k):
        raise AssertionError("clear public lookup hit must not call LLM")

    monkeypatch.setattr(intent_router, "_llm_route", _boom)
    result = _run(route_skills("查一下武汉大学哪年建校", ALL))

    assert "public_info_lookup" in result
    assert "memory_read" not in result


def test_scattered_noise_does_not_anchor_floor(monkeypatch):
    # 回归锁：闲聊四散（public 仅 25% 噪声 top-1，未达 NOISE_DOMINANCE）时
    # 不得锚定 public 的 floor，真实 public query 仍应语义直选——不被噪声天花板误杀。
    init_manager.embed_model = ScatteredNoiseFakeEmbed()
    monkeypatch.setattr(
        routing_calibration,
        "_positive_examples",
        lambda skill: [f"pos:{skill.id}"],
    )
    monkeypatch.setattr(
        routing_calibration,
        "_noise_pool",
        lambda skills: ["n_public", "n_know", "n_note", "n_mem"],
    )

    async def _boom(*a, **k):
        raise AssertionError("recall-preserved hit must not call LLM")

    monkeypatch.setattr(intent_router, "_llm_route", _boom)
    result = _run(route_skills("这个问题的答案是什么", ALL))

    routable = [
        sid
        for sid in ALL
        if (skill := intent_router.skill_registry.get(sid))
        and skill.routable
        and not skill.always_on
    ]
    signature = routing_calibration.calibration_signature(
        routable, init_manager.embed_model, intent_router._index_vector_dim
    )
    calibration = routing_calibration._calibration_cache[signature]
    # public 噪声占比 25% < 50% → 不锚定：floor 应停在正例基线（~0.33），远低于噪声天花板 0.44。
    assert calibration.floor_for("public_info_lookup") < 0.40
    assert "public_info_lookup" not in calibration.noise_ceiling
    assert "public_info_lookup" in result

