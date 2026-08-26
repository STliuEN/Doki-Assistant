from __future__ import annotations

import asyncio
import base64
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.chat_history import Base
from app.models.skill_domain import (
    Skill,
    SkillAlias,
    SkillAuditEvent,
    SkillCapabilityGrant,
    SkillImport,
    SkillInstallation,
    SkillRegistryEvent,
    SkillRegistryState,
    SkillRunBinding,
    SkillVersion,
)
from app.skills.package import SkillPackageError
from app.skills.registry import StandardSkillRegistry
from app.skills.schema import (
    SkillDraftCreate,
    SkillDraftUpdate,
    SkillResourceChanges,
    SkillResourceInput,
)
from app.skills.service import SkillConflictError, SkillService
from app.skills.storage import SkillPackageStorage

SKILL_TABLES = (
    Skill.__table__,
    SkillAlias.__table__,
    SkillVersion.__table__,
    SkillInstallation.__table__,
    SkillCapabilityGrant.__table__,
    SkillImport.__table__,
    SkillAuditEvent.__table__,
    SkillRegistryState.__table__,
    SkillRegistryEvent.__table__,
    SkillRunBinding.__table__,
)


def _run(coro):
    return asyncio.run(coro)


@asynccontextmanager
async def _session_factory(database_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection,
                tables=SKILL_TABLES,
            )
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _service(storage_root) -> SkillService:
    service = SkillService()
    service.storage = SkillPackageStorage(storage_root)
    service.registry = StandardSkillRegistry()
    return service


def _draft(name: str = "transaction-skill", instructions: str = "Version one.") -> SkillDraftCreate:
    return SkillDraftCreate(
        name=name,
        display_name="Transaction Skill",
        description="Exercises the standard Skill transaction lifecycle.",
        instructions=instructions,
    )


async def _publish(service: SkillService, db, skill_id: str, revision: int):
    return await service.publish_draft(
        db,
        skill_id,
        actor_id="admin",
        expected_revision=revision,
        enabled=True,
        default=True,
        visibility="public",
        order=10,
        tools=(),
        always_on=False,
        routable=True,
        routing_examples={"positive": ["transaction test"]},
    )


async def _approve_import(
    service: SkillService,
    db,
    import_result: dict,
    *,
    expected_revision: int,
):
    return await service.approve_import(
        db,
        import_result["id"],
        actor_id="admin",
        expected_digest=import_result["digest"],
        expected_revision=expected_revision,
        enabled=False,
        default=False,
        visibility="public",
        order=100,
        tools=(),
        always_on=False,
        routable=True,
        routing_examples={},
    )


def test_draft_publish_conflict_and_rollback_are_transactional(tmp_path) -> None:
    async def scenario():
        async with _session_factory(tmp_path / "lifecycle.db") as factory:
            service = _service(tmp_path / "packages")
            async with factory() as db:
                draft = await service.create_draft(db, _draft(), "admin")
                assert draft["status"] == "draft"
                assert service.registry.snapshot.skills == ()

                published_v1 = await _publish(service, db, draft["id"], draft["revision"])
                v1_id = published_v1["version_id"]
                assert service.registry.get("transaction-skill").instructions.strip() == "Version one."

                draft_v2 = await service.save_draft(
                    db,
                    draft["id"],
                    SkillDraftUpdate(
                        name="transaction-skill",
                        display_name="Transaction Skill",
                        description="Exercises the standard Skill transaction lifecycle.",
                        instructions="Version two.",
                        expected_revision=published_v1["revision"],
                    ),
                    "admin",
                )
                assert draft_v2["status"] == "draft"
                assert service.registry.get("transaction-skill").version_id == v1_id

                published_v2 = await _publish(service, db, draft["id"], draft_v2["revision"])
                assert published_v2["version_id"] != v1_id
                assert service.registry.get("transaction-skill").instructions.strip() == "Version two."

                with pytest.raises(SkillConflictError, match="revision changed"):
                    await service.update_settings(
                        db,
                        draft["id"],
                        actor_id="admin",
                        expected_revision=draft_v2["revision"],
                        patch={"order": 20},
                    )

                rolled_back = await service.rollback(
                    db,
                    draft["id"],
                    actor_id="admin",
                    expected_revision=published_v2["revision"],
                    version_id=v1_id,
                )
                assert rolled_back["version_id"] == v1_id
                assert service.registry.get("transaction-skill").instructions.strip() == "Version one."

                revisions = list(
                    (
                        await db.execute(
                            select(SkillRegistryEvent.revision).order_by(SkillRegistryEvent.revision)
                        )
                    ).scalars()
                )
                assert revisions == sorted(set(revisions))
                assert revisions == [1, 2, 3]

    _run(scenario())


