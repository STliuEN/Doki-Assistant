from __future__ import annotations

import asyncio
import base64
import hashlib
from contextlib import asynccontextmanager
from datetime import datetime

import pytest
from sqlalchemy import event, select
from sqlalchemy.dialects.mysql import LONGBLOB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.db.uow import SqlUnitOfWork
from app.e4.identity import deterministic_target_uuid
from app.e4.importer import (
    E4ImportBlocked,
    E4ImportConflict,
    E4Importer,
    E4ImportResult,
    build_business_dry_run,
    load_business_bundle,
)
from app.e4.repository import E4MigrationRepository
from app.models.chat_history import Base, ChatMessage, ChatSession
from app.models.e4_migration import E4MigrationBatch, E4MigrationEntity, MediaAsset
from app.models.embedding_config import UserEmbeddingConfig
from app.models.identity_domain import MigrationMap, User
from app.models.job_domain import AuditEvent, Job, JobAttempt
from app.models.knowledge_document import KnowledgeSourceDocument
from app.models.memory_item import MemoryItem
from app.models.model_config import UserModelConfig
from app.models.note import Note
from app.models.note_template import NoteTemplate
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

CORRELATION_ID = "aaaaaaaa-1111-4111-8111-111111111111"
USER_ID = "11111111-1111-4111-8111-111111111111"


@compiles(LONGBLOB, "sqlite")
def _compile_long_blob_for_sqlite(_type, _compiler, **_kwargs):
    return "BLOB"

TABLES = (
    User.__table__,
    ChatSession.__table__,
    ChatMessage.__table__,
    KnowledgeSourceDocument.__table__,
    MemoryItem.__table__,
    NoteTemplate.__table__,
    Note.__table__,
    UserEmbeddingConfig.__table__,
    UserModelConfig.__table__,
    SkillRunBinding.__table__,
    MigrationMap.__table__,
    Job.__table__,
    JobAttempt.__table__,
    AuditEvent.__table__,
    E4MigrationBatch.__table__,
    E4MigrationEntity.__table__,
    MediaAsset.__table__,
    Skill.__table__,
    SkillAlias.__table__,
    SkillVersion.__table__,
    SkillInstallation.__table__,
    SkillCapabilityGrant.__table__,
    SkillImport.__table__,
    SkillAuditEvent.__table__,
    SkillRegistryEvent.__table__,
    SkillRegistryState.__table__,
)


def _run(coro):
    return asyncio.run(coro)


@asynccontextmanager
async def _factory(path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")

    @event.listens_for(engine.sync_engine, "connect")
    def _foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=TABLES))
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
                username="e4-import-user",
                email_display="e4-import@example.test",
                email_normalized="e4-import@example.test",
                password_hash="test-hash",
            )
        )
        await session.commit()


def _bundle(entity, *, media=(), existing_mappings=()):
    return {
        "artifact_kind": "e4-business-bundle",
        "schema_version": 1,
        "migration_batch_id": "e4-import-001",
        "snapshot_manifest_digest": "a" * 64,
        "schema_revision": "20260905_0008_e4_business_shadow",
        "correlation_id": CORRELATION_ID,
        "entities": [entity],
        "media": list(media),
        "existing_mappings": list(existing_mappings),
    }


def test_business_bundle_load_and_offline_dry_run(tmp_path):
    entity = {
        "source_system": "fastapi_legacy",
        "entity_type": "note",
        "source_id": "note-1",
        "entity_content_digest": "b" * 64,
        "scope": "global",
        "data": {"user_id": "legacy-user", "title": "E4", "content": "body"},
    }
    bundle = load_business_bundle(_bundle(entity))
    report = build_business_dry_run(bundle)
    assert report.blocked is False
    assert report.decisions[0].target_uuid == deterministic_target_uuid(
        {"source_system": "fastapi_legacy", "entity_type": "note", "source_id": "note-1"}
    )


