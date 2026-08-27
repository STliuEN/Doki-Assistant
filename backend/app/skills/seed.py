"""Idempotent one-time installation of Doki's migrated standard Skill seeds."""

from __future__ import annotations

import logging

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.skill_domain import (
    Skill,
    SkillAlias,
    SkillAuditEvent,
    SkillCapabilityGrant,
    SkillInstallation,
    SkillInstallationStatus,
    SkillPackageFormat,
    SkillRegistryEvent,
    SkillRegistryState,
    SkillVersion,
    SkillVersionStatus,
)
from app.skills.seed_manifest import SEED_SKILL_MANIFEST
from app.skills.service import (
    _effective_grants,
    _installation_settings,
    _manifest,
    _requested_capabilities,
)
from app.skills.storage import SkillPackageStorage, skill_package_storage

logger = logging.getLogger(__name__)


def build_seed_runtime_snapshot(*, storage: SkillPackageStorage | None = None):
    """Build a deterministic in-memory snapshot from standard seed packages.

    This is intentionally separate from database installation.  Production
    requests must use the database-backed snapshot populated during startup;
    the helper exists for offline benchmarks, migration tooling, and tests
    that need a real standard package without creating a database.
    """

    from app.skills.registry import (
        RuntimeSkill,
        RuntimeSkillResource,
        SkillRegistrySnapshot,
        standard_skill_registry,
    )
    from app.skills.service import _manifest

    package_storage = storage or skill_package_storage
    runtime_skills: list[RuntimeSkill] = []
    for seed in SEED_SKILL_MANIFEST:
        stored = package_storage.store_directory(seed.package_source)
        manifest = _manifest(stored.package)
        compatibility = manifest["compatibility"]
        resources = tuple(
            RuntimeSkillResource(
                path=item.path,
                kind=item.kind,
                size=item.size,
                sha256=item.sha256,
            )
            for item in stored.package.resource_manifest
            if item.path != "SKILL.md"
        )
        routing_examples = {
            key: tuple(values)
            for key, values in seed.routing_examples
        }
        runtime_skills.append(
            RuntimeSkill(
                id=seed.legacy_alias,
                stable_id=f"seed:{seed.package_name}",
                canonical_name=seed.package_name,
                aliases=(seed.legacy_alias,),
                label=seed.display_name,
                description=stored.package.metadata.description,
                tool_ids=seed.tool_ids,
                instructions=stored.package.instructions,
                resources=resources,
                storage_key=stored.storage_key,
                version_id=f"seed:{seed.package_name}:1",
                version_number=1,
                digest=stored.digest,
                installation_revision=1,
                is_default=seed.default,
                enabled=bool(compatibility.get("runtime_ready", False)),
                order=seed.order,
                visibility=seed.visibility,
                always_on=seed.always_on,
                routable=seed.routable,
                routing_examples=routing_examples,
                compatibility_level=compatibility.get("level", "A"),
                format_compatible=bool(compatibility.get("format_compatible", True)),
                runtime_ready=bool(compatibility.get("runtime_ready", False)),
                compatibility_reasons=tuple(compatibility.get("reasons", [])),
                effective_grants={
                    "tools": list(seed.tool_ids),
                    "resources": {
                        "read": [resource.path for resource in resources if resource.kind != "script"]
                    },
                    "scripts": [],
                    "network": [],
                    "secrets": [],
                },
                origin={"type": "system_seed", "digest": stored.digest},
            )
        )
    snapshot = SkillRegistrySnapshot(revision=1, skills=tuple(runtime_skills))
    # Publishing is idempotent for the same revision and never regresses a
    # newer database-backed snapshot.
    standard_skill_registry.publish(snapshot)
    return snapshot


async def install_standard_skill_seeds(db: AsyncSession) -> int:
    """Install only missing seeds; never overwrite an existing managed Skill."""

    installed = 0
    for seed in SEED_SKILL_MANIFEST:
        existing_result = await db.execute(
            select(Skill)
            .outerjoin(SkillAlias, SkillAlias.skill_id == Skill.id)
            .where(
                or_(
                    Skill.canonical_name == seed.package_name,
                    SkillAlias.alias_name == seed.legacy_alias,
                )
            )
        )
        if existing_result.unique().scalar_one_or_none() is not None:
            continue

        try:
            async with db.begin_nested():
                stored = skill_package_storage.store_directory(seed.package_source)
                manifest = _manifest(stored.package)
                skill = Skill(canonical_name=seed.package_name, created_by="system")
                db.add(skill)
                await db.flush()
                db.add(
                    SkillAlias(
                        skill_id=skill.id,
                        alias_name=seed.legacy_alias,
                        alias_type="legacy_migration",
                    )
                )
                version = SkillVersion(
                    skill_id=skill.id,
                    version_number=1,
                    package_format=SkillPackageFormat.AGENT_SKILLS_V1,
                    source="legacy_migration",
                    package_digest=stored.digest,
                    storage_key=stored.storage_key,
                    package_size_bytes=stored.archive_size,
                    name=stored.package.metadata.name,
                    display_name=seed.display_name,
                    description=stored.package.metadata.description,
                    manifest={**manifest, "version_note": "One-time migration to the standard Skill package format."},
                    requested_capabilities=_requested_capabilities(stored.package),
                    status=SkillVersionStatus.READY,
                    created_by="system",
                )
                db.add(version)
                await db.flush()
                settings = _installation_settings(
                    default=seed.default,
                    visibility=seed.visibility,
                    order=seed.order,
                    tools=seed.tool_ids,
                    always_on=seed.always_on,
                    routable=seed.routable,
                    routing_examples=dict(seed.routing_examples),
                )
                installation = SkillInstallation(
                        skill_id=skill.id,
                        active_version_id=version.id,
                        draft_version_id=None,
                        status=SkillInstallationStatus.ENABLED,
                        settings=settings,
                        revision=1,
                        created_by="system",
                        updated_by="system",
                    )
                db.add(installation)
                await db.flush()
                db.add(
                    SkillCapabilityGrant(
                        installation_id=installation.id,
                        skill_version_id=version.id,
                        grants=_effective_grants(version, seed.tool_ids),
                        revision=1,
                        granted_by="system",
                    )
                )
                db.add(
                    SkillAuditEvent(
                        skill_id=skill.id,
                        skill_version_id=version.id,
                        installation_id=installation.id,
                        actor_type="system",
                        actor_id="system",
                        action="legacy_seed_migrated",
                        target_type="skill",
                        target_id=skill.id,
                        details={"legacy_alias": seed.legacy_alias, "digest": stored.digest},
                    )
                )
                installed += 1
        except Exception as exc:
            logger.error("Standard Skill seed %s failed validation: %s", seed.package_name, exc)
            continue

    if installed:
        state_result = await db.execute(
            select(SkillRegistryState).where(SkillRegistryState.id == "global").with_for_update()
        )
        state = state_result.scalar_one_or_none()
        if state is None:
            state = SkillRegistryState(id="global", revision=0)
            db.add(state)
            await db.flush()
        state.revision = int(state.revision) + 1
        db.add(
            SkillRegistryEvent(
                revision=state.revision,
                event_type="standard_seed_migration_completed",
                payload={"installed": installed},
            )
        )
    await db.commit()
    return installed