@pytest.mark.parametrize(
    ("display_name", "version_note"),
    [
        ("Renamed Transaction Skill", ""),
        ("Transaction Skill", "A different management note"),
    ],
)
def test_same_package_digest_rejects_conflicting_display_metadata(
    tmp_path,
    display_name: str,
    version_note: str,
) -> None:
    async def scenario():
        async with _session_factory(tmp_path / f"metadata-{len(version_note)}.db") as factory:
            service = _service(tmp_path / f"packages-{len(version_note)}")
            async with factory() as db:
                draft = await service.create_draft(db, _draft(), "admin")

                with pytest.raises(SkillConflictError, match="different display metadata"):
                    await service.save_draft(
                        db,
                        draft["id"],
                        SkillDraftUpdate(
                            name="transaction-skill",
                            display_name=display_name,
                            description="Exercises the standard Skill transaction lifecycle.",
                            instructions="Version one.",
                            version_note=version_note,
                            expected_revision=draft["revision"],
                        ),
                        "admin",
                    )

                unchanged = await service.get_detail(db, draft["id"], can_manage=True)
                assert unchanged["revision"] == draft["revision"]
                assert unchanged["version_id"] == draft["version_id"]

    _run(scenario())


def test_new_import_uses_zero_as_the_explicit_uninstalled_revision(tmp_path) -> None:
    async def scenario():
        async with _session_factory(tmp_path / "new-import.db") as factory:
            service = _service(tmp_path / "new-import-packages")
            async with factory() as db:
                archive = service._archive_from_draft(_draft(name="new-import-skill"))
                reviewed = await service.import_archive(
                    db,
                    archive,
                    actor_id="admin",
                    idempotency_key="new-import",
                )

                assert reviewed["revision"] is None
                installed = await _approve_import(service, db, reviewed, expected_revision=0)
                assert installed["name"] == "new-import-skill"
                assert installed["revision"] == 1
                assert installed["enabled"] is False
                installation = (
                    await db.execute(select(SkillInstallation).where(SkillInstallation.skill_id == installed["skill_id"]))
                ).scalar_one()
                assert installation.status.value == "disabled"
                assert installation.settings["installed_disabled"] is True
                assert installed["installation_state"] == "installed_disabled"

    _run(scenario())


def test_import_storage_io_failure_is_quarantined_and_not_published(tmp_path, monkeypatch) -> None:
    async def scenario():
        async with _session_factory(tmp_path / "import-storage-io.db") as factory:
            service = _service(tmp_path / "import-storage-io-packages")

            def fail_store(_archive: bytes):
                raise PermissionError("storage volume is read-only")

            monkeypatch.setattr(service.storage, "store_archive", fail_store)
            async with factory() as db:
                result = await service.import_archive(
                    db,
                    service._archive_from_draft(_draft(name="storage-io-skill")),
                    actor_id="admin",
                    idempotency_key="storage-io",
                )

                assert result["status"] == "quarantined"
                assert result["diagnostics"][0]["code"] == "storage_unavailable"
                record = await db.get(SkillImport, result["id"])
                assert record is not None
                assert record.status.value == "quarantined"
                assert record.skill_id is None
                assert service.registry.snapshot.skills == ()

    _run(scenario())


def test_import_approval_ignores_requested_enable_and_requires_separate_transition(tmp_path) -> None:
    async def scenario():
        async with _session_factory(tmp_path / "import-disabled.db") as factory:
            service = _service(tmp_path / "import-disabled-packages")
            async with factory() as db:
                archive = service._archive_from_draft(_draft(name="contained-import"))
                reviewed = await service.import_archive(
                    db,
                    archive,
                    actor_id="admin",
                    idempotency_key="contained-import",
                )
                installed = await service.approve_import(
                    db,
                    reviewed["id"],
                    actor_id="admin",
                    expected_digest=reviewed["digest"],
                    expected_revision=0,
                    enabled=True,
                    default=True,
                    visibility="public",
                    order=100,
                    tools=(),
                    always_on=False,
                    routable=True,
                    routing_examples={},
                )

                assert installed["enabled"] is False
                assert installed["default"] is False
                assert service.registry.get("contained-import") is None

    _run(scenario())


