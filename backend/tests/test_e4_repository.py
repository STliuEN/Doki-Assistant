from __future__ import annotations

import asyncio
import hashlib
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.uow import SqlUnitOfWork
from app.e4.repository import E4ConflictError, E4MigrationRepository, E4StateError, E4ValidationError
from app.models.chat_history import Base
from app.models.e4_migration import E4MigrationBatch, E4MigrationEntity, MediaAsset
from app.models.identity_domain import MigrationMap, User
from app.models.job_domain import AuditEvent, Job

E4_TABLES = (
    User.__table__,
    Job.__table__,
    AuditEvent.__table__,
    MigrationMap.__table__,
    E4MigrationBatch.__table__,
    E4MigrationEntity.__table__,
    MediaAsset.__table__,
)

CORRELATION_ID = "aaaaaaaa-1111-4111-8111-111111111111"
USER_ID = "11111111-1111-4111-8111-111111111111"
TARGET_A = "22222222-2222-4222-8222-222222222222"
TARGET_B = "33333333-3333-4333-8333-333333333333"


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
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=E4_TABLES))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def _seed_user(factory):
    async with factory() as session:
        session.add(
            User(
                id=USER_ID,
                username="e4-user",
                email_display="e4@example.test",
                email_normalized="e4@example.test",
                password_hash="test-hash",
            )
        )
        await session.commit()


async def _create_batch(repository: E4MigrationRepository, batch_id: str = "e4-batch-001"):
    return await repository.create_batch(
        migration_batch_id=batch_id,
        snapshot_manifest_digest="a" * 64,
        schema_revision="20260905_0008_e4_business_shadow",
        correlation_id=CORRELATION_ID,
        actor_id="e4-test",
    )


def test_batch_replay_is_idempotent_and_conflicts_are_immutable(tmp_path) -> None:
    async def scenario():
        async with _session_factory(tmp_path / "batch.db") as factory:
            async with SqlUnitOfWork(factory) as uow:
                repository = E4MigrationRepository(uow.require_session())
                first = await _create_batch(repository)
                replay = await _create_batch(repository)
                assert replay.id == first.id
                await uow.commit()

            async with SqlUnitOfWork(factory) as uow:
                repository = E4MigrationRepository(uow.require_session())
                with pytest.raises(E4ConflictError, match="immutable facts"):
                    await repository.create_batch(
                        migration_batch_id="e4-batch-001",
                        snapshot_manifest_digest="b" * 64,
                        schema_revision="20260905_0008_e4_business_shadow",
                        correlation_id=CORRELATION_ID,
                    )

            async with factory() as session:
                assert await session.scalar(select(E4MigrationBatch.id)) == first.id
                audit = (await session.scalars(select(AuditEvent).where(AuditEvent.migration_id == "e4-batch-001"))).all()
                assert len(audit) == 1
                assert audit[0].action == "migration.started"
                assert audit[0].correlation_id == CORRELATION_ID

    _run(scenario())


def test_entity_requires_scope_owner_and_follows_validated_mapping_lifecycle(tmp_path) -> None:
    async def scenario():
        async with _session_factory(tmp_path / "entity.db") as factory:
            await _seed_user(factory)
            async with SqlUnitOfWork(factory) as uow:
                repository = E4MigrationRepository(uow.require_session())
                batch = await _create_batch(repository)
                with pytest.raises(E4ValidationError, match="canonical_user_id"):
                    await repository.record_entity(
                        batch_id=batch.id,
                        source_system="fastapi_legacy",
                        entity_type="note",
                        source_id="note-1",
                        entity_content_digest="b" * 64,
                        scope_type="user",
                    )
                entity = await repository.record_entity(
                    batch_id=batch.id,
                    source_system="fastapi_legacy",
                    entity_type="note",
                    source_id="note-1",
                    entity_content_digest="b" * 64,
                    scope_type="user",
                    canonical_user_id=USER_ID,
                )
                with pytest.raises(E4StateError, match="cannot be mapped"):
                    await repository.map_entity(entity_id=entity.id, target_uuid=TARGET_A)
                await repository.transition_entity(
                    entity_id=entity.id,
                    to_status="validated",
                    expected_status="candidate",
                )
                mapped = await repository.map_entity(entity_id=entity.id, target_uuid=TARGET_A)
                replay = await repository.map_entity(entity_id=entity.id, target_uuid=TARGET_A)
                assert mapped.created is True
                assert replay.created is False
                await repository.mark_imported(entity_id=entity.id, target_uuid=TARGET_A)
                await repository.mark_reconciled(entity_id=entity.id)
                await repository.set_batch_status(batch_id=batch.id, to_status="validated", expected_status="planned")
                await repository.set_batch_status(batch_id=batch.id, to_status="importing", expected_status="validated")
                await repository.set_batch_status(batch_id=batch.id, to_status="imported", expected_status="importing")
                await repository.set_batch_status(batch_id=batch.id, to_status="reconciled", expected_status="imported")
                await uow.commit()

            async with factory() as session:
                persisted = await session.get(E4MigrationEntity, entity.id)
                batch_row = await session.get(E4MigrationBatch, batch.id)
                assert persisted is not None and persisted.status == "reconciled"
                assert batch_row is not None and batch_row.status == "reconciled"
                assert await session.scalar(select(MigrationMap.target_uuid)) == TARGET_A
                audits = (await session.scalars(select(AuditEvent).where(AuditEvent.migration_id == batch.migration_batch_id))).all()
                assert audits and {audit.correlation_id for audit in audits} == {CORRELATION_ID}
                assert {audit.action for audit in audits} >= {
                    "migration.started",
                    "migration.entity_state_changed",
                    "migration.mapped",
                    "migration.imported",
                    "migration.reconciled",
                }

    _run(scenario())


