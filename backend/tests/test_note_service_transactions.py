from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.transaction_context import register_post_commit
from app.db.uow import SqlUnitOfWork
from app.models.chat_history import Base
from app.models.identity_domain import User
from app.models.note import Note
from app.schemas.models import NoteCreate
from app.services.note_service import NoteService


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
            lambda sync: Base.metadata.create_all(sync, tables=(User.__table__, Note.__table__))
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _service(events: list[tuple[str, str]]) -> NoteService:
    service = object.__new__(NoteService)

    async def add_vector(_db, _user_id, note_id, _title, _content):
        events.append(("add", note_id))

    service._add_note_vector = add_vector
    return service


def test_note_projection_runs_only_after_uow_commit(tmp_path) -> None:
    async def scenario():
        events: list[tuple[str, str]] = []
        service = _service(events)
        async with _session_factory(tmp_path / "note-commit.db") as factory:
            async with SqlUnitOfWork(factory) as uow:
                response = await service.create_note(
                    uow.require_session(),
                    "legacy-user",
                    NoteCreate(title="transactional", content="body", tags=[]),
                )
                assert events == []
                await uow.commit()

            assert events == [("add", response.id)]

    _run(scenario())


def test_note_projection_is_discarded_when_uow_rolls_back(tmp_path) -> None:
    async def scenario():
        events: list[tuple[str, str]] = []
        service = _service(events)
        async with _session_factory(tmp_path / "note-rollback.db") as factory:
            async with SqlUnitOfWork(factory) as uow:
                response = await service.create_note(
                    uow.require_session(),
                    "legacy-user",
                    NoteCreate(title="rolled back", content="body", tags=[]),
                )
                assert events == []
                assert response.id

            assert events == []
            async with factory() as session:
                assert await session.scalar(select(Note).where(Note.id == response.id)) is None

    _run(scenario())


def test_post_commit_cancellation_does_not_rollback_durable_sql(tmp_path) -> None:
    async def scenario():
        async with _session_factory(tmp_path / "post-commit-cancel.db") as factory:
            async with SqlUnitOfWork(factory) as uow:
                note = Note(id="cancelled-callback", user_id="legacy-user", title="durable", content="body")
                uow.require_session().add(note)

                async def cancelled_callback():
                    raise asyncio.CancelledError()

                register_post_commit(uow.require_session(), cancelled_callback)
                await uow.commit()

            async with factory() as session:
                persisted = await session.get(Note, "cancelled-callback")
                assert persisted is not None and persisted.title == "durable"

    _run(scenario())
