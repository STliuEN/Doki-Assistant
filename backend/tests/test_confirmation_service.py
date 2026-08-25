from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest
from langchain_core.tools import tool

from app.agent.skill_registry import ToolDefinition
from app.agent.tool_guard import tool_definition_digest, tool_provider_config_digest
from app.services import confirmation_service
from app.services.confirmation_service import PendingActionBindingError


def _run(coroutine):
    return asyncio.run(coroutine)


@tool("fixture_tool")
async def _fixture_tool(value: str) -> str:
    """Fixture tool."""
    return value


def _definition(**overrides) -> ToolDefinition:
    values = {
        "id": "fixture",
        "label": "Fixture",
        "description": "Fixture tool",
        "category": "test",
        "order": 1,
        "tool": _fixture_tool,
        "entrypoint": "tests.test_confirmation_service:_fixture_tool",
        "risk_level": "high",
        "requires_confirmation": True,
    }
    values.update(overrides)
    return ToolDefinition(**values)


class _FakeDb:
    def __init__(self, binding):
        self.binding = binding

    async def get(self, _model, run_id):
        return self.binding if run_id == self.binding.run_id else None


def _binding(**overrides):
    values = {
        "run_id": "run-1",
        "user_id": "user-1",
        "session_id": "session-1",
        "registry_revision": 7,
        "skill_bindings": [],
        "effective_grants": {"tools": ["fixture"], "skills": {}},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _action(definition: ToolDefinition, **overrides):
    values = {
        "id": "action-1",
        "user_id": "user-1",
        "session_id": "session-1",
        "run_id": "run-1",
        "registry_revision": 7,
        "tool_id": "fixture",
        "tool_digest": tool_definition_digest(definition),
        "source": "local",
        "provider_config_digest": None,
    }
    values.update(overrides)
    return values


def test_resolve_confirmed_tool_requires_matching_run_grant_and_definition(monkeypatch):
    definition = _definition()
    monkeypatch.setattr(confirmation_service, "tool_registry", SimpleNamespace(get=lambda _tool_id: definition))
    monkeypatch.setattr(
        confirmation_service,
        "skill_service",
        SimpleNamespace(reconcile_registry=lambda _db: _async_value(_snapshot())),
    )

    resolved = _run(
        confirmation_service.resolve_confirmed_tool(
            _FakeDb(_binding()),
            _action(definition),
            "user-1",
            requested_session_id="session-1",
        )
    )

    assert resolved is definition


@pytest.mark.parametrize(
    ("binding", "action_overrides"),
    [
        (_binding(effective_grants={"tools": []}), {}),
        (_binding(user_id="other-user"), {}),
        (_binding(registry_revision=8), {}),
        (_binding(session_id="other-session"), {}),
        (_binding(), {"run_id": None}),
    ],
)
def test_resolve_confirmed_tool_rejects_binding_or_grant_drift(monkeypatch, binding, action_overrides):
    definition = _definition()
    monkeypatch.setattr(confirmation_service, "tool_registry", SimpleNamespace(get=lambda _tool_id: definition))
    monkeypatch.setattr(
        confirmation_service,
        "skill_service",
        SimpleNamespace(reconcile_registry=lambda _db: _async_value(_snapshot())),
    )

    with pytest.raises(PendingActionBindingError):
        _run(
            confirmation_service.resolve_confirmed_tool(
                _FakeDb(binding),
                _action(definition, **action_overrides),
                "user-1",
                requested_session_id="session-1",
            )
        )


@pytest.mark.parametrize(
    "changed_definition",
    [
        replace(_definition(), enabled=False),
        replace(_definition(), available=False),
        replace(_definition(), requires_confirmation=False),
        replace(_definition(), visibility="private"),
    ],
)
def test_resolve_confirmed_tool_rejects_current_policy_or_definition_drift(monkeypatch, changed_definition):
    original = _definition()
    monkeypatch.setattr(
        confirmation_service,
        "tool_registry",
        SimpleNamespace(get=lambda _tool_id: changed_definition),
    )
    monkeypatch.setattr(
        confirmation_service,
        "skill_service",
        SimpleNamespace(reconcile_registry=lambda _db: _async_value(_snapshot())),
    )

    with pytest.raises(PendingActionBindingError):
        _run(
            confirmation_service.resolve_confirmed_tool(
                _FakeDb(_binding()),
                _action(original),
                "user-1",
            )
        )


def test_resolve_confirmed_private_tool_requires_current_admin_authorization(monkeypatch):
    definition = _definition(visibility="private")
    monkeypatch.setattr(confirmation_service, "tool_registry", SimpleNamespace(get=lambda _tool_id: definition))
    monkeypatch.setattr(
        confirmation_service,
        "skill_service",
        SimpleNamespace(reconcile_registry=lambda _db: _async_value(_snapshot())),
    )

    with pytest.raises(PendingActionBindingError):
        _run(
            confirmation_service.resolve_confirmed_tool(
                _FakeDb(_binding()),
                _action(definition),
                "user-1",
                allow_private=False,
            )
        )

    assert _run(
        confirmation_service.resolve_confirmed_tool(
            _FakeDb(_binding()),
            _action(definition),
            "user-1",
            allow_private=True,
        )
    ) is definition


def test_resolve_confirmed_public_tool_rejects_revoked_private_skill_authorization(monkeypatch):
    definition = _definition()
    private_skill = SimpleNamespace(
        enabled=True,
        visibility="private",
        version_id="version-private",
        digest="d" * 64,
        installation_revision=1,
        effective_grants={"tools": ["fixture"]},
    )
    binding = _binding(
        skill_bindings=[
            {
                "skill_id": "stable-private",
                "version_id": "version-private",
                "digest": "d" * 64,
                "installation_revision": 1,
            }
        ],
        effective_grants={
            "tools": ["fixture"],
            "tool_grant_sources": {"fixture": ["stable-private"]},
            "skills": {"stable-private": {"tools": ["fixture"]}},
        },
    )
    monkeypatch.setattr(confirmation_service, "tool_registry", SimpleNamespace(get=lambda _tool_id: definition))
    monkeypatch.setattr(
        confirmation_service,
        "skill_service",
        SimpleNamespace(
            reconcile_registry=lambda _db: _async_value(
                SimpleNamespace(revision=7, get=lambda identifier: private_skill if identifier == "stable-private" else None)
            )
        ),
    )

    with pytest.raises(PendingActionBindingError, match="private Skill"):
        _run(
            confirmation_service.resolve_confirmed_tool(
                _FakeDb(binding),
                _action(definition),
                "user-1",
                allow_private=False,
            )
        )


def test_resolve_confirmed_tool_rejects_registry_revision_advance(monkeypatch):
    definition = _definition()
    monkeypatch.setattr(confirmation_service, "tool_registry", SimpleNamespace(get=lambda _tool_id: definition))
    monkeypatch.setattr(
        confirmation_service,
        "skill_service",
        SimpleNamespace(reconcile_registry=lambda _db: _async_value(_snapshot(revision=8))),
    )

    with pytest.raises(PendingActionBindingError):
        _run(
            confirmation_service.resolve_confirmed_tool(
                _FakeDb(_binding()),
                _action(definition),
                "user-1",
            )
        )


def test_resolve_confirmed_mcp_tool_rejects_provider_endpoint_drift(monkeypatch):
    from app.agent.mcp import provider as provider_module

    server = SimpleNamespace(
        id="provider-1",
        enabled=True,
        transport="http",
        command=None,
        args=(),
        env={"TOKEN": "secret-value"},
        url="https://old.example.test/mcp",
        allow_tools=("write",),
        deny_tools=(),
        default_risk_level="high",
        default_requires_confirmation=True,
        timeout_seconds=30,
        max_output_chars=10_000,
        tool_overrides={},
    )
    fake_provider = SimpleNamespace(servers=lambda: [server])
    monkeypatch.setattr(provider_module, "mcp_provider", fake_provider)
    definition = _definition(source="mcp", provider_id="provider-1", external_name="write")
    action = _action(
        definition,
        source="mcp",
        provider_config_digest=tool_provider_config_digest(definition),
    )

    server.url = "https://new.example.test/mcp"
    monkeypatch.setattr(confirmation_service, "tool_registry", SimpleNamespace(get=lambda _tool_id: definition))
    monkeypatch.setattr(
        confirmation_service,
        "skill_service",
        SimpleNamespace(reconcile_registry=lambda _db: _async_value(_snapshot())),
    )
    monkeypatch.setattr(
        confirmation_service,
        "mcp_tool_registry",
        SimpleNamespace(ensure_fresh=lambda: _async_value(False)),
    )

    with pytest.raises(PendingActionBindingError):
        _run(
            confirmation_service.resolve_confirmed_tool(
                _FakeDb(_binding()),
                action,
                "user-1",
            )
        )


def _snapshot(*, revision: int = 7):
    return SimpleNamespace(revision=revision, get=lambda _identifier: None)


async def _async_value(value):
    return value
