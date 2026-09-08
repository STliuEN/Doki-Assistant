from __future__ import annotations

import asyncio
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.business_owner import business_owner_matches
from app.models.chat_history import Base
from app.models.identity_domain import User
from app.models.note import Note
from app.services.note_service import NoteService

OWNER = "11111111-2222-4333-8444-555555555555"
OTHER = "22222222-2222-4333-8444-555555555555"


def test_migrated_notes_use_canonical_owner_without_legacy_cross_user_access(tmp_path):
    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'owners.db'}")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=(User.__table__, Note.__table__)))
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as session:
                session.add_all([
                    Note(id="migrated", user_id="legacy-user", canonical_user_id=OWNER, title="owned", content="body"),
                    Note(id="other", user_id=OWNER, canonical_user_id=OTHER, title="not-owned", content="body"),
                    Note(id="new", user_id=OWNER, title="new", content="body"),
                    Note(id="legacy", user_id="legacy-user", title="unmigrated", content="body"),
                ])
                await session.commit()
                service = object.__new__(NoteService)
                notes, count = await service.list_notes(session, OWNER)
                assert count == 2
                assert {note.id for note in notes} == {"migrated", "new"}
                assert (await service.get_note(session, "migrated", OWNER)).id == "migrated"
                assert await service.get_note(session, "other", OWNER) is None
                assert await service.get_note(session, "migrated", "legacy-user") is None
                assert (await service.get_note(session, "legacy", "legacy-user")).id == "legacy"
        finally:
            await engine.dispose()
    asyncio.run(scenario())


def test_in_memory_session_owner_checks_prefer_canonical_identity():
    row = SimpleNamespace(canonical_user_id=OWNER, user_id="legacy-user")
    assert business_owner_matches(row, OWNER)
    assert not business_owner_matches(row, "legacy-user")
    assert not business_owner_matches(row, OTHER)
    assert business_owner_matches(SimpleNamespace(canonical_user_id=None, user_id=OWNER), OWNER)