def test_skill_input_dependency_order_and_replay_preserve_legacy_facts(tmp_path):
    async def scenario():
        skill_id = "11111111-2222-4333-8444-555555555555"
        alias_id = "22222222-2222-4333-8444-555555555555"
        parent = {"source_system": "skill_legacy", "entity_type": "skill", "source_id": skill_id}
        child = {
            "source_system": "skill_legacy", "entity_type": "skill_alias", "source_id": alias_id,
            "scope": "global", "entity_content_digest": "c" * 64, "foreign_keys": [parent],
            "data": {"skill_id": skill_id, "alias_name": "legacy-example", "created_at": "2026-06-15T12:00:00"},
        }
        bundle = _bundle(child)
        bundle["entities"].append({**parent, "scope": "global", "entity_content_digest": "d" * 64,
                                   "data": {"canonical_name": "example", "created_by": "system"}})
        bundle["entities"].append({"source_system": "skill_legacy", "entity_type": "skill_registry_state", "source_id": "global",
                                   "scope": "global", "entity_content_digest": "e" * 64, "data": {"revision": 7}})
        async with _factory(tmp_path / "skill-input.db") as factory:
            async with SqlUnitOfWork(factory) as uow:
                first = await E4Importer(uow.require_session()).import_bundle(bundle)
                await uow.commit()
            async with SqlUnitOfWork(factory) as uow:
                replay = await E4Importer(uow.require_session()).import_bundle(bundle)
                await uow.commit()
            async with factory() as session:
                alias = await session.get(SkillAlias, alias_id)
                assert alias.skill_id == skill_id
                assert alias.created_at == datetime(2026, 6, 15, 12)
                assert (await session.get(SkillRegistryState, "global")).revision == 7
                assert (await session.get(Skill, skill_id)).created_by == "system"
            assert first.imported_entities == 3
            assert replay.skipped_entities == 3
    _run(scenario())


def test_business_dry_run_reports_already_mapped_entities_as_skipped(tmp_path):
    entity = {
        "source_system": "fastapi_legacy",
        "entity_type": "note",
        "source_id": "note-replay",
        "entity_content_digest": "b" * 64,
        "scope": "global",
        "data": {"user_id": "legacy-user", "title": "E4", "content": "body"},
    }
    target_uuid = deterministic_target_uuid(entity)
    bundle = _bundle(
        entity,
        existing_mappings=[
            {
                **{key: entity[key] for key in ("source_system", "entity_type", "source_id")},
                "target_uuid": target_uuid,
                "source_digest": entity["entity_content_digest"],
                "status": "mapped",
            }
        ],
    )
    async def scenario():
        async with _factory(tmp_path / "dry-run.db") as factory:
            async with SqlUnitOfWork(factory) as uow:
                result = await E4Importer(uow.require_session()).import_bundle(bundle, dry_run=True)
                assert result.skipped_entities == 1
                assert result.imported_entities == 0
                assert result.dry_run is True

    _run(scenario())


def test_import_replay_is_idempotent_and_sets_canonical_shadow(tmp_path):
    async def scenario():
        entity = {
            "source_system": "fastapi_legacy",
            "entity_type": "note",
            "source_id": "note-1",
            "entity_content_digest": "b" * 64,
            "scope": "global",
            "data": {"user_id": "legacy-user", "title": "E4", "content": "body", "tags": []},
        }
        bundle = _bundle(entity)
        async with _factory(tmp_path / "import.db") as factory:
            async with SqlUnitOfWork(factory) as uow:
                first = await E4Importer(uow.require_session()).import_bundle(bundle)
                await uow.commit()
            async with SqlUnitOfWork(factory) as uow:
                replay = await E4Importer(uow.require_session()).import_bundle(bundle)
                await uow.commit()
            async with factory() as session:
                note = await session.scalar(select(Note).where(Note.id == "note-1"))
                mapping = await session.scalar(select(MigrationMap).where(MigrationMap.source_id == "note-1"))
                batch = await session.scalar(select(E4MigrationBatch).where(E4MigrationBatch.migration_batch_id == "e4-import-001"))
                assert note is not None and note.canonical_id == deterministic_target_uuid(
                    {"source_system": "fastapi_legacy", "entity_type": "note", "source_id": "note-1"}
                )
                assert mapping is not None and mapping.status == "mapped"
                assert batch is not None and batch.status == "imported"
                assert first.imported_entities == 1
                assert replay.imported_entities == 0
                assert replay.skipped_entities == 1

    _run(scenario())


