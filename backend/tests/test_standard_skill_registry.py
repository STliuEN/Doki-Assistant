from app.models.skill_domain import Skill, SkillAlias
from app.skills.registry import (
    RuntimeSkill,
    SkillRegistrySnapshot,
    StandardSkillRegistry,
)
from app.skills.service import _public_skill_id, _sorted_skill_aliases


def _skill(**overrides) -> RuntimeSkill:
    values = {
        "id": "memory_read",
        "stable_id": "00000000-0000-0000-0000-000000000001",
        "canonical_name": "memory-read",
        "aliases": ("memory_read",),
        "label": "Memory Read",
        "description": "Read memories.",
        "tool_ids": (),
        "instructions": "Read only.",
        "resources": (),
        "storage_key": "objects/aa/" + "a" * 64 + ".zip",
        "version_id": "00000000-0000-0000-0000-000000000002",
        "version_number": 1,
        "digest": "a" * 64,
        "installation_revision": 1,
        "enabled": True,
        "is_default": True,
    }
    values.update(overrides)
    return RuntimeSkill(**values)


def test_snapshot_resolves_stable_name_and_legacy_alias() -> None:
    skill = _skill()
    snapshot = SkillRegistrySnapshot(revision=3, skills=(skill,))

    assert snapshot.get(skill.stable_id) is skill
    assert snapshot.get("memory-read") is skill
    assert snapshot.get("memory_read") is skill


def test_public_id_and_alias_catalog_order_are_relationship_order_independent() -> None:
    skill = Skill(canonical_name="memory-read")
    # Simulate different DB relationship materialization orders.
    skill.aliases = [
        SkillAlias(alias_name="memory_read", alias_type="legacy_migration"),
        SkillAlias(alias_name="memory_read_old", alias_type="legacy"),
    ]
    assert [alias.alias_name for alias in _sorted_skill_aliases(skill)] == [
        "memory_read_old",
        "memory_read",
    ]
    assert _public_skill_id(skill) == "memory_read_old"

    skill.aliases.reverse()
    assert [alias.alias_name for alias in _sorted_skill_aliases(skill)] == [
        "memory_read_old",
        "memory_read",
    ]
    assert _public_skill_id(skill) == "memory_read_old"


def test_registry_publishes_a_complete_snapshot_atomically() -> None:
    registry = StandardSkillRegistry()
    assert registry.publish(SkillRegistrySnapshot(revision=2, skills=(_skill(),)))
    assert registry.revision == 2
    assert registry.default_skill_ids() == ["memory_read"]

    assert not registry.publish(SkillRegistrySnapshot(revision=1, skills=()))
    assert registry.get("memory-read") is not None


def test_degraded_snapshot_fails_closed_and_same_revision_can_recover() -> None:
    registry = StandardSkillRegistry()
    healthy = SkillRegistrySnapshot(revision=4, skills=(_skill(),))
    degraded = SkillRegistrySnapshot(
        revision=4,
        skills=(),
        degraded=True,
        failure_identity="failure-identity",
    )
    assert registry.publish(degraded)
    assert registry.snapshot.degraded is True
    assert registry.snapshot.failure_identity == "failure-identity"
    assert registry.get("memory_read") is None
    assert registry.all() == []

    assert registry.publish(healthy)
    assert registry.snapshot.degraded is False
    assert registry.get("memory_read") is not None

    # A late failure from the same revision cannot regress a healthy recovery.
    assert not registry.publish(degraded)
    assert registry.get("memory_read") is not None



def test_prompt_only_skill_does_not_require_tools_to_be_available() -> None:
    skill = _skill(tool_ids=(), runtime_ready=True)
    registry = StandardSkillRegistry()
    registry.publish(SkillRegistrySnapshot(revision=1, skills=(skill,)))

    assert registry.get("memory_read") is skill
    assert registry.all() == [skill]


def test_disabled_skill_is_managed_but_not_routable() -> None:
    skill = _skill(enabled=False, is_default=False)
    registry = StandardSkillRegistry()
    registry.publish(SkillRegistrySnapshot(revision=1, skills=(skill,)))

    assert registry.get("memory-read") is None
    assert registry.get_managed("memory-read") is skill
    assert registry.all() == []


def test_duplicate_aliases_fail_before_publication() -> None:
    other = _skill(
        id="other",
        stable_id="00000000-0000-0000-0000-000000000003",
        canonical_name="other",
        aliases=("memory_read",),
    )

    try:
        SkillRegistrySnapshot(revision=1, skills=(_skill(), other))
    except ValueError as exc:
        assert "duplicate Skill identifier" in str(exc)
    else:
        raise AssertionError("duplicate aliases must be rejected")
