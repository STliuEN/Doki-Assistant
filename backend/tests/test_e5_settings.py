import asyncio

import pytest
from sqlalchemy import func, select

from app.db.business_authority import BusinessWriteError
from app.db.transaction_context import mark_managed_transaction
from app.models.embedding_config import UserEmbeddingConfig
from app.models.job_domain import Job
from app.models.rag_runtime import RagUserState
from app.rag.projection.contracts import IndexConfig, QueryConfig
from app.rag.projection.settings import request_rebuild, save_index, save_query, status
from tests.test_e5_rag_projection import OTHER, OWNER, e5_database


def test_query_save_is_owner_scoped_without_embedding_creation_or_rebuild(tmp_path, monkeypatch):
    async def scenario():
        async with e5_database(tmp_path / "db", monkeypatch) as factory:
            async with factory() as db:
                result = await save_query(db, OWNER, QueryConfig(top_k=3, rerank=False), 0)
                assert result["query_config"]["top_k"] == 3
                assert result["job_id"] is None
                assert await db.scalar(select(func.count()).select_from(Job)) == 0
                assert await db.scalar(select(func.count()).select_from(UserEmbeddingConfig)) == 0
                assert (await status(db, OTHER))["status"] == "uninitialized"
                with pytest.raises(BusinessWriteError, match="revision_conflict"):
                    await save_query(db, OWNER, QueryConfig(top_k=4, rerank=False), 0)
    asyncio.run(scenario())


def test_index_change_is_atomic_and_rebuild_requests_deduplicate(tmp_path, monkeypatch):
    async def scenario():
        async with e5_database(tmp_path / "db", monkeypatch) as factory:
            async with factory() as db:
                mark_managed_transaction(db)
                result = await save_index(db, OWNER, IndexConfig(chunk_size=800), 0)
                assert result["status"] == "queued"
                assert (await request_rebuild(db, OWNER))["job_id"] == result["job_id"]
                assert await db.scalar(select(func.count()).select_from(Job)) == 1
                await db.rollback()
            async with factory() as db:
                assert await db.get(RagUserState, OWNER) is None
                assert await db.scalar(select(func.count()).select_from(Job)) == 0
                result = await save_index(db, OWNER, IndexConfig(chunk_size=800), 0)
                assert (await request_rebuild(db, OWNER))["job_id"] == result["job_id"]
                with pytest.raises(BusinessWriteError, match="in_progress"):
                    await save_index(db, OWNER, IndexConfig(chunk_size=900), result["revision"])
                await db.rollback()
            async with factory() as db:
                assert (await status(db, OWNER))["index_config"]["chunk_size"] == 800
    asyncio.run(scenario())
