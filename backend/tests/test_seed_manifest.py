from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.skills.package import load_skill_package
from app.skills.seed_manifest import SEED_PACKAGES_DIR, SEED_SKILL_MANIFEST, SeedSkillManifest

EXPECTED_SEED_NAMES = {
    "knowledge-research",
    "mcp-smoke-test",
    "memory-cleanup",
    "memory-read",
    "memory-write",
    "note-research",
    "note-writer",
    "public-info-lookup",
    "review-planner",
    "system-context",
}


def test_seed_manifest_is_complete_unique_and_immutable() -> None:
    assert isinstance(SEED_SKILL_MANIFEST, tuple)
    assert {item.package_name for item in SEED_SKILL_MANIFEST} == EXPECTED_SEED_NAMES
    assert {item.legacy_alias for item in SEED_SKILL_MANIFEST} == {
        name.replace("-", "_") for name in EXPECTED_SEED_NAMES
    }
    assert len({item.order for item in SEED_SKILL_MANIFEST}) == len(SEED_SKILL_MANIFEST)
    with pytest.raises(FrozenInstanceError):
        SEED_SKILL_MANIFEST[0].order = 0  # type: ignore[misc]


def test_seed_package_directories_exactly_match_the_manifest() -> None:
    package_directories = {
        item.name
        for item in SEED_PACKAGES_DIR.iterdir()
        if item.is_dir() and not item.is_symlink()
    }

    assert package_directories == EXPECTED_SEED_NAMES


def test_each_seed_is_a_valid_instruction_only_standard_package() -> None:
    for seed in SEED_SKILL_MANIFEST:
        assert seed.source_path == SEED_PACKAGES_DIR / seed.package_name

        package = load_skill_package(seed.source_path)

        assert package.package_type == "directory"
        assert package.metadata.name == seed.package_name
        assert {"name", "description"} <= set(package.metadata.frontmatter)
        assert package.metadata.description.strip()
        assert package.instructions.strip()
        assert tuple((resource.path, resource.kind) for resource in package.resources) == (
            ("SKILL.md", "instructions"),
        )
        assert package.total_uncompressed_bytes == package.resources[0].size


def test_seed_runtime_descriptors_are_well_formed_and_fail_closed() -> None:
    for seed in SEED_SKILL_MANIFEST:
        assert seed.display_name.strip()
        assert seed.visibility in {"public", "private"}
        assert seed.order >= 0
        assert len(seed.tool_ids) == len(set(seed.tool_ids))
        assert all(tool_id.strip() for tool_id in seed.tool_ids)

        routing_examples = dict(seed.routing_examples)
        assert set(routing_examples) <= {"positive", "negative"}
        assert all(examples for examples in routing_examples.values())
        assert all(example.strip() for examples in routing_examples.values() for example in examples)
        if seed.routable:
            assert routing_examples.get("positive")

        package = load_skill_package(seed.source_path)
        assert all(resource.kind != "script" for resource in package.resources)


def test_seed_descriptor_rejects_a_source_outside_its_named_package() -> None:
    original = SEED_SKILL_MANIFEST[0]
    with pytest.raises(ValueError, match="seed source"):
        SeedSkillManifest(
            package_name=original.package_name,
            package_source=SEED_PACKAGES_DIR / "different-package",
            legacy_alias=original.legacy_alias,
            display_name=original.display_name,
            tool_ids=original.tool_ids,
            default=original.default,
            visibility=original.visibility,
            order=original.order,
            always_on=original.always_on,
            routable=original.routable,
            routing_examples=original.routing_examples,
        )