def test_repeated_published_import_revalidates_storage_before_return(tmp_path) -> None:
    async def scenario():
        async with _session_factory(tmp_path / "published-import-retry.db") as factory:
            service = _service(tmp_path / "published-import-retry-packages")
            async with factory() as db:
                archive = service._archive_from_draft(_draft(name="published-import-retry"))
                reviewed = await service.import_archive(
                    db,
                    archive,
                    actor_id="admin",
                    idempotency_key="published-import-retry",
                )
                installed = await _approve_import(service, db, reviewed, expected_revision=0)
                version = await db.get(SkillVersion, installed["version_id"])
                assert version is not None
                (service.storage.root / version.storage_key).write_bytes(b"tampered")

                with pytest.raises(SkillPackageError, match="ZIP|zip|digest"):
                    await _approve_import(service, db, reviewed, expected_revision=0)

    _run(scenario())


def test_publish_revalidates_storage_before_switching_active_version(tmp_path) -> None:
    async def scenario():
        async with _session_factory(tmp_path / "publish-digest.db") as factory:
            service = _service(tmp_path / "publish-digest-packages")
            async with factory() as db:
                draft = await service.create_draft(db, _draft(), "admin")
                version = await db.get(SkillVersion, draft["version_id"])
                object_path = service.storage.root / version.storage_key
                object_path.write_bytes(b"not-a-zip")

                with pytest.raises(Exception, match="storage|ZIP|zip"):
                    await _publish(service, db, draft["id"], draft["revision"])

                await db.rollback()
                installation = (
                    await db.execute(select(SkillInstallation).where(SkillInstallation.skill_id == draft["skill_id"]))
                ).scalar_one()
                assert installation.active_version_id is None
                assert service.registry.snapshot.skills == ()

    _run(scenario())


def test_post_commit_registry_refresh_cancellation_preserves_pointer_and_outbox(tmp_path, monkeypatch) -> None:
    async def scenario():
        async with _session_factory(tmp_path / "publish-cancel.db") as factory:
            service = _service(tmp_path / "publish-cancel-packages")
            async with factory() as db:
                draft = await service.create_draft(db, _draft(name="publish-cancel"), "admin")

                async def cancel_refresh(*_args, **_kwargs):
                    raise asyncio.CancelledError()

                monkeypatch.setattr(service, "refresh_registry", cancel_refresh)
                published = await _publish(service, db, draft["id"], draft["revision"])

                installation = (
                    await db.execute(
                        select(SkillInstallation).where(
                            SkillInstallation.skill_id == draft["skill_id"]
                        )
                    )
                ).scalar_one()
                assert installation.active_version_id == published["version_id"]
                pending = (
                    await db.execute(
                        select(SkillRegistryEvent).where(SkillRegistryEvent.processed_at.is_(None))
                    )
                ).scalars().all()
                assert pending

    _run(scenario())


def test_import_approval_is_bound_to_the_reviewed_installation_revision(tmp_path) -> None:
    async def scenario():
        async with _session_factory(tmp_path / "import-cas.db") as factory:
            service = _service(tmp_path / "import-cas-packages")
            async with factory() as db:
                draft = await service.create_draft(db, _draft(), "admin")
                published = await _publish(service, db, draft["id"], draft["revision"])
                archive = service._archive_from_draft(_draft(instructions="Imported update."))
                reviewed = await service.import_archive(
                    db,
                    archive,
                    actor_id="admin",
                    idempotency_key="existing-import",
                )
                assert reviewed["revision"] == published["revision"]

                updated = await service.update_settings(
                    db,
                    draft["id"],
                    actor_id="admin",
                    expected_revision=published["revision"],
                    patch={"order": 22},
                )

                with pytest.raises(SkillConflictError, match="reviewed at revision"):
                    await _approve_import(
                        service,
                        db,
                        reviewed,
                        expected_revision=updated["revision"],
                    )
                with pytest.raises(SkillConflictError, match="revision changed"):
                    await _approve_import(
                        service,
                        db,
                        reviewed,
                        expected_revision=reviewed["revision"],
                    )

                unchanged = await service.get_detail(db, draft["id"], can_manage=True)
                assert unchanged["digest"] == published["digest"]
                assert unchanged["order"] == 22

    _run(scenario())