def test_mapping_target_collision_and_entity_digest_conflict_fail_closed(tmp_path) -> None:
    async def scenario():
        async with _session_factory(tmp_path / "mapping-conflict.db") as factory:
            async with SqlUnitOfWork(factory) as uow:
                repository = E4MigrationRepository(uow.require_session())
                batch = await _create_batch(repository)
                first = await repository.record_entity(
                    batch_id=batch.id,
                    source_system="legacy",
                    entity_type="user",
                    source_id="one",
                    entity_content_digest="c" * 64,
                    scope_type="global",
                    status="validated",
                )
                second = await repository.record_entity(
                    batch_id=batch.id,
                    source_system="legacy",
                    entity_type="user",
                    source_id="two",
                    entity_content_digest="d" * 64,
                    scope_type="global",
                    status="validated",
                )
                await repository.map_entity(entity_id=first.id, target_uuid=TARGET_A)
                with pytest.raises(E4ConflictError, match="already mapped"):
                    await repository.map_entity(entity_id=second.id, target_uuid=TARGET_A)
                conflicted = await repository.get_entity(second.id)
                assert conflicted.status == "conflict"
                with pytest.raises(E4ConflictError, match="immutable fact"):
                    await repository.record_entity(
                        batch_id=batch.id,
                        source_system="legacy",
                        entity_type="user",
                        source_id="one",
                        entity_content_digest="e" * 64,
                        scope_type="global",
                        status="validated",
                    )
                await uow.commit()

            async with factory() as session:
                row = await session.scalar(select(E4MigrationEntity).where(E4MigrationEntity.source_id == "one"))
                assert row is not None and row.status == "conflict"
                assert await session.scalar(select(MigrationMap.target_uuid)) == TARGET_A
                blocked = (
                    await session.scalars(
                        select(AuditEvent).where(
                            AuditEvent.migration_id == batch.migration_batch_id,
                            AuditEvent.error_code == "target_uuid_collision",
                        )
                    )
                ).all()
                assert len(blocked) == 1 and blocked[0].correlation_id == CORRELATION_ID

    _run(scenario())


def test_entity_owner_source_key_is_immutable_and_conflict_is_audited(tmp_path) -> None:
    async def scenario():
        async with _session_factory(tmp_path / "owner-conflict.db") as factory:
            await _seed_user(factory)
            async with SqlUnitOfWork(factory) as uow:
                repository = E4MigrationRepository(uow.require_session())
                batch = await _create_batch(repository)
                await repository.record_entity(
                    batch_id=batch.id,
                    source_system="fastapi_legacy",
                    entity_type="note",
                    source_id="owner-note",
                    entity_content_digest="a" * 64,
                    scope_type="user",
                    canonical_user_id=USER_ID,
                    owner_source_key={"source_system": "django", "entity_type": "user", "source_id": "owner-1"},
                )
                with pytest.raises(E4ConflictError, match="immutable fact"):
                    await repository.record_entity(
                        batch_id=batch.id,
                        source_system="fastapi_legacy",
                        entity_type="note",
                        source_id="owner-note",
                        entity_content_digest="a" * 64,
                        scope_type="user",
                        canonical_user_id=USER_ID,
                        owner_source_key={"source_system": "django", "entity_type": "user", "source_id": "owner-2"},
                    )
                await uow.commit()

            async with factory() as session:
                row = await session.scalar(select(E4MigrationEntity).where(E4MigrationEntity.source_id == "owner-note"))
                assert row is not None and row.status == "conflict"
                audit = await session.scalar(
                    select(AuditEvent).where(
                        AuditEvent.migration_id == batch.migration_batch_id,
                        AuditEvent.error_code == "entity_fact_conflict",
                    )
                )
                assert audit is not None and audit.correlation_id == CORRELATION_ID

    _run(scenario())


