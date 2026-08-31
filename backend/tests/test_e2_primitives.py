from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.uow import SqlUnitOfWork
from app.e2 import (
    E2PrimitiveConflictError,
    E2PrimitiveValidationError,
    SyntheticAuthRepository,
    SyntheticMigrationMapRepository,
    SyntheticRagRepository,
    SyntheticSkillRepository,
)
from app.models.chat_history import Base
from app.models.identity_domain import (
    AuthSession,
    MigrationMap,
    RefreshToken,
    Role,
    RoleBinding,
    TokenRevocation,
    User,
)
from app.models.job_domain import AuditEvent, Job, JobAttempt
from app.models.projection_domain import RagGeneration, RagGenerationHead, SkillPackage, SkillPackageUpload

E2_TABLES = (
    User.__table__,
    AuthSession.__table__,
    RefreshToken.__table__,
    TokenRevocation.__table__,
    Role.__table__,
    RoleBinding.__table__,
    MigrationMap.__table__,
    Job.__table__,
    JobAttempt.__table__,
    AuditEvent.__table__,
    RagGeneration.__table__,
    RagGenerationHead.__table__,
    SkillPackage.__table__,
    SkillPackageUpload.__table__,
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
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=E2_TABLES))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


NOW = datetime.now(UTC)
UUID_A = "11111111-1111-4111-8111-111111111111"
UUID_B = "22222222-2222-4222-8222-222222222222"
UUID_C = "33333333-3333-4333-8333-333333333333"
UUID_D = "44444444-4444-4444-8444-444444444444"


def test_auth_primitives_are_transactional_and_rotate_refresh_tokens(tmp_path) -> None:
    async def scenario():
        async with _session_factory(tmp_path / "auth.db") as factory:
            async with SqlUnitOfWork(factory) as uow:
                repository = SyntheticAuthRepository(uow.require_session())
                user = await repository.create_user(
                    user_id=UUID_A,
                    email_normalized="synthetic@example.test",
                    username="synthetic",
                )
                session = await repository.create_session(
                    session_id=UUID_B,
                    user_id=user.id,
                    expires_at=NOW + timedelta(days=1),
                )
                parent = await repository.issue_refresh_token(
                    token_id=UUID_C,
                    session_id=session.id,
                    token_digest="a" * 64,
                    jti_digest="b" * 64,
                    expires_at=NOW + timedelta(days=1),
                )
                child = await repository.rotate_refresh_token(
                    parent_token_id=parent.id,
                    token_id=UUID_D,
                    token_digest="c" * 64,
                    jti_digest="d" * 64,
                    expires_at=NOW + timedelta(days=1),
                )
                await repository.revoke(
                    scope_type="session",
                    scope_key=session.id,
                    session_id=session.id,
                    reason="synthetic test",
                )
                await uow.commit()

            async with factory() as read_session:
                persisted_parent = await read_session.get(RefreshToken, parent.id)
                persisted_child = await read_session.get(RefreshToken, child.id)
                assert persisted_parent is not None and persisted_parent.status == "consumed"
                assert persisted_parent.replaced_by_token_id == child.id
                assert persisted_child is not None and persisted_child.parent_token_id == parent.id
                assert await read_session.scalar(select(TokenRevocation.scope_key)) == session.id

            async with SqlUnitOfWork(factory) as uow:
                repository = SyntheticAuthRepository(uow.require_session())
                with pytest.raises(E2PrimitiveConflictError):
                    await repository.create_user(
                        email_normalized="synthetic@example.test",
                        username="duplicate",
                    )

    _run(scenario())


def test_auth_primitives_reject_bad_scope_and_roll_back(tmp_path) -> None:
    async def scenario():
        async with _session_factory(tmp_path / "auth-rollback.db") as factory:
            async with SqlUnitOfWork(factory) as uow:
                repository = SyntheticAuthRepository(uow.require_session())
                with pytest.raises(E2PrimitiveValidationError):
                    await repository.revoke(scope_type="token", scope_key="token", reason="bad")
                await repository.create_user(
                    email_normalized="rolled-back@example.test",
                    username="rolled-back",
                )

            async with factory() as read_session:
                assert await read_session.scalar(select(User.id)) is None
                assert await read_session.scalar(select(TokenRevocation.id)) is None

    _run(scenario())