def test_admin_catalog_includes_drafts_without_exposing_them_to_runtime_users(tmp_path) -> None:
    async def scenario():
        async with _session_factory(tmp_path / "draft-catalog.db") as factory:
            service = _service(tmp_path / "packages")
            async with factory() as db:
                draft = await service.create_draft(db, _draft(), "admin")

                public_catalog = await service.catalog(db, can_manage=False, tools=[])
                admin_catalog = await service.catalog(db, can_manage=True, tools=[])

                assert public_catalog["skills"] == []
                assert service.registry.snapshot.skills == ()
                assert admin_catalog["skills"] == [
                    {
                        "id": "transaction-skill",
                        "skill_id": draft["skill_id"],
                        "name": "transaction-skill",
                        "label": "Transaction Skill",
                        "description": "Exercises the standard Skill transaction lifecycle.",
                        "tool_ids": [],
                        "is_default": False,
                        "enabled": False,
                        "visibility": "public",
                        "order": 100,
                        "always_on": False,
                        "routable": True,
                        "routing_examples": {},
                        "version": 1,
                        "revision": 1,
                        "digest": draft["digest"],
                        "status": "draft",
                        "origin": {"type": "visual_editor", "digest": draft["digest"]},
                        "compatibility": draft["compatibility"],
                        "updated_at": draft["updated_at"],
                    }
                ]

    _run(scenario())


def test_incremental_resource_changes_preserve_replace_add_and_delete_files(tmp_path) -> None:
    async def scenario():
        async with _session_factory(tmp_path / "resources.db") as factory:
            service = _service(tmp_path / "packages")
            async with factory() as db:
                draft = await service.create_draft(
                    db,
                    SkillDraftCreate(
                        name="resource-skill",
                        display_name="Resource Skill",
                        description="Exercises incremental package resource editing.",
                        instructions="Read the bundled references when needed.",
                        resources=[
                            SkillResourceInput(
                                path="references/keep.md",
                                content_base64=base64.b64encode(b"keep\n").decode("ascii"),
                            ),
                            SkillResourceInput(
                                path="references/change.md",
                                content_base64=base64.b64encode(b"old\n").decode("ascii"),
                            ),
                            SkillResourceInput(
                                path="assets/remove.txt",
                                content_base64=base64.b64encode(b"remove\n").decode("ascii"),
                            ),
                        ],
                    ),
                    "admin",
                )

                updated = await service.save_draft(
                    db,
                    draft["id"],
                    SkillDraftUpdate(
                        name="resource-skill",
                        display_name="Resource Skill",
                        description="Exercises incremental package resource editing.",
                        instructions="Read the bundled references when needed.",
                        expected_revision=draft["revision"],
                        resource_changes=SkillResourceChanges(
                            upsert=[
                                SkillResourceInput(
                                    path="references/change.md",
                                    content_base64=base64.b64encode(b"new\n").decode("ascii"),
                                ),
                                SkillResourceInput(
                                    path="references/added.md",
                                    content_base64=base64.b64encode(b"added\n").decode("ascii"),
                                ),
                            ],
                            delete=["assets/remove.txt"],
                        ),
                    ),
                    "admin",
                )

                assert {resource["path"] for resource in updated["resources"]} == {
                    "references/added.md",
                    "references/change.md",
                    "references/keep.md",
                }
                keep, _ = await service.read_resource(db, draft["id"], "references/keep.md")
                changed, _ = await service.read_resource(db, draft["id"], "references/change.md")
                added, _ = await service.read_resource(db, draft["id"], "references/added.md")
                assert keep == b"keep\n"
                assert changed == b"new\n"
                assert added == b"added\n"

    _run(scenario())


