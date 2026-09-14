import asyncio
import threading
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.job_domain import Job
from app.models.projection_domain import RagGenerationHead
from app.models.rag_runtime import RagArtifact, RagUserState
from app.rag.projection.chroma_adapter import ChromaProjectionAdapter
from app.rag.projection.contracts import Chunk, ProjectionUnavailable
from app.rag.projection.service import E5ProjectionService
from tests.test_e5_rag_projection import OWNER, Embedding, adapter, e5_database, note, runner


def test_cancelled_thread_cannot_race_cleanup_or_resurrect_collection(tmp_path):
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()

    class SlowEmbedding(Embedding):
        def embed_documents(self, texts):
            entered.set()
            try:
                if not release.wait(5):
                    raise RuntimeError("test release timeout")
                return super().embed_documents(texts)
            finally:
                finished.set()

    async def scenario():
        store = ChromaProjectionAdapter(lambda _: SlowEmbedding(), persist_directory=tmp_path / "chroma")
        generation = str(uuid4())
        args = {"collection": store.locator("notes", generation), "owner": OWNER, "generation": generation}
        build = {**args, "chunks": [Chunk("a", "text", "source", "digest", "notes", 0)], "embedding": {"dimension": 3}}
        task = asyncio.create_task(store.build(**build))
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            with pytest.raises(ProjectionUnavailable, match="attempt_busy"):
                await store.delete(**args)
        finally:
            release.set()
        assert await asyncio.to_thread(finished.wait, 5)
        # A lock can remain held briefly after embedding returns while the add finishes.
        for _ in range(100):
            try:
                await store.delete(**args)
                break
            except ProjectionUnavailable as error:
                assert error.code == "chroma_attempt_busy"
                await asyncio.sleep(0.02)
        else:
            raise AssertionError("cleanup did not converge")
        assert not store._client().list_collections()
        with pytest.raises(ProjectionUnavailable, match="attempt_retired"):
            await store.build(**build)
    asyncio.run(scenario())


def test_missing_collection_tombstone_blocks_delayed_worker(tmp_path):
    async def scenario():
        store = adapter(tmp_path / "chroma")
        generation = str(uuid4())
        args = {"collection": store.locator("notes", generation), "owner": OWNER, "generation": generation}
        await store.delete(**args)
        with pytest.raises(ProjectionUnavailable, match="attempt_retired"):
            await store.build(**args, chunks=[], embedding={"dimension": 3})
    asyncio.run(scenario())


def test_new_service_retries_failed_cleanup_without_rebuild(tmp_path, monkeypatch):
    async def scenario():
        async with e5_database(tmp_path / "db", monkeypatch) as factory:
            store = adapter(tmp_path / "chroma")
            async with factory() as db:
                row = note(tags=[], category="study")
                db.add(row)
                await db.commit()
            consumer = await runner(factory, store)
            await consumer.run_once()
            async with factory() as db:
                old = set(await db.scalars(select(RagGenerationHead.active_generation_id)))
                row = await db.get(type(row), row.id)
                row.content = "updated SQL"
                await db.commit()
            original = store.delete

            async def fail(**kwargs):
                raise ProjectionUnavailable("chroma_cleanup_failed")

            store.delete = fail
            await consumer.run_once()
            async with factory() as db:
                assert (await db.get(RagUserState, OWNER)).status == "ready"
                for key in old:
                    assert (await db.get(RagArtifact, key)).cleanup_status == "pending"
            store.delete = original
            service = E5ProjectionService(factory, adapter=store)
            await service.reconcile()
            await service.reconcile()
            async with factory() as db:
                for key in old:
                    assert (await db.get(RagArtifact, key)).cleanup_status == "deleted"
                assert (await db.get(RagUserState, OWNER)).status == "ready"
            assert len(store._client().list_collections()) == 2
    asyncio.run(scenario())


def test_cancelled_queued_job_becomes_explicit_failed_state(tmp_path, monkeypatch):
    async def scenario():
        async with e5_database(tmp_path / "db", monkeypatch) as factory:
            async with factory() as db:
                db.add(note(tags=[], category="study"))
                await db.commit()
                job = await db.scalar(select(Job))
                job.status = "cancelled"
                await db.commit()
            await E5ProjectionService(factory, adapter=adapter(tmp_path / "chroma")).reconcile()
            async with factory() as db:
                assert (await db.get(RagUserState, OWNER)).status == "failed"
    asyncio.run(scenario())