def test_uow_rollback_removes_batches_entities_and_audits(tmp_path) -> None:
    async def scenario():
        async with _session_factory(tmp_path / "rollback.db") as factory:
            async with SqlUnitOfWork(factory) as uow:
                repository = E4MigrationRepository(uow.require_session())
                batch = await _create_batch(repository)
                await repository.record_entity(
                    batch_id=batch.id,
                    source_system="legacy",
                    entity_type="note",
                    source_id="rollback-note",
                    entity_content_digest="f" * 64,
                    scope_type="global",
                )

            async with factory() as session:
                assert await session.scalar(select(E4MigrationBatch.id)) is None
                assert await session.scalar(select(E4MigrationEntity.id)) is None
                assert await session.scalar(select(AuditEvent.id)) is None

    _run(scenario())


def test_media_bytes_are_sql_authoritative_and_replayable(tmp_path) -> None:
    async def scenario():
        payload = b"original media bytes"
        artifact_digest = hashlib.sha256(payload).hexdigest()
        legacy_md5 = hashlib.md5(payload).hexdigest()
        content_digest = "1" * 64
        async with _session_factory(tmp_path / "media.db") as factory:
            await _seed_user(factory)
            async with SqlUnitOfWork(factory) as uow:
                repository = E4MigrationRepository(uow.require_session())
                batch = await _create_batch(repository)
                global_asset = await repository.record_media_asset(
                    batch_id=batch.id,
                    source_system="filesystem",
                    source_id="global-image",
                    content_blob=payload,
                    content_digest=content_digest,
                    artifact_digest=artifact_digest,
                    legacy_md5=legacy_md5,
                    filename="image.png",
                    mime_type="image/png",
                    scope_type="global",
                )
                replay = await repository.record_media_asset(
                    batch_id=batch.id,
                    source_system="filesystem",
                    source_id="global-image",
                    content_blob=payload,
                    content_digest=content_digest,
                    filename="image.png",
                    mime_type="image/png",
                    scope_type="global",
                )
                assert replay.id == global_asset.id
                second_batch = await _create_batch(repository, "e4-media-replay-002")
                cross_batch_replay = await repository.record_media_asset(
                    batch_id=second_batch.id,
                    source_system="filesystem",
                    source_id="global-image",
                    content_blob=payload,
                    content_digest=content_digest,
                    filename="image.png",
                    mime_type="image/png",
                    scope_type="global",
                )
                assert cross_batch_replay.id == global_asset.id
                assert cross_batch_replay.migration_batch_id == batch.migration_batch_id
                user_asset = await repository.record_media_asset(
                    batch_id=batch.id,
                    source_system="filesystem",
                    source_id="private-image",
                    content_blob=payload,
                    content_digest="2" * 64,
                    filename="private.png",
                    mime_type="image/png",
                    scope_type="user",
                    canonical_user_id=USER_ID,
                )
                assert user_asset.canonical_user_id == USER_ID
                with pytest.raises(E4ValidationError, match="requires canonical_user_id"):
                    await repository.record_media_asset(
                        batch_id=batch.id,
                        source_system="filesystem",
                        source_id="missing-owner",
                        content_blob=payload,
                        content_digest="3" * 64,
                        filename="missing.png",
                        mime_type="image/png",
                        scope_type="user",
                    )
                with pytest.raises(E4ValidationError, match="artifact_digest"):
                    await repository.record_media_asset(
                        batch_id=batch.id,
                        source_system="filesystem",
                        source_id="bad-digest",
                        content_blob=payload,
                        content_digest="4" * 64,
                        artifact_digest="0" * 64,
                        filename="bad.png",
                        mime_type="image/png",
                        scope_type="global",
                    )
                with pytest.raises(E4ConflictError, match="immutable asset"):
                    await repository.record_media_asset(
                        batch_id=batch.id,
                        source_system="filesystem",
                        source_id="global-image",
                        content_blob=payload,
                        content_digest="9" * 64,
                        filename="image.png",
                        mime_type="image/png",
                        scope_type="global",
                    )
                await uow.commit()

            async with factory() as session:
                assets = (await session.scalars(select(MediaAsset).order_by(MediaAsset.source_id))).all()
                assert len(assets) == 2
                assert assets[0].content_blob == payload or assets[1].content_blob == payload
                media_audit = (await session.scalars(select(AuditEvent).where(AuditEvent.action == "migration.media_imported"))).all()
                assert len(media_audit) == 2
                media_conflict = await session.scalar(
                    select(AuditEvent).where(
                        AuditEvent.action == "migration.blocked",
                        AuditEvent.error_code == "media_fact_conflict",
                    )
                )
                assert media_conflict is not None and media_conflict.correlation_id == CORRELATION_ID

    _run(scenario())


def test_audit_payload_rejects_secret_material(tmp_path) -> None:
    async def scenario():
        async with _session_factory(tmp_path / "audit.db") as factory:
            async with SqlUnitOfWork(factory) as uow:
                repository = E4MigrationRepository(uow.require_session())
                with pytest.raises(E4ValidationError, match="secret material"):
                    repository.append_audit(
                        action="migration.test",
                        target_type="migration_batch",
                        target_id="batch",
                        correlation_id=CORRELATION_ID,
                        reason="test",
                        result="blocked",
                        after={"api_key": "must-not-be-recorded"},
                    )

    _run(scenario())
