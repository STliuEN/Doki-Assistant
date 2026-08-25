from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent.skill_registry import SkillRegistry
from app.skills.registry import RuntimeSkill, SkillRegistrySnapshot


def _skill(
    identifier: str,
    *,
    tools: tuple[str, ...] = ("allowed",),
    visibility: str = "public",
) -> RuntimeSkill:
    return RuntimeSkill(
        id=identifier,
        stable_id=f"stable-{identifier}",
        canonical_name=identifier,
        aliases=(),
        label=identifier,
        description=identifier,
        tool_ids=tools,
        instructions="",
        resources=(),
        storage_key=f"objects/{identifier}",
        version_id=f"version-{identifier}",
        version_number=1,
        digest=f"digest-{identifier}",
        installation_revision=1,
        enabled=True,
        visibility=visibility,
        effective_grants={"tools": list(tools)},
    )


def _registry() -> SkillRegistry:
    fake_tools = {
        tool_id: SimpleNamespace(
            id=tool_id,
            enabled=True,
            available=True,
            visibility="public",
            order=index,
            name=tool_id,
            tool=SimpleNamespace(name=tool_id),
        )
        for index, tool_id in enumerate(("allowed", "other"))
    }
    tools = SimpleNamespace(
        ids=lambda: set(fake_tools),
        all=lambda: list(fake_tools.values()),
        get=lambda tool_id: fake_tools[tool_id],
    )
    registry = SkillRegistry(tool_registry=tools)
    return registry


def test_direct_tool_ids_must_be_granted_by_selected_skill() -> None:
    registry = _registry()
    snapshot = SkillRegistrySnapshot(revision=4, skills=(_skill("one"),))

    with pytest.raises(ValueError, match="not granted"):
        registry.resolve(
            ["one"],
            ["other"],
            snapshot=snapshot,
        )


def test_resolution_records_all_stable_skill_grant_sources(monkeypatch) -> None:
    registry = _registry()
    snapshot = SkillRegistrySnapshot(
        revision=4,
        skills=(
            _skill("one", tools=("allowed",)),
            _skill("two", tools=("allowed",)),
        ),
    )
    monkeypatch.setattr(
        "app.agent.tool_guard.wrap_tool",
        lambda definition: definition.tool,
    )

    resolution = registry.resolve(["one", "two"], ["allowed"], snapshot=snapshot)

    assert resolution.tool_ids == ["allowed"]
    assert resolution.tool_grant_sources == {
        "allowed": ["stable-one", "stable-two"],
    }
