from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import DateTime, event, func, select, text, update
from sqlalchemy.dialects import mysql, sqlite
from sqlalchemy.dialects.mysql import LONGBLOB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.db.business_authority import BusinessSession, BusinessWriteError, _normalise_datetime, business_digest, mutate_rows
from app.db.transaction_context import persist_service_write
from app.db.uow import SqlUnitOfWork
from app.jobs.business_handlers import business_handlers
from app.jobs.repository import JobRepository
from app.jobs.runner import SqlJobRunner
from app.models.chat_history import Base, ChatMessage, ChatSession
from app.models.identity_domain import User
from app.models.job_domain import AuditEvent, Job, JobAttempt
from app.models.knowledge_document import KnowledgeSourceDocument
from app.models.memory_item import MemoryItem
from app.models.note import Note
from app.models.skill_domain import Skill, SkillRegistryEvent, SkillRunBinding

OWNER = "11111111-2222-4333-8444-555555555555"
OTHER = "22222222-2222-4333-8444-555555555555"


@compiles(LONGBLOB, "sqlite")
def compile_blob(_type, _compiler, **_kwargs):
    return "BLOB"


@asynccontextmanager
async def database(path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")

    @event.listens_for(engine.sync_engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    tables = (User, ChatSession, ChatMessage, Note, MemoryItem, KnowledgeSourceDocument, SkillRunBinding, Job, JobAttempt, AuditEvent)
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[model.__table__ for model in tables]))
    factory = async_sessionmaker(engine, expire_on_commit=False, sync_session_class=BusinessSession)
    try:
        async with factory() as session:
            for owner in (OWNER, OTHER):
                session.add(
                    User(
                        id=owner,
                        username=owner,
                        email_display=owner + "@test.invalid",
                        email_normalized=owner + "@test.invalid",
                        password_hash="fixture",
                    )
                )
            await session.commit()
        yield factory
    finally:
        await engine.dispose()


def note(**values):
    return Note(id=str(uuid4()), user_id=OWNER, title="fixture", content="private content", **values)


def test_registry_acknowledgement_uses_guarded_rows_and_is_idempotent(tmp_path):
    from app.skills.registry import SkillRegistrySnapshot
    from app.skills.service import SkillService

    async def scenario():
        async with database(tmp_path / "registry-events.db") as factory:
            async with factory.kw["bind"].begin() as connection:
                await connection.run_sync(
                    lambda sync: Base.metadata.create_all(sync, tables=[Skill.__table__, SkillRegistryEvent.__table__])
                )
            service = SkillService()
            service.reconcile_registry = AsyncMock(return_value=SkillRegistrySnapshot(revision=1, skills=()))
            async with factory() as session:
                current = SkillRegistryEvent(id=str(uuid4()), revision=1, event_type="fixture", payload={})
                future = SkillRegistryEvent(id=str(uuid4()), revision=2, event_type="fixture", payload={})
                session.add_all([current, future])
                await session.commit()
                await service.consume_registry_events(session)
                assert current.processed_at is not None
                assert future.processed_at is None
                query = select(func.count()).select_from(AuditEvent).where(
                    AuditEvent.target_type == "skill_registry_events", AuditEvent.action == "business.updated"
                )
                assert await session.scalar(query) == 1
                await service.consume_registry_events(session)
                assert await session.scalar(query) == 1

    asyncio.run(scenario())


def test_business_audit_jobs_commit_and_rollback_together(tmp_path):
    async def scenario():
        async with database(tmp_path / "atomic.db") as factory:
            callbacks = []
            async with SqlUnitOfWork(factory) as uow:
                session = uow.require_session()
                row = note()
                session.add(row)
                await persist_service_write(session, callback=lambda: callbacks.append("legacy"))
                assert row.canonical_id == row.id and row.canonical_user_id == OWNER
                assert await session.scalar(select(func.count()).select_from(Job)) == 2
            async with factory() as session:
                for model in (Note, AuditEvent, Job):
                    assert await session.scalar(select(func.count()).select_from(model)) == 0
            async with SqlUnitOfWork(factory) as uow:
                row = note()
                uow.require_session().add(row)
                await uow.commit()
            async with factory() as session:
                saved = await session.get(Note, row.id)
                assert saved.content_digest == business_digest(saved)
                assert await session.scalar(select(func.count()).select_from(Job)) == 2
                audits = (await session.scalars(select(AuditEvent).where(AuditEvent.action == "business.created"))).all()
                assert len(audits) == 1 and "private content" not in str(audits[0].after_json)
            assert not callbacks
    asyncio.run(scenario())


