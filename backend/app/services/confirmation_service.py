from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.mcp.registry import mcp_tool_registry
from app.agent.skill_registry import ToolDefinition, skill_registry, tool_registry
from app.agent.tool_guard import tool_definition_digest, tool_provider_config_digest
from app.models.skill_domain import SkillRunBinding
from app.skills.service import SkillRegistryStaleError, skill_service


class PendingActionBindingError(RuntimeError):
    """Raised when a deferred action no longer matches its immutable run grant."""


def _invalid(message: str) -> PendingActionBindingError:
    return PendingActionBindingError(message)


async def resolve_confirmed_tool(
    db: AsyncSession,
    action: dict[str, Any],
    user_id: str,
    *,
    requested_session_id: str | None = None,
    allow_private: bool = False,
) -> ToolDefinition:
    """Resolve a confirmed Tool only when its run binding and definition still match."""
    run_id = action.get("run_id")
    registry_revision = action.get("registry_revision")
    tool_id = action.get("tool_id")
    captured_digest = action.get("tool_digest")
    if (
        not isinstance(run_id, str)
        or not run_id
        or not isinstance(registry_revision, int)
        or not isinstance(tool_id, str)
        or not tool_id
        or not isinstance(captured_digest, str)
        or len(captured_digest) != 64
    ):
        raise _invalid("pending action is missing its run authorization snapshot")

    binding = await db.get(SkillRunBinding, run_id)
    if binding is None:
        raise _invalid("the originating run binding no longer exists")
    if binding.user_id != user_id or action.get("user_id") != user_id:
        raise _invalid("the pending action does not belong to this user")
    if action.get("session_id") != binding.session_id:
        raise _invalid("the pending action session does not match its run binding")
    if requested_session_id is not None and requested_session_id != binding.session_id:
        raise _invalid("the confirmation request targets a different session")
    if int(binding.registry_revision) != registry_revision:
        raise _invalid("the pending action registry revision does not match its run binding")

    grants = binding.effective_grants if isinstance(binding.effective_grants, dict) else {}
    granted_tools = grants.get("tools")
    if not isinstance(granted_tools, list) or tool_id not in granted_tools:
        raise _invalid("the Tool was not granted to the originating run")

    try:
        current_snapshot = await skill_service.reconcile_registry(db)
    except SkillRegistryStaleError as exc:
        raise _invalid("the current Skill registry cannot be reconciled") from exc
    if current_snapshot.revision != registry_revision:
        raise _invalid("the Skill registry changed after the action was created")

    captured_skill_bindings = binding.skill_bindings if isinstance(binding.skill_bindings, list) else []
    captured_skill_grants = grants.get("skills") if isinstance(grants.get("skills"), dict) else {}
    grant_sources = grants.get("tool_grant_sources")
    if captured_skill_bindings:
        source_ids = grant_sources.get(tool_id) if isinstance(grant_sources, dict) else None
        if not isinstance(source_ids, list) or not source_ids:
            raise _invalid("the Tool has no recorded Skill authorization source")
        captured_ids = {
            item.get("skill_id")
            for item in captured_skill_bindings
            if isinstance(item, dict) and isinstance(item.get("skill_id"), str)
        }
        if not captured_ids.intersection(source_ids):
            raise _invalid("the Tool authorization source is not part of the originating run")
    for captured in captured_skill_bindings:
        if not isinstance(captured, dict):
            raise _invalid("the run contains an invalid Skill binding")
        stable_id = captured.get("skill_id")
        if not isinstance(stable_id, str):
            raise _invalid("the run contains an invalid Skill identity")
        current_skill = current_snapshot.get(stable_id)
        if current_skill is None or not current_skill.enabled:
            raise _invalid("a Skill from the originating run is no longer enabled")
        if current_skill.visibility != "public" and not allow_private:
            raise _invalid("a private Skill from the originating run is no longer authorized")
        if (
            current_skill.version_id != captured.get("version_id")
            or current_skill.digest != captured.get("digest")
            or current_skill.installation_revision != captured.get("installation_revision")
            or dict(current_skill.effective_grants) != captured_skill_grants.get(stable_id)
        ):
            raise _invalid("a Skill version or grant changed after the action was created")

    if action.get("source") == "mcp" and await mcp_tool_registry.ensure_fresh():
        skill_registry.reload()
    try:
        tool_def = tool_registry.get(tool_id)
    except KeyError as exc:
        raise _invalid("the Tool is no longer registered") from exc

    if (
        not tool_def.enabled
        or not tool_def.available
        or not tool_def.requires_confirmation
        or (tool_def.visibility != "public" and not allow_private)
    ):
        raise _invalid("the Tool is no longer enabled, available, and confirmation-protected")
    if tool_definition_digest(tool_def) != captured_digest:
        raise _invalid("the Tool definition changed after the action was created")
    current_provider_digest = tool_provider_config_digest(tool_def)
    if action.get("source") == "mcp" and not current_provider_digest:
        raise _invalid("the MCP policy authority is unavailable")
    if action.get("provider_config_digest") != current_provider_digest:
        raise _invalid("the Tool provider configuration changed after the action was created")
    return tool_def
