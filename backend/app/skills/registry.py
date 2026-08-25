"""Immutable runtime catalog for active standard Skill package versions."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class RuntimeSkillResource:
    path: str
    kind: str
    size: int
    sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "kind": self.kind,
            "size": self.size,
            "sha256": self.sha256,
            "executable": self.kind == "script",
        }


@dataclass(frozen=True, slots=True)
class RuntimeSkill:
    id: str
    stable_id: str
    canonical_name: str
    aliases: tuple[str, ...]
    label: str
    description: str
    tool_ids: tuple[str, ...]
    instructions: str
    resources: tuple[RuntimeSkillResource, ...]
    storage_key: str
    version_id: str
    version_number: int
    digest: str
    installation_revision: int
    is_default: bool = False
    enabled: bool = False
    order: int = 100
    visibility: str = "public"
    always_on: bool = False
    routable: bool = True
    routing_examples: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    compatibility_level: str = "A"
    format_compatible: bool = True
    runtime_ready: bool = True
    compatibility_reasons: tuple[str, ...] = ()
    effective_grants: Mapping[str, Any] = field(default_factory=dict)
    origin: Mapping[str, Any] = field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None

    def as_catalog_item(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "skill_id": self.stable_id,
            "name": self.canonical_name,
            "label": self.label,
            "description": self.description,
            "tool_ids": list(self.tool_ids),
            "is_default": self.is_default,
            "enabled": self.enabled,
            "visibility": self.visibility,
            "order": self.order,
            "always_on": self.always_on,
            "routable": self.routable,
            "routing_examples": {key: list(value) for key, value in self.routing_examples.items()},
            "version": self.version_number,
            "revision": self.installation_revision,
            "digest": self.digest,
            "status": "enabled" if self.enabled else "disabled",
            "origin": dict(self.origin),
            "compatibility": {
                "level": self.compatibility_level,
                "format_compatible": self.format_compatible,
                "runtime_ready": self.runtime_ready,
                "reasons": list(self.compatibility_reasons),
            },
            "capability_grants": dict(self.effective_grants),
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True, slots=True)
class SkillRegistrySnapshot:
    revision: int
    skills: tuple[RuntimeSkill, ...]
    degraded: bool = False
    failure_identity: str | None = None
    _lookup: Mapping[str, RuntimeSkill] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        lookup: dict[str, RuntimeSkill] = {}
        stable_ids: set[str] = set()
        for skill in self.skills:
            if skill.stable_id in stable_ids:
                raise ValueError(f"duplicate Skill stable ID: {skill.stable_id}")
            stable_ids.add(skill.stable_id)
            identifiers = (skill.id, skill.stable_id, skill.canonical_name, *skill.aliases)
            for identifier in identifiers:
                previous = lookup.get(identifier)
                if previous is not None and previous.stable_id != skill.stable_id:
                    raise ValueError(f"duplicate Skill identifier: {identifier}")
                lookup[identifier] = skill
        object.__setattr__(self, "_lookup", MappingProxyType(lookup))

    def get(self, identifier: str) -> RuntimeSkill | None:
        return self._lookup.get(identifier)

    def all(self, *, include_disabled: bool = False) -> tuple[RuntimeSkill, ...]:
        if include_disabled:
            return self.skills
        return tuple(skill for skill in self.skills if skill.enabled)


class StandardSkillRegistry:
    """Atomically publish complete snapshots while readers remain lock-free."""

    def __init__(self) -> None:
        self._write_lock = RLock()
        self._snapshot = SkillRegistrySnapshot(revision=0, skills=())

    @property
    def snapshot(self) -> SkillRegistrySnapshot:
        return self._snapshot

    @property
    def revision(self) -> int:
        return self._snapshot.revision

    def publish(self, snapshot: SkillRegistrySnapshot) -> bool:
        with self._write_lock:
            if snapshot.revision < self._snapshot.revision:
                return False
            # A late failed rebuild must not regress a healthy recovery at the
            # same durable revision. A healthy snapshot may still recover a
            # degraded one at that revision.
            if (
                snapshot.revision == self._snapshot.revision
                and snapshot.degraded
                and not self._snapshot.degraded
            ):
                return False
            self._snapshot = snapshot
            return True

    def get(self, identifier: str) -> RuntimeSkill | None:
        skill = self._snapshot.get(identifier)
        return skill if skill is not None and skill.enabled else None

    def get_managed(self, identifier: str) -> RuntimeSkill | None:
        return self._snapshot.get(identifier)

    def all(self) -> list[RuntimeSkill]:
        return list(self._snapshot.all())

    def all_managed(self) -> list[RuntimeSkill]:
        return list(self._snapshot.all(include_disabled=True))

    def default_skill_ids(self) -> list[str]:
        return [skill.id for skill in self._snapshot.all() if skill.is_default]

    def public_catalog(self, tools: list[dict[str, Any]]) -> dict[str, Any]:
        visible = [
            skill
            for skill in self._snapshot.all()
            if skill.visibility == "public"
        ]
        selected_tools = {
            tool_id
            for skill in visible
            if skill.is_default
            for tool_id in skill.tool_ids
        }
        ordered_default_tools = [
            str(tool["id"])
            for tool in tools
            if tool.get("id") in selected_tools and tool.get("enabled") and tool.get("available", True)
        ]
        return {
            "revision": self._snapshot.revision,
            "skills": [skill.as_catalog_item() for skill in visible],
            "tools": tools,
            "default_skill_ids": [skill.id for skill in visible if skill.is_default],
            "default_tool_ids": ordered_default_tools,
            "allowed_actions": ["view"],
        }


standard_skill_registry = StandardSkillRegistry()