def test_actor_owner_and_immutable_identity_fail_closed(tmp_path):
    async def scenario():
        async with database(tmp_path / "owners.db") as factory:
            async with factory() as session:
                session.info["e4_actor_id"] = OTHER
                session.add(note())
                with pytest.raises(BusinessWriteError):
                    await session.flush()
                await session.rollback()
            async with factory() as session:
                row = note()
                session.add(row)
                await session.commit()
                row.canonical_user_id = OTHER
                with pytest.raises(BusinessWriteError):
                    await session.flush()
                await session.rollback()
            async with factory() as session:
                row = Note(id=str(uuid4()), user_id="legacy", canonical_user_id=OWNER, title="bad", content="bad")
                session.add(row)
                with pytest.raises(BusinessWriteError):
                    await session.flush()
    asyncio.run(scenario())


def test_parent_shadow_and_bulk_write_bypass(tmp_path):
    async def scenario():
        async with database(tmp_path / "parents.db") as factory:
            async with factory() as session:
                parent = ChatSession(id="legacy-compatible-session", user_id=OWNER)
                child = ChatMessage(session_id=parent.id, role="user", content="hello")
                session.add_all([child, parent])
                await session.commit()
                assert child.canonical_session_id == parent.canonical_id
                assert child.content_digest == business_digest(child)
                for statement in (update(ChatSession).values(title="bypass"), text("DELETE FROM chat_sessions")):
                    with pytest.raises(BusinessWriteError):
                        await session.execute(statement)
                child.session_id = "another-session"
                with pytest.raises(BusinessWriteError):
                    await session.flush()
    asyncio.run(scenario())


def test_mutate_rows_tracks_each_delete_and_job(tmp_path):
    async def scenario():
        async with database(tmp_path / "delete.db") as factory:
            async with factory() as session:
                session.add_all([note(tags=[], category="life"), note(tags=[], category="life")])
                await session.commit()
                assert await mutate_rows(session, Note, Note.user_id == OWNER, remove=True) == 2
                await session.commit()
                assert await session.scalar(select(func.count()).select_from(Note)) == 0
                assert await session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action.like("business.%"))) == 4
                assert await session.scalar(select(func.count()).select_from(Job)) == 4
    asyncio.run(scenario())


def test_enrichment_result_and_business_writes_are_single_fenced_commit(tmp_path):
    async def scenario():
        async with database(tmp_path / "enrich.db") as factory:
            async with factory() as session:
                row = note()
                session.add(row)
                await session.commit()
            calls = []
            async def tagger(content):
                calls.append(content)
                return {"tags": ["test"], "category": "life"}
            runner = SqlJobRunner(factory, registry=business_handlers(factory, tagger=tagger), claim_registered_only=True)
            assert await runner.run_once()
            assert not await runner.run_once()
            assert runner.status()["succeeded_count"] == 1 and runner.status()["rejected_count"] == 0
            async with factory() as session:
                saved = await session.get(Note, row.id)
                assert saved.tags == ["test"]
                assert await session.scalar(select(func.count()).select_from(MemoryItem)) == 1
                jobs = (await session.scalars(select(Job))).all()
                assert {job.job_type: job.status for job in jobs} == {"e4.note.enrich": "succeeded", "e4.note.project": "queued"}
                assert await session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "job.fenced_rejected")) == 0
            assert calls == ["private content"]
    asyncio.run(scenario())