def test_missing_key_version_quarantines_encrypted_config_without_row_write(tmp_path):
    async def scenario():
        owner_key = {"source_system": "fastapi_legacy", "entity_type": "user", "source_id": USER_ID}
        owner_target = deterministic_target_uuid(owner_key)
        entity = {
            "source_system": "fastapi_legacy",
            "entity_type": "model_config",
            "source_id": "config-1",
            "entity_content_digest": "c" * 64,
            "scope": "user",
            "owner": owner_key,
            "data": {
                "user_id": "owner-1",
                "model_type": "chat",
                "provider": "ollama",
                "model_name": "test",
                "base_url": "http://localhost",
                "api_key_encrypted": "ciphertext",
            },
        }
        bundle = _bundle(
            entity,
            existing_mappings=[
                {
                    **owner_key,
                    "target_uuid": owner_target,
                    "source_digest": "d" * 64,
                    "status": "mapped",
                }
            ],
        )
        async with _factory(tmp_path / "quarantine.db") as factory:
            await _seed_user(factory)
            async with SqlUnitOfWork(factory) as uow:
                result = await E4Importer(uow.require_session()).import_bundle(bundle)
                await uow.commit()
            async with factory() as session:
                config = await session.scalar(select(UserModelConfig).where(UserModelConfig.id == "config-1"))
                migration_entity = await session.scalar(select(E4MigrationEntity))
                batch = await session.scalar(select(E4MigrationBatch))
                assert config is None
                assert migration_entity is not None and migration_entity.status == "excluded"
                assert batch is not None and batch.status == "blocked"
                assert result.quarantined_entities == 1

    _run(scenario())


def test_conflicting_business_row_rolls_back_batch_and_audit(tmp_path):
    async def scenario():
        entity = {
            "source_system": "fastapi_legacy",
            "entity_type": "note",
            "source_id": "note-1",
            "entity_content_digest": "b" * 64,
            "scope": "global",
            "data": {"user_id": "legacy-user", "title": "E4", "content": "body"},
        }
        bundle = _bundle(entity)
        async with _factory(tmp_path / "rollback.db") as factory:
            async with factory() as session:
                session.add(
                    Note(
                        id="note-1",
                        user_id="legacy-user",
                        title="different",
                        content="body",
                    )
                )
                await session.commit()
            async with SqlUnitOfWork(factory) as uow:
                with pytest.raises((E4ImportBlocked, ValueError)):
                    await E4Importer(uow.require_session()).import_bundle(bundle)
            async with factory() as session:
                assert await session.scalar(select(E4MigrationBatch.id)) is None
                assert await session.scalar(select(MigrationMap.id)) is None
                assert await session.scalar(select(E4MigrationEntity.id)) is None

    _run(scenario())


def test_business_fk_failure_is_savepoint_isolated_for_conflict_audit(tmp_path):
    async def scenario():
        missing_session_uuid = "22222222-2222-4222-8222-222222222222"
        entity = {
            "source_system": "fastapi_legacy",
            "entity_type": "message",
            "source_id": "99",
            "entity_content_digest": "b" * 64,
            "scope": "global",
            "data": {
                "role": "assistant",
                "content": "orphaned canonical message",
                "canonical_session_id": missing_session_uuid,
            },
        }
        bundle = _bundle(entity)
        async with _factory(tmp_path / "fk-conflict.db") as factory:
            async with SqlUnitOfWork(factory) as uow:
                with pytest.raises(E4ImportConflict, match="foreign-key"):
                    await E4Importer(uow.require_session()).import_bundle(bundle)
                # The failed business flush was contained by a savepoint, so a
                # caller that elects to retain the evidence can still commit
                # the entity conflict and audit record.
                await uow.commit()

            async with factory() as session:
                migration_entity = await session.scalar(select(E4MigrationEntity))
                assert migration_entity is not None and migration_entity.status == "conflict"
                batch = await session.scalar(select(E4MigrationBatch))
                assert batch is not None and batch.status == "blocked"
                audit = await session.scalar(
                    select(AuditEvent).where(
                        AuditEvent.migration_id == bundle["migration_batch_id"],
                        AuditEvent.error_code == "business_row_conflict",
                    )
                )
                assert audit is not None and audit.correlation_id == CORRELATION_ID

    _run(scenario())