def test_executable_package_stays_disabled_and_ungranted(tmp_path) -> None:
    async def scenario():
        async with _session_factory(tmp_path / "executable.db") as factory:
            service = _service(tmp_path / "packages")
            script = base64.b64encode(b"console.log('not executed')\n").decode("ascii")
            async with factory() as db:
                draft = await service.create_draft(
                    db,
                    SkillDraftCreate(
                        name="executable-skill",
                        display_name="Executable Skill",
                        description="Contains a script that must remain disabled.",
                        instructions="Never execute scripts in the API process.",
                        resources=[
                            SkillResourceInput(
                                path="scripts/main.mjs",
                                content_base64=script,
                            )
                        ],
                    ),
                    "admin",
                )
                published = await _publish(service, db, draft["id"], draft["revision"])

                assert published["compatibility"]["level"] == "C"
                assert published["compatibility"]["runtime_ready"] is False
                assert published["enabled"] is False
                assert published["default"] is False
                assert published["capability_grants"]["scripts"] == []
                assert service.registry.get("executable-skill") is None

    _run(scenario())


def test_registry_reconciliation_converges_independent_process_snapshots(tmp_path) -> None:
    async def scenario():
        async with _session_factory(tmp_path / "registry.db") as factory:
            first = _service(tmp_path / "packages")
            second = _service(tmp_path / "packages")
            async with factory() as db:
                draft = await first.create_draft(db, _draft(), "admin")
                published = await _publish(first, db, draft["id"], draft["revision"])
                assert second.registry.revision == 0

                second_snapshot = await second.reconcile_registry(db)
                assert second_snapshot.revision == first.registry.revision
                assert second.registry.get("transaction-skill").digest == published["digest"]

                updated = await first.update_settings(
                    db,
                    draft["id"],
                    actor_id="admin",
                    expected_revision=published["revision"],
                    patch={"order": 77},
                )
                assert second.registry.revision < first.registry.revision
                await second.consume_registry_events(db)
                assert second.registry.revision == first.registry.revision
                assert second.registry.get("transaction-skill").order == 77
                assert updated["revision"] > published["revision"]

    _run(scenario())


def test_standard_seed_install_is_idempotent(tmp_path, monkeypatch) -> None:
    async def scenario():
        from app.skills import seed as seed_module

        async with _session_factory(tmp_path / "seed.db") as factory:
            monkeypatch.setattr(
                seed_module,
                "skill_package_storage",
                SkillPackageStorage(tmp_path / "packages"),
            )
            async with factory() as db:
                assert await seed_module.install_standard_skill_seeds(db) == 10
                assert await seed_module.install_standard_skill_seeds(db) == 0
                count = await db.scalar(select(func.count()).select_from(Skill))
                grant_count = await db.scalar(
                    select(func.count()).select_from(SkillCapabilityGrant)
                )
                assert count == 10
                assert grant_count == 10

    _run(scenario())


def test_agent_run_persists_exact_version_digest_and_grants(tmp_path, monkeypatch) -> None:
    async def scenario():
        from app.services import agent_run_service

        async with _session_factory(tmp_path / "binding.db") as factory:
            service = _service(tmp_path / "packages")
            async with factory() as db:
                draft = await service.create_draft(db, _draft(), "admin")
                published = await _publish(service, db, draft["id"], draft["revision"])

                class _McpRegistry:
                    async def ensure_fresh(self):
                        return False

                monkeypatch.setattr(agent_run_service, "skill_service", service)
                monkeypatch.setattr(agent_run_service, "mcp_tool_registry", _McpRegistry())
                plan = await agent_run_service.prepare_agent_run(
                    db,
                    "user-1",
                    query="transaction test",
                    model_config_id=None,
                    prompt_type=None,
                    skill_ids=[draft["id"]],
                    tool_ids=[],
                    session_id="session-1",
                    run_id="run-1",
                )

                binding = await db.get(SkillRunBinding, "run-1")
                assert binding is not None
                assert binding.registry_revision == plan.registry_revision
                assert binding.skill_bindings == plan.skill_bindings
                assert binding.skill_bindings[0]["version_id"] == published["version_id"]
                assert binding.skill_bindings[0]["digest"] == published["digest"]
                assert binding.effective_grants == plan.effective_grants

    _run(scenario())