@pytest.mark.parametrize(
    ('response_content', 'failure', 'error_code'),
    [
        ('not JSON', None, 'invalid_tag_result'),
        ('[]', None, 'invalid_tag_result'),
        ('{}', None, 'invalid_tag_result'),
        ('{"tags": "invalid", "category": "life"}', None, 'invalid_tag_result'),
        ('{"tags": [1], "category": "life"}', None, 'invalid_tag_result'),
        ('{"tags": [], "category": "unknown"}', None, 'invalid_tag_result'),
        ('{"tags": [], "category": null}', None, 'invalid_tag_result'),
        ([], None, 'invalid_tag_result'),
        (None, TimeoutError('sensitive provider detail'), 'model_timeout'),
        (None, httpx.ReadTimeout('sensitive provider detail'), 'model_timeout'),
        (None, httpx.ConnectError('sensitive provider detail'), 'model_connection_error'),
    ],
)
def test_model_failures_retry_then_dead_letter_without_business_mutation(tmp_path, monkeypatch, response_content, failure, error_code):
    from app.core.background_init import init_manager

    model = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content=response_content), side_effect=failure))
    monkeypatch.setattr(init_manager, 'chat_model', model)
    clock = datetime.now(UTC) + timedelta(hours=1)

    async def database_now(_repository):
        return clock

    monkeypatch.setattr(JobRepository, '_database_now', database_now)

    async def scenario():
        nonlocal clock
        async with database(tmp_path / 'model-failures.db') as factory:
            async with factory() as session:
                row = note()
                session.add(row)
                await session.commit()
                original_digest = row.content_digest
                original_audits = await session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action.like('business.%')))
            runner = SqlJobRunner(factory, registry=business_handlers(factory), claim_registered_only=True)
            for attempt_number in range(1, 6):
                assert await runner.run_once()
                expected_status = 'dead_letter' if attempt_number == 5 else 'retry_wait'
                async with factory() as session:
                    saved = await session.get(Note, row.id)
                    job = await session.scalar(select(Job).where(Job.job_type == 'e4.note.enrich'))
                    attempt = await session.scalar(select(JobAttempt).where(JobAttempt.job_id == job.id, JobAttempt.attempt_number == attempt_number))
                    assert (job.status, job.error_code, job.attempt_count) == (expected_status, error_code, attempt_number)
                    assert job.result_json is None
                    assert (attempt.outcome, attempt.error_code) == (expected_status, error_code)
                    assert 'sensitive provider detail' not in job.error_detail
                    assert saved.tags is None and saved.category is None and saved.content_digest == original_digest
                    assert await session.scalar(select(func.count()).select_from(MemoryItem)) == 0
                    business_audits = await session.scalar(
                        select(func.count()).select_from(AuditEvent).where(AuditEvent.action.like('business.%'))
                    )
                    assert business_audits == original_audits
                    error_audits = await session.scalar(
                        select(func.count()).select_from(
                            AuditEvent,
                        ).where(AuditEvent.job_id == job.id, AuditEvent.error_code == error_code)
                    )
                    assert error_audits == attempt_number
                clock += timedelta(hours=1)
            assert not await runner.run_once()
            assert model.ainvoke.await_count == 5

    asyncio.run(scenario())


def test_enrichment_stale_lease_cannot_change_business_rows(tmp_path):
    async def scenario():
        async with database(tmp_path / "fenced.db") as factory:
            async with factory() as session:
                row = note()
                session.add(row)
                await session.commit()

            async def tagger(_content):
                async with factory() as session:
                    await session.execute(update(Job).where(Job.job_type == "e4.note.enrich").values(fencing_token=99))
                    await session.commit()
                return {"tags": ["invalid"], "category": "life"}

            runner = SqlJobRunner(factory, registry=business_handlers(factory, tagger=tagger), claim_registered_only=True)
            await runner.run_once()
            async with factory() as session:
                saved = await session.get(Note, row.id)
                assert saved.tags is None and saved.category is None
                assert await session.scalar(select(func.count()).select_from(MemoryItem)) == 0
    asyncio.run(scenario())