def test_media_only_bundle_is_replayable_and_has_a_zero_entity_identity_report(tmp_path):
    async def scenario():
        payload = b"media-only-e4"
        bundle = {
            "artifact_kind": "e4-business-bundle",
            "schema_version": 1,
            "migration_batch_id": "e4-media-only-001",
            "snapshot_manifest_digest": "a" * 64,
            "schema_revision": "20260905_0008_e4_business_shadow",
            "correlation_id": CORRELATION_ID,
            "entities": [],
            "media": [
                {
                    "source_system": "filesystem",
                    "source_id": "image-1",
                    "content_digest": "b" * 64,
                    "artifact_digest": hashlib.sha256(payload).hexdigest(),
                    "legacy_md5": hashlib.md5(payload).hexdigest(),
                    "scope": "global",
                    "filename": "image.png",
                    "mime_type": "image/png",
                    "content_blob_base64": base64.b64encode(payload).decode("ascii"),
                }
            ],
        }
        parsed = load_business_bundle(bundle)
        report = build_business_dry_run(parsed)
        assert report.blocked is False
        assert report.decisions == ()
        async with _factory(tmp_path / "media-only.db") as factory:
            async with SqlUnitOfWork(factory) as uow:
                first = await E4Importer(uow.require_session()).import_bundle(parsed)
                await uow.commit()
            async with SqlUnitOfWork(factory) as uow:
                replay = await E4Importer(uow.require_session()).import_bundle(parsed)
                await uow.commit()
            async with factory() as session:
                asset = await session.scalar(select(MediaAsset).where(MediaAsset.source_id == "image-1"))
                batch = await session.scalar(select(E4MigrationBatch).where(E4MigrationBatch.migration_batch_id == "e4-media-only-001"))
                assert asset is not None and asset.content_blob == payload
                assert batch is not None and batch.status == "imported"
                assert first.media_imported == 1
                assert replay.media_imported == 1

    _run(scenario())


def test_media_only_bundle_resolves_owner_from_sql_mapping(tmp_path):
    async def scenario():
        payload = b"private-media-e4"
        owner_key = {
            "source_system": "fastapi_legacy",
            "entity_type": "user",
            "source_id": USER_ID,
        }
        bundle = {
            "artifact_kind": "e4-business-bundle",
            "schema_version": 1,
            "migration_batch_id": "e4-media-owner-001",
            "snapshot_manifest_digest": "a" * 64,
            "schema_revision": "20260905_0008_e4_business_shadow",
            "correlation_id": CORRELATION_ID,
            "entities": [],
            "media": [
                {
                    "source_system": "filesystem",
                    "source_id": "private-image-1",
                    "content_digest": "b" * 64,
                    "artifact_digest": hashlib.sha256(payload).hexdigest(),
                    "legacy_md5": hashlib.md5(payload).hexdigest(),
                    "scope": "user",
                    "owner": owner_key,
                    "filename": "private.png",
                    "mime_type": "image/png",
                    "content_blob_base64": base64.b64encode(payload).decode("ascii"),
                }
            ],
        }
        async with _factory(tmp_path / "media-owner.db") as factory:
            await _seed_user(factory)
            async with factory() as session:
                session.add(
                    MigrationMap(
                        migration_batch_id="e3-user-map",
                        source_system=owner_key["source_system"],
                        entity_type=owner_key["entity_type"],
                        source_id=owner_key["source_id"],
                        target_uuid=USER_ID,
                        source_digest="c" * 64,
                        status="mapped",
                    )
                )
                await session.commit()
            async with SqlUnitOfWork(factory) as uow:
                result = await E4Importer(uow.require_session()).import_bundle(bundle)
                await uow.commit()
            async with factory() as session:
                asset = await session.scalar(select(MediaAsset).where(MediaAsset.source_id == "private-image-1"))
                assert result.media_imported == 1
                assert asset is not None and asset.canonical_user_id == USER_ID and asset.scope_id == USER_ID

    _run(scenario())


