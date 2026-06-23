"""intent_router 路由逻辑单测。

覆盖：规则叠加打分、过宽动词不误独占、强/弱信号分流、
always-on 常驻、top-N 截断、LLM 仲裁与各级安全回退。
LLM 经路通过 monkeypatch 隔离，不触发真实模型调用。
"""

from __future__ import annotations

import asyncio

import pytest

from app.agent import intent_router
from app.agent.intent_router import route_skills


def _run(coro):
    return asyncio.run(coro)


# 全部候选 skill，作为"已选集合"上界
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


def test_single_candidate_passthrough():
    assert _run(route_skills("随便问问", ["memory_read"])) == ["memory_read"]


def test_empty_query_passthrough():
    assert _run(route_skills("   ", ALL)) == ALL


def test_strong_signal_selected_without_llm(monkeypatch):
    # 强信号命中应直接入选，且不应触碰 LLM
    def _boom(*_args, **_kwargs):
        raise AssertionError("strong signal must not call LLM")

    monkeypatch.setattr(intent_router, "_llm_route", _boom)
    result = _run(route_skills("帮我删除昨天那条事项", ALL))
    assert "memory_cleanup" in result
    # always-on 常驻
    assert "system_context" in result


def test_multi_signal_stacks(monkeypatch):
    monkeypatch.setattr(intent_router, "_llm_route", lambda *a, **k: _fail())
    # "根据知识库" → knowledge_research(2.0)；"记成笔记" → note_writer(2.0)
    result = _run(route_skills("根据知识库把要点记成笔记", ALL))
    assert "knowledge_research" in result
    assert "note_writer" in result


def test_broad_verb_is_weak_goes_to_llm(monkeypatch):
    # "更新" 只是弱信号(memory_write=1.0)，不应独占，应进入 LLM 仲裁
    captured = {}

    async def _fake_llm(query, candidates, hints):
        captured["hints"] = hints
        return ["note_writer"]

    monkeypatch.setattr(intent_router, "_llm_route", _fake_llm)
    result = _run(route_skills("更新一下我的内容", ALL))
    # LLM 仲裁结果生效
    assert "note_writer" in result
    # memory_write 作为弱命中先验传给了 LLM
    assert "memory_write" in captured["hints"]


def test_llm_failure_falls_back_to_weak_hits(monkeypatch):
    async def _raise(*_a, **_k):
        raise RuntimeError("llm down")

    monkeypatch.setattr(intent_router, "_llm_route", _raise)
    # "更新" 弱命中 memory_write；LLM 挂掉后退到弱命中而非全集
    result = _run(route_skills("更新一下", ALL))
    assert "memory_write" in result
    assert len(result) < len(ALL)


def test_no_signal_falls_back_to_full(monkeypatch):
    async def _empty(*_a, **_k):
        return []

    monkeypatch.setattr(intent_router, "_llm_route", _empty)
    # 完全无规则信号且 LLM 空 → 回退全集
    result = _run(route_skills("你好呀今天心情不错", ALL))
    assert result == ALL


def test_cap_limits_skill_count(monkeypatch):
    async def _greedy(query, candidates, hints):
        # LLM 贪心返回一大堆
        return [c for c in candidates if c != "system_context"]

    monkeypatch.setattr(intent_router, "_llm_route", _greedy)
    result = _run(route_skills("更新一下", ALL))
    non_always = [s for s in result if s not in intent_router.ALWAYS_ON]
    assert len(non_always) <= intent_router.MAX_SKILLS


def test_routing_never_introduces_unselected(monkeypatch):
    async def _hallucinate(*_a, **_k):
        return ["memory_cleanup", "review_planner"]

    monkeypatch.setattr(intent_router, "_llm_route", _hallucinate)
    # 候选集合只有两个，LLM 即便幻觉也不能引入集合外能力
    candidates = ["memory_read", "note_research"]
    result = _run(route_skills("更新一下", candidates))
    assert set(result).issubset(set(candidates))


def _fail():
    raise AssertionError("LLM should not be called for strong-signal path")