def test_sql_upload_works_without_chroma_and_rolls_back_on_invalid_batch(tmp_path, monkeypatch):
    import io

    from fastapi import HTTPException, UploadFile

    from app.rag.vector_store import VectorStoreService
    from app.router.knowledge_service import KnowledgeService

    def forbidden(*_args, **_kwargs):
        raise AssertionError("SQL upload must not create a projection")

    monkeypatch.setattr(VectorStoreService, "__new__", forbidden)

    async def scenario():
        async with database(tmp_path / "upload.db") as factory:
            service = KnowledgeService()
            async with SqlUnitOfWork(factory) as uow:
                from app.models.embedding_config import UserEmbeddingConfig
                async with uow.require_session().bind.begin() as connection:
                    await connection.run_sync(lambda sync: UserEmbeddingConfig.__table__.create(sync))
                result = await service.accept_sql_uploads([UploadFile(io.BytesIO(b"hello"), filename="test.txt")], OWNER, uow.require_session())
                assert result["projection_status"] == "queued" and len(result["job_ids"]) == 1
                await uow.commit()
            with pytest.raises(HTTPException):
                async with SqlUnitOfWork(factory) as uow:
                    await service.accept_sql_uploads(
                        [UploadFile(io.BytesIO(b"other"), filename="other.txt"), UploadFile(io.BytesIO(b"bad"), filename="bad.exe")],
                        OWNER,
                        uow.require_session(),
                    )
                    await uow.commit()
            async with factory() as session:
                assert await session.scalar(select(func.count()).select_from(KnowledgeSourceDocument)) == 1
                assert await session.scalar(select(func.count()).select_from(Job)) == 1
    asyncio.run(scenario())


def test_mysql_timestamp_precision_matches_written_digest():
    value = datetime(2026, 9, 7, 12, 30, 0, 987654)
    assert _normalise_datetime(value, DateTime(), mysql.dialect()).microsecond == 0
    assert _normalise_datetime(value, mysql.DATETIME(fsp=3), mysql.dialect()).microsecond == 987000
    assert _normalise_datetime(value, mysql.DATETIME(fsp=6), mysql.dialect()) == value
    assert _normalise_datetime(value, DateTime(), sqlite.dialect()) == value
    aware = value.replace(tzinfo=timezone(timedelta(hours=8)))
    assert _normalise_datetime(aware, DateTime(), mysql.dialect()) == aware.astimezone(UTC).replace(tzinfo=None, microsecond=0)


def test_chat_pair_failure_rolls_back_parent_and_audit(tmp_path, monkeypatch):
    from importlib import import_module
    database_session_manager = import_module("app.services.database_session_manager")

    async def scenario():
        async with database(tmp_path / "pair.db") as factory:
            monkeypatch.setattr(database_session_manager, "AsyncSessionLocal", factory)
            manager = database_session_manager.DatabaseSessionManager()
            from sqlalchemy.exc import IntegrityError
            with pytest.raises(IntegrityError):
                await manager.add_message("failed-parent", OWNER, "hello", None)
            async with factory() as session:
                for model in (ChatSession, ChatMessage, AuditEvent):
                    assert await session.scalar(select(func.count()).select_from(model)) == 0
    asyncio.run(scenario())


def test_skill_run_binding_has_canonical_parent_and_owner(tmp_path):
    async def scenario():
        async with database(tmp_path / "binding.db") as factory:
            async with factory() as session:
                parent = ChatSession(id="binding-parent", user_id=OWNER)
                binding = SkillRunBinding(run_id=str(uuid4()), session_id=parent.id, user_id=OWNER, registry_revision=1)
                session.add_all([parent, binding])
                await session.commit()
                assert binding.canonical_user_id == OWNER and binding.canonical_session_id == parent.canonical_id
                assert binding.skill_bindings == [] and binding.effective_grants == {}
                assert await session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.target_type == "skill_run_bindings")) == 1
    asyncio.run(scenario())


def test_commit_failure_cannot_return_success_response(tmp_path):
    from fastapi import Depends, FastAPI
    from httpx import ASGITransport, AsyncClient

    async def scenario():
        async with database(tmp_path / "response.db") as factory:
            async def transaction():
                async with SqlUnitOfWork(factory) as uow:
                    yield uow.require_session()
                    await uow.commit()
            app = FastAPI()
            @app.post("/write")
            async def write(session=Depends(transaction, scope="function")):
                session.add(Note(id=str(uuid4()), user_id="legacy-invalid", title="invalid", content="not committed"))
                return {"ok": True}
            async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as client:
                assert (await client.post("/write")).status_code == 500
            async with factory() as session:
                assert await session.scalar(select(func.count()).select_from(Note)) == 0
    asyncio.run(scenario())