def test_message_import_orders_session_dependency_and_maps_column_aliases(tmp_path):
    async def scenario():
        session_entity = {
            "source_system": "fastapi_legacy",
            "entity_type": "session",
            "source_id": "session-1",
            "entity_content_digest": "c" * 64,
            "scope": "global",
            "data": {"user_id": "legacy-user", "title": "ordered", "metadata": {"channel": "test"}},
        }
        message_entity = {
            "source_system": "fastapi_legacy",
            "entity_type": "message",
            "source_id": "1",
            "entity_content_digest": "d" * 64,
            "scope": "global",
            "foreign_keys": [
                {"source_system": "fastapi_legacy", "entity_type": "session", "source_id": "session-1"}
            ],
            "data": {"session_id": "session-1", "role": "user", "content": "hello"},
        }
        bundle = {
            "artifact_kind": "e4-business-bundle",
            "schema_version": 1,
            "migration_batch_id": "e4-order-001",
            "snapshot_manifest_digest": "a" * 64,
            "schema_revision": "20260905_0008_e4_business_shadow",
            "correlation_id": CORRELATION_ID,
            "entities": [message_entity, session_entity],
            "media": [],
        }
        async with _factory(tmp_path / "order.db") as factory:
            async with SqlUnitOfWork(factory) as uow:
                result = await E4Importer(uow.require_session()).import_bundle(bundle)
                await uow.commit()
            async with factory() as session:
                imported_session = await session.scalar(select(ChatSession).where(ChatSession.id == "session-1"))
                imported_message = await session.scalar(select(ChatMessage).where(ChatMessage.id == 1))
                assert result.imported_entities == 2
                assert imported_session is not None and imported_session.metadata_ == {"channel": "test"}
                assert imported_message is not None
                assert imported_message.canonical_session_id == imported_session.canonical_id

    _run(scenario())


def test_knowledge_document_bundle_stores_original_bytes_in_sql(tmp_path):
    async def scenario():
        payload = b"document bytes"
        bundle = _bundle(
            {
                "source_system": "fastapi_legacy",
                "entity_type": "knowledge_document",
                "source_id": "doc-1",
                "entity_content_digest": "e" * 64,
                "artifact_digest": hashlib.sha256(payload).hexdigest(),
                "legacy_md5": hashlib.md5(payload).hexdigest(),
                "scope": "global",
                "content_blob_base64": base64.b64encode(payload).decode("ascii"),
                "data": {
                    "user_id": "legacy-user",
                    "md5": hashlib.md5(payload).hexdigest(),
                    "filename": "doc.txt",
                    "original_filename": "doc.txt",
                    "file_ext": "txt",
                    "mime_type": "text/plain",
                    "file_size": len(payload),
                },
            }
        )
        async with _factory(tmp_path / "document.db") as factory:
            async with SqlUnitOfWork(factory) as uow:
                result = await E4Importer(uow.require_session()).import_bundle(bundle)
                await uow.commit()
            async with factory() as session:
                document = await session.scalar(select(KnowledgeSourceDocument).where(KnowledgeSourceDocument.id == "doc-1"))
                assert result.imported_entities == 1
                assert document is not None and document.content_blob == payload
                assert document.artifact_digest == hashlib.sha256(payload).hexdigest()

    _run(scenario())