def test_rag_generation_head_uses_revision_cas_and_retires_previous_generation(tmp_path) -> None:
    async def scenario():
        async with _session_factory(tmp_path / "rag.db") as factory:
            async with SqlUnitOfWork(factory) as uow:
                repository = SyntheticRagRepository(uow.require_session())
                head = await repository.ensure_head(
                    owner_scope_type="synthetic",
                    owner_scope_id="rag-test",
                    index_kind="lexical",
                    head_id=UUID_A,
                )
                first = await repository.create_generation(
                    owner_scope_type="synthetic",
                    owner_scope_id="rag-test",
                    index_kind="lexical",
                    embedding_fingerprint="1" * 64,
                    generation=1,
                    config={"schema_version": 1, "model": "synthetic"},
                    config_schema_version=1,
                    source_revision=1,
                    generation_id=UUID_B,
                )
                await repository.mark_ready(generation_id=first.id)
                await repository.stage_generation(head_id=head.id, generation_id=first.id, expected_revision=1)
                with pytest.raises(E2PrimitiveConflictError):
                    await repository.activate_generation(head_id=head.id, generation_id=first.id, expected_revision=1)
                head = await uow.require_session().get(RagGenerationHead, head.id)
                await repository.activate_generation(head_id=head.id, generation_id=first.id, expected_revision=2)
                second = await repository.create_generation(
                    owner_scope_type="synthetic",
                    owner_scope_id="rag-test",
                    index_kind="lexical",
                    embedding_fingerprint="2" * 64,
                    generation=2,
                    config={"schema_version": 1, "model": "synthetic-v2"},
                    config_schema_version=1,
                    source_revision=2,
                    generation_id=UUID_C,
                )
                await repository.mark_ready(generation_id=second.id)
                await repository.stage_generation(head_id=head.id, generation_id=second.id, expected_revision=3)
                await repository.activate_generation(head_id=head.id, generation_id=second.id, expected_revision=4)
                await uow.commit()

            async with factory() as read_session:
                persisted_first = await read_session.get(RagGeneration, first.id)
                persisted_second = await read_session.get(RagGeneration, second.id)
                persisted_head = await read_session.get(RagGenerationHead, head.id)
                assert persisted_first is not None and persisted_first.status == "retired"
                assert persisted_second is not None and persisted_second.status == "ready"
                assert persisted_head is not None and persisted_head.active_generation_id == second.id

    _run(scenario())


def test_skill_package_and_upload_digests_are_idempotent(tmp_path) -> None:
    async def scenario():
        archive = b"synthetic archive"
        package_digest = "e" * 64
        async with _session_factory(tmp_path / "skill.db") as factory:
            async with SqlUnitOfWork(factory) as uow:
                repository = SyntheticSkillRepository(uow.require_session())
                package = await repository.store_package(
                    package_id=UUID_A,
                    archive=archive,
                    package_digest=package_digest,
                    manifest={"schema_version": 1, "name": "synthetic"},
                    manifest_schema_version=1,
                )
                same_package = await repository.store_package(
                    archive=archive,
                    package_digest=package_digest,
                    manifest={"schema_version": 1, "name": "synthetic"},
                    manifest_schema_version=1,
                )
                upload = await repository.record_upload(package_id=package.id, raw_archive=archive)
                same_upload = await repository.record_upload(package_id=package.id, raw_archive=archive)
                assert same_package.id == package.id
                assert same_upload.id == upload.id
                with pytest.raises(E2PrimitiveValidationError):
                    await repository.store_package(
                        archive=archive,
                        package_digest="f" * 64,
                        canonical_archive_digest="0" * 64,
                        manifest={"schema_version": 1, "name": "bad"},
                        manifest_schema_version=1,
                    )
                await uow.commit()

            async with factory() as read_session:
                assert await read_session.scalar(select(SkillPackage.id)) == package.id
                assert await read_session.scalar(select(SkillPackageUpload.id)) == upload.id

    _run(scenario())


def test_migration_map_replay_is_idempotent_but_digest_conflict_is_rejected(tmp_path) -> None:
    async def scenario():
        async with _session_factory(tmp_path / "migration.db") as factory:
            async with SqlUnitOfWork(factory) as uow:
                repository = SyntheticMigrationMapRepository(uow.require_session())
                first = await repository.map_source(
                    mapping_id=UUID_A,
                    migration_batch_id="synthetic-batch",
                    source_system="legacy",
                    entity_type="user",
                    source_id="legacy-1",
                    target_uuid=UUID_B,
                    source_digest="a" * 64,
                )
                replay = await repository.map_source(
                    migration_batch_id="synthetic-batch-2",
                    source_system="legacy",
                    entity_type="user",
                    source_id="legacy-1",
                    target_uuid=UUID_B,
                    source_digest="a" * 64,
                )
                assert replay.id == first.id
                with pytest.raises(E2PrimitiveConflictError):
                    await repository.map_source(
                        migration_batch_id="synthetic-batch",
                        source_system="legacy",
                        entity_type="user",
                        source_id="legacy-1",
                        target_uuid=UUID_C,
                        source_digest="b" * 64,
                    )
                await uow.commit()

            async with factory() as read_session:
                assert await read_session.scalar(select(MigrationMap.id)) == UUID_A

    _run(scenario())
