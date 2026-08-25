"""agent_run_service.prepare_agent_run 单测：模型解析(404)、prompt 校验(400)、
tool_ids 显式跳过路由、MCP 自愈 reload、notices 透传。

route_skills / resolve_skills / mcp_tool_registry / model_config_service 全部 monkeypatch 隔离，
不触真实模型与注册表。
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.agent.skill_registry import SkillResolution
from app.services import agent_run_service
from app.skills.service import SKILL_REGISTRY_STALE_MESSAGE, SkillRegistryStaleError


def _run(coro):
    return asyncio.run(coro)


class _FakeTool:
    def __init__(self, name):
        self.name = name


def _runtime_skill(identifier: str, *, visibility: str = "public", enabled: bool = True):
    return SimpleNamespace(
        id=identifier,
        stable_id=f"stable-{identifier}",
        canonical_name=identifier.replace("_", "-"),
        version_id=f"version-{identifier}",
        version_number=1,
        digest=f"digest-{identifier}",
        installation_revision=1,
        is_default=identifier == "s_default",
        enabled=enabled,
        visibility=visibility,
        effective_grants={"tools": ["rag"]},
    )


def _patch_common(monkeypatch, *, routed_calls, resolution, mcp_refreshed=False, reload_calls=None):
    """装配公共桩：记录 route_skills 是否被调用、resolve_skills 返回值、mcp 自愈与 reload。"""

    async def fake_route_skills(query, candidates):
        routed_calls.append((query, candidates))
        return candidates

    def fake_resolve_skills(skill_ids, tool_ids, **_kwargs):
        return resolution

    class _FakeMcp:
        async def ensure_fresh(self):
            return mcp_refreshed

    class _FakeRegistry:
        def default_skill_ids(self):
            return ["s_default"]

        def reload(self):
            if reload_calls is not None:
                reload_calls.append(True)

    monkeypatch.setattr(agent_run_service, "route_skills", fake_route_skills)
    monkeypatch.setattr(agent_run_service, "resolve_skills", fake_resolve_skills)
    monkeypatch.setattr(agent_run_service, "mcp_tool_registry", _FakeMcp())
    monkeypatch.setattr(agent_run_service, "skill_registry", _FakeRegistry())

    class _FakeSkillService:
        default_skill = _runtime_skill("s_default")
        registry = SimpleNamespace(
            snapshot=SimpleNamespace(
                revision=7,
                all=lambda: (_FakeSkillService.default_skill,),
                get=lambda identifier: _runtime_skill(identifier),
            )
        )

        async def refresh_registry(self, db):
            return None

    monkeypatch.setattr(agent_run_service, "skill_service", _FakeSkillService())

    # model_config_service：无 model_config_id 时不应被调用
    class _FakeSvc:
        async def get_config(self, db, user_id, cid):
            return None  # 模拟「找不到」

    monkeypatch.setattr(agent_run_service, "get_model_config_service", lambda: _FakeSvc())


def _resolution(tools=("rag",), notices=()):
    return SkillResolution(
        skill_ids=["s1"],
        tool_ids=list(tools),
        tools=[_FakeTool(t) for t in tools],
        skill_prompts=["prompt-s1"],
        notices=list(notices),
    )


def test_prepare_run_invalid_prompt_type_400(monkeypatch):
    routed: list = []
    _patch_common(monkeypatch, routed_calls=routed, resolution=_resolution())
    with pytest.raises(HTTPException) as ei:
        _run(agent_run_service.prepare_agent_run(
            db=None, user_id="u1", query="hi",
            model_config_id=None, prompt_type="not_a_mode",
            skill_ids=None, tool_ids=None,
        ))
    assert ei.value.status_code == 400


def test_prepare_run_model_config_not_found_404(monkeypatch):
    routed: list = []
    _patch_common(monkeypatch, routed_calls=routed, resolution=_resolution())
    with pytest.raises(HTTPException) as ei:
        _run(agent_run_service.prepare_agent_run(
            db=None, user_id="u1", query="hi",
            model_config_id="missing", prompt_type=None,
            skill_ids=None, tool_ids=None,
        ))
    assert ei.value.status_code == 404


def test_prepare_run_registry_stale_503(monkeypatch):
    routed: list = []
    _patch_common(monkeypatch, routed_calls=routed, resolution=_resolution())

    class _StaleSkillService:
        async def reconcile_registry(self, db):
            raise SkillRegistryStaleError("revision mismatch")

    monkeypatch.setattr(agent_run_service, "skill_service", _StaleSkillService())
    with pytest.raises(HTTPException) as exc_info:
        _run(agent_run_service.prepare_agent_run(
            db=object(),
            user_id="u1",
            query="hi",
            model_config_id=None,
            prompt_type=None,
            skill_ids=None,
            tool_ids=None,
        ))

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == SKILL_REGISTRY_STALE_MESSAGE


def test_prepare_run_explicit_tool_ids_skip_routing(monkeypatch):
    routed: list = []
    _patch_common(monkeypatch, routed_calls=routed, resolution=_resolution())
    plan = _run(agent_run_service.prepare_agent_run(
        db=None, user_id="u1", query="hi",
        model_config_id=None, prompt_type=None,
        skill_ids=["s1"], tool_ids=["rag"],
    ))
    assert routed == []  # 显式 tool_ids → route_skills 未被调用
    assert [t.name for t in plan.tools] == ["rag"]
    assert plan.skill_ids == ["s1"]
    assert plan.tool_ids == ["rag"]


def test_prepare_run_rejects_private_skill_before_routing_provider(monkeypatch):
    routed: list = []
    _patch_common(monkeypatch, routed_calls=routed, resolution=_resolution())
    private_skill = _runtime_skill("s1", visibility="private")
    snapshot = SimpleNamespace(
        revision=7,
        all=lambda: (private_skill,),
        get=lambda identifier: private_skill if identifier == "s1" else None,
    )
    agent_run_service.skill_service.registry.snapshot = snapshot

    with pytest.raises(HTTPException) as exc_info:
        _run(agent_run_service.prepare_agent_run(
            db=None,
            user_id="u1",
            query="must not reach a provider",
            model_config_id=None,
            prompt_type=None,
            skill_ids=["s1"],
            tool_ids=None,
        ))

    assert exc_info.value.status_code == 400
    assert routed == []


def test_prepare_run_offline_does_not_query_registry_database(monkeypatch):
    routed: list = []
    _patch_common(monkeypatch, routed_calls=routed, resolution=_resolution())

    class _FailingSkillService:
        registry = agent_run_service.skill_service.registry

        async def refresh_registry(self, db):
            raise AssertionError("offline run must use the already published snapshot")

    monkeypatch.setattr(agent_run_service, "skill_service", _FailingSkillService())
    plan = _run(agent_run_service.prepare_agent_run(
        db=None,
        user_id="u1",
        query="offline",
        model_config_id=None,
        prompt_type=None,
        skill_ids=["s1"],
        tool_ids=["rag"],
    ))
    assert plan.skill_ids == ["s1"]


def test_prepare_run_routes_when_no_tool_ids(monkeypatch):
    routed: list = []
    _patch_common(monkeypatch, routed_calls=routed, resolution=_resolution())
    _run(agent_run_service.prepare_agent_run(
        db=None, user_id="u1", query="问题",
        model_config_id=None, prompt_type=None,
        skill_ids=None, tool_ids=None,
    ))
    assert len(routed) == 1  # 无 tool_ids → 走预路由
    assert routed[0][0] == "问题"
    assert routed[0][1] == ["s_default"]  # 用 default_skill_ids 作候选


def test_prepare_run_mcp_refresh_triggers_reload(monkeypatch):
    routed: list = []
    reloads: list = []
    _patch_common(monkeypatch, routed_calls=routed, resolution=_resolution(),
                  mcp_refreshed=True, reload_calls=reloads)
    _run(agent_run_service.prepare_agent_run(
        db=None, user_id="u1", query="hi",
        model_config_id=None, prompt_type=None,
        skill_ids=["s1"], tool_ids=["rag"],
    ))
    assert reloads == [True]  # ensure_fresh 返回 True → reload 被调用


def test_prepare_run_notices_into_prompt(monkeypatch):
    routed: list = []
    _patch_common(monkeypatch, routed_calls=routed,
                  resolution=_resolution(notices=["MCP 工具 X 暂不可用"]))
    plan = _run(agent_run_service.prepare_agent_run(
        db=None, user_id="u1", query="hi",
        model_config_id=None, prompt_type=None,
        skill_ids=["s1"], tool_ids=["rag"],
    ))
    assert plan.notices == ["MCP 工具 X 暂不可用"]
    assert "MCP 工具 X 暂不可用" in plan.system_prompt  # notice 注入 system prompt


def test_prepare_run_rejects_cumulative_skill_instruction_overflow(monkeypatch):
    routed: list = []
    resolution = replace(
        _resolution(),
        skill_prompts=["x" * (agent_run_service.MAX_SKILL_INSTRUCTION_CHARS_PER_RUN + 1)],
    )
    _patch_common(monkeypatch, routed_calls=routed, resolution=resolution)

    with pytest.raises(HTTPException) as exc_info:
        _run(agent_run_service.prepare_agent_run(
            db=None,
            user_id="u1",
            query="hi",
            model_config_id=None,
            prompt_type=None,
            skill_ids=["s1"],
            tool_ids=["rag"],
        ))

    assert exc_info.value.status_code == 400
    assert "run budget" in exc_info.value.detail


def test_prepare_run_instruction_budget_counts_utf8_bytes(monkeypatch):
    routed: list = []
    resolution = replace(
        _resolution(),
        skill_prompts=[
            "技" * ((agent_run_service.MAX_SKILL_INSTRUCTION_BYTES_PER_RUN // 3) + 1)
        ],
    )
    _patch_common(monkeypatch, routed_calls=routed, resolution=resolution)

    with pytest.raises(HTTPException) as exc_info:
        _run(agent_run_service.prepare_agent_run(
            db=None,
            user_id="u1",
            query="hi",
            model_config_id=None,
            prompt_type=None,
            skill_ids=["s1"],
            tool_ids=["rag"],
        ))

    assert exc_info.value.status_code == 400
    assert "byte run budget" in exc_info.value.detail


def test_prepare_run_records_tool_grant_sources(monkeypatch):
    routed: list = []
    resolution = replace(
        _resolution(),
        tool_grant_sources={"rag": ["stable-s1", "stable-s2"]},
    )
    _patch_common(monkeypatch, routed_calls=routed, resolution=resolution)

    plan = _run(agent_run_service.prepare_agent_run(
        db=None,
        user_id="u1",
        query="hi",
        model_config_id=None,
        prompt_type=None,
        skill_ids=["s1"],
        tool_ids=["rag"],
    ))

    assert plan.effective_grants["tool_grant_sources"] == {
        "rag": ["stable-s1", "stable-s2"]
    }


def test_prepare_run_rejects_too_many_selected_skills(monkeypatch):
    routed: list = []
    resolution = replace(
        _resolution(),
        skill_ids=[
            f"skill-{index}"
            for index in range(agent_run_service.MAX_SELECTED_SKILLS_PER_RUN + 1)
        ],
    )
    _patch_common(monkeypatch, routed_calls=routed, resolution=resolution)

    with pytest.raises(HTTPException) as exc_info:
        _run(agent_run_service.prepare_agent_run(
            db=None,
            user_id="u1",
            query="hi",
            model_config_id=None,
            prompt_type=None,
            skill_ids=resolution.skill_ids,
            tool_ids=["rag"],
        ))

    assert exc_info.value.status_code == 400
    assert "at most" in exc_info.value.detail