def test_finalize_rejects_a_partial_bundle_without_committing_imported_status(tmp_path):
    async def scenario():
        entities = [
            {
                "source_system": "fastapi_legacy",
                "entity_type": "note",
                "source_id": source_id,
                "entity_content_digest": digest,
                "scope": "global",
                "data": {"user_id": "legacy-user", "title": source_id, "content": "body"},
            }
            for source_id, digest in (("note-a", "a" * 64), ("note-b", "b" * 64))
        ]
        bundle = {
            "artifact_kind": "e4-business-bundle",
            "schema_version": 1,
            "migration_batch_id": "e4-partial-finalize-001",
            "snapshot_manifest_digest": "c" * 64,
            "schema_revision": "20260905_0008_e4_business_shadow",
            "correlation_id": CORRELATION_ID,
            "entities": entities,
            "media": [],
        }
        async with _factory(tmp_path / "partial-finalize.db") as factory:
            async with SqlUnitOfWork(factory) as uow:
                repository = E4MigrationRepository(uow.require_session())
                batch = await repository.create_batch(
                    migration_batch_id=bundle["migration_batch_id"],
                    snapshot_manifest_digest=bundle["snapshot_manifest_digest"],
                    schema_revision=bundle["schema_revision"],
                    correlation_id=bundle["correlation_id"],
                )
                await repository.set_batch_status(batch_id=batch.id, to_status="validated", expected_status="planned")
                await repository.set_batch_status(batch_id=batch.id, to_status="importing", expected_status="validated")
                await uow.commit()

            async with SqlUnitOfWork(factory) as uow:
                with pytest.raises(E4ImportBlocked, match="every bundle entity"):
                    await E4Importer(uow.require_session()).import_bundle(
                        bundle,
                        entity_offset=1,
                        entity_limit=1,
                        finalize=True,
                    )

            async with factory() as session:
                persisted_batch = await session.scalar(select(E4MigrationBatch))
                assert persisted_batch is not None and persisted_batch.status == "importing"
                assert await session.scalar(select(E4MigrationEntity.id)) is None
                assert await session.scalar(select(Note.id)) is None

    _run(scenario())


def test_two_chunk_import_finalizes_only_after_all_chunks_are_committed(tmp_path):
    async def scenario():
        entities = [
            {
                "source_system": "fastapi_legacy",
                "entity_type": "note",
                "source_id": source_id,
                "entity_content_digest": digest,
                "scope": "global",
                "data": {"user_id": "legacy-user", "title": source_id, "content": "body"},
            }
            for source_id, digest in (("note-first", "e" * 64), ("note-last", "f" * 64))
        ]
        bundle = {
            "artifact_kind": "e4-business-bundle",
            "schema_version": 1,
            "migration_batch_id": "e4-two-chunk-001",
            "snapshot_manifest_digest": "1" * 64,
            "schema_revision": "20260905_0008_e4_business_shadow",
            "correlation_id": CORRELATION_ID,
            "entities": entities,
            "media": [],
        }
        async with _factory(tmp_path / "two-chunk.db") as factory:
            async with SqlUnitOfWork(factory) as uow:
                first = await E4Importer(uow.require_session()).import_bundle(
                    bundle,
                    entity_offset=0,
                    entity_limit=1,
                    finalize=False,
                )
                await uow.commit()
            assert first.imported_entities == 1

            async with SqlUnitOfWork(factory) as uow:
                last = await E4Importer(uow.require_session()).import_bundle(
                    bundle,
                    entity_offset=1,
                    entity_limit=1,
                    finalize=True,
                )
                await uow.commit()
            async with factory() as session:
                batch = await session.scalar(
                    select(E4MigrationBatch).where(E4MigrationBatch.migration_batch_id == "e4-two-chunk-001")
                )
                assert last.imported_entities == 1
                assert batch is not None and batch.status == "imported"
                assert await session.scalar(select(Note.id).where(Note.id == "note-first")) == "note-first"
                assert await session.scalar(select(Note.id).where(Note.id == "note-last")) == "note-last"

    _run(scenario())


def test_import_result_marks_quarantine_as_blocked():
    result = E4ImportResult(
        migration_batch_id="e4-result-001",
        correlation_id=CORRELATION_ID,
        dry_run=False,
        total_entities=1,
        imported_entities=0,
        skipped_entities=0,
        quarantined_entities=1,
        media_imported=0,
        blocked_entities=1,
        report_sha256="d" * 64,
    )
    assert result.blocked is True
    assert result.as_dict()["blocked"] is True
