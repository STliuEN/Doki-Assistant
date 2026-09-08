from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from importlib import import_module

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.chat_history import Base, ChatMessage, ChatSession
from app.models.identity_domain import User


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
            lambda sync: Base.metadata.create_all(
                sync,
                tables=(User.__table__, ChatSession.__table__, ChatMessage.__table__),
            )
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def test_session_manager_mutations_use_transaction_helper(monkeypatch, tmp_path) -> None:
    async def scenario():
        manager_module = import_module("app.services.database_session_manager")

        async with _session_factory(tmp_path / "session-manager.db") as factory:
            calls = []
            original_persist = manager_module.persist_service_write

            async def tracked_persist(session, callback=None):
                calls.append((session, callback))
                await original_persist(session, callback=callback)

            monkeypatch.setattr(manager_module, "AsyncSessionLocal", factory)
            monkeypatch.setattr(manager_module, "persist_service_write", tracked_persist)
            manager = manager_module.DatabaseSessionManager()

            await manager.add_message("session-1", "legacy-user", "hello", "world")
            messages = await manager.get_messages("session-1", "legacy-user")
            assistant_id = next(item["id"] for item in messages if item["role"] == "assistant")
            await manager.update_session_summary("session-1", "legacy-user", "summary", assistant_id, 3)
            appended = await manager.append_assistant_message("session-1", "legacy-user", "follow-up")
            await manager.update_message_content("session-1", "legacy-user", appended["id"], "updated")
            await manager.delete_message("session-1", "legacy-user", appended["id"])
            await manager.clear_session("session-1", "legacy-user")

            assert len(calls) == 7
            async with factory() as session:
                assert await session.scalar(select(ChatSession).where(ChatSession.id == "session-1")) is None
                assert await session.scalar(select(ChatMessage).where(ChatMessage.session_id == "session-1")) is None

    _run(scenario())
