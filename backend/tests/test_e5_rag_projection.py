import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db import business_authority
from app.db.business_authority import BusinessWriteError
from app.jobs.business_handlers import business_handlers
from app.jobs.runner import SqlJobRunner
from app.models.embedding_config import UserEmbeddingConfig
from app.models.job_domain import AuditEvent, Job
from app.models.note import Note
from app.models.projection_domain import RagGeneration, RagGenerationHead
from app.models.rag_runtime import RagArtifact, RagUserState
from app.rag.projection.chroma_adapter import ChromaProjectionAdapter
from app.rag.projection.contracts import Chunk, ProjectionUnavailable
from app.rag.projection.service import E5ProjectionService
from app.rag.projection.sources import Source, digest, source_manifest
from tests.test_e4_business_authority import OTHER, OWNER, database, note


class Embedding:
    def embed_documents(self, texts):
        return [[float(len(value)), 1.0, 0.5] for value in texts]

    def embed_query(self, value):
        return self.embed_documents([value])[0]


async def snapshot(config):
    return {**config, "dimension": 3, "model_digest": "fixture-v1"}


@asynccontextmanager
async def e5_database(path, monkeypatch):
    async with database(path) as factory:
        async with factory.kw["bind"].begin() as connection:
            await connection.run_sync(lambda sync: RagUserState.metadata.create_all(sync, tables=[
                UserEmbeddingConfig.__table__, RagGeneration.__table__, RagGenerationHead.__table__,
                RagUserState.__table__, RagArtifact.__table__]))
        monkeypatch.setattr(business_authority, "E5_RAG_ENABLED", True)
        yield factory


def adapter(path):
    return ChromaProjectionAdapter(lambda _: Embedding(), persist_directory=path)


async def runner(factory, store):
    service = E5ProjectionService(factory, adapter=store, snapshot_provider=snapshot)

    async def project(session, kind, payload, context):
        try:
            return await service.rebuild(session, payload["owner_id"], context)
        except Exception:
            import traceback
            traceback.print_exc()
            raise

    return SqlJobRunner(factory, registry=business_handlers(factory, projector=project), claim_registered_only=True)


def test_gate_covers_unbound_sessions_other_users_and_transaction_reuse(tmp_path, monkeypatch):
    async def scenario():
        async with e5_database(tmp_path / "gate.db", monkeypatch) as factory:
            async with factory() as db:
                first = note(tags=[], category="study")
                first_id = first.id
                db.add(first)
                await db.commit()
                state = await db.get(RagUserState, OWNER)
                assert state.status == "building" and state.job_id
                assert not db.info.get("e5_scope_transitions")
                first.tags = ["late"]
                with pytest.raises(BusinessWriteError, match="rag_rebuild_in_progress"):
                    await db.commit()
                await db.rollback()
            async with factory() as db:
                db.info["e5_rag_state"] = None  # No binding or stale binding cannot bypass.
                first = await db.get(Note, first_id)
                first.content = "changed"
                with pytest.raises(BusinessWriteError):
                    await db.flush()
            async with factory() as db:
                other = Note(id=OTHER, user_id=OTHER, title="other", content="other", tags=[], category="study")
                db.add(other)
                await db.commit()
                assert (await db.get(RagUserState, OTHER)).status == "building"
    asyncio.run(scenario())


def test_real_chroma_receipts_scope_missing_collection_and_protected_paths(tmp_path, monkeypatch):
    monkeypatch.delenv("E5_CHROMA_PERSIST_DIRECTORY", raising=False)
    with pytest.raises(ProjectionUnavailable, match="path_required"):
        ChromaProjectionAdapter(lambda _: Embedding())
    with pytest.raises(ProjectionUnavailable, match="overlaps_protected"):
        adapter("data/chromadb/e5")

    async def scenario():
        store = adapter(tmp_path / "vectors")
        generation = OWNER
        collection = store.locator("notes", generation)
        chunk = Chunk("chunk-1", "private source", "note-1", "digest", "notes", 0)
        receipt = await store.build(collection=collection, owner=OWNER, generation=generation, chunks=[chunk], embedding={"dimension": 3})
        await store.validate(collection=collection, owner=OWNER, generation=generation, chunks=[chunk], receipt=receipt)
        with pytest.raises(ProjectionUnavailable):
            await store.validate(collection=collection, owner=OWNER, generation=generation, chunks=[replace(chunk, text="tamper")], receipt=receipt)
        with pytest.raises(ProjectionUnavailable):
            await store.delete(collection=collection, owner=OTHER, generation=generation)
        hits = await store.query(collection=collection, owner=OWNER, generation=generation, query="private", embedding={"dimension": 3}, top_k=10)
        assert hits[0].chunk == chunk
        await store.delete(collection=collection, owner=OWNER, generation=generation)
        with pytest.raises(ProjectionUnavailable):
            await store.query(collection=collection, owner=OWNER, generation=generation, query="private", embedding={"dimension": 3}, top_k=10)
        assert store._client().list_collections() == []
    asyncio.run(scenario())


def test_runner_publishes_both_heads_job_audit_and_reclaims_old_generation(tmp_path, monkeypatch):
    async def scenario():
        async with e5_database(tmp_path / "atomic.db", monkeypatch) as factory:
            store = adapter(tmp_path / "vectors")
            async with factory() as db:
                row = note(tags=[], category="study")
                db.add(row)
                await db.commit()
            consumer = await runner(factory, store)
            assert await consumer.run_once()
            assert consumer.snapshot.succeeded_count == 1
            async with factory() as db:
                state = await db.get(RagUserState, OWNER)
                assert state.status == "ready" and state.job_id is None
                heads = list(await db.scalars(select(RagGenerationHead)))
                old = {head.active_generation_id for head in heads}
                assert len(old) == 2
                job = await db.scalar(select(Job))
                assert job.status == "succeeded" and job.result_json["status"] == "ready"
                assert await db.scalar(select(AuditEvent).where(AuditEvent.action == "rag.published"))
                row = await db.get(Note, row.id)
                row.content = "new canonical SQL text"
                await db.commit()
                assert (await db.get(RagUserState, OWNER)).status == "building"
            assert await consumer.run_once()
            assert consumer.snapshot.succeeded_count == 2
            async with factory() as db:
                for generation in old:
                    assert (await db.get(RagGeneration, generation)).status == "retired"
                    assert (await db.get(RagArtifact, generation)).cleanup_status == "deleted"
            assert len(store._client().list_collections()) == 2
    asyncio.run(scenario())


@pytest.mark.parametrize("fault", ["validation", "source_drift", "lease_loss", "completion_rejected"])
def test_failed_or_stale_attempt_never_publishes_either_head(tmp_path, monkeypatch, fault):
    async def scenario():
        async with e5_database(tmp_path / "fault.db", monkeypatch) as factory:
            store = adapter(tmp_path / "vectors")
            original = store.validate
            async with factory() as db:
                row = note(tags=[], category="study")
                db.add(row)
                await db.commit()
            plain = async_sessionmaker(factory.kw["bind"], expire_on_commit=False)
            async def validate(**kwargs):
                await original(**kwargs)
                if kwargs["collection"].startswith("e5_notes_"):
                    if fault == "validation":
                        raise ProjectionUnavailable("injected_receipt_failure")
                    async with plain() as db:
                        if fault == "source_drift":
                            await db.execute(update(Note).values(content="external modification"))
                        elif fault == "lease_loss":
                            await db.execute(update(Job).values(fencing_token=Job.fencing_token + 1))
                        await db.commit()
            store.validate = validate
            if fault == "completion_rejected":
                from app.jobs.repository import JobRepository, TransitionResult
                async def reject(*args, **kwargs):
                    return TransitionResult(False, "stale")
                monkeypatch.setattr(JobRepository, "succeed", reject)
            consumer = await runner(factory, store)
            assert await consumer.run_once()
            async with factory() as db:
                assert (await db.get(RagUserState, OWNER)).status != "ready"
                assert all(head.active_generation_id is None for head in await db.scalars(select(RagGenerationHead)))
                assert all(artifact.receipt is None for artifact in await db.scalars(select(RagArtifact)))
                assert (await db.scalar(select(Job))).status != "succeeded"
    asyncio.run(scenario())


def test_manifest_includes_parser_extension():
    original = Source("source", "knowledge", "file", b"text", "txt")
    assert digest(source_manifest([original])) != digest(source_manifest([replace(original, extension="pdf")]))


def test_business_session_rejects_global_sql_switch():
    from types import SimpleNamespace
    state = SimpleNamespace(statement=text("SET GLOBAL read_only = 1"), is_update=False, is_delete=False, is_insert=False)
    with pytest.raises(BusinessWriteError):
        business_authority.reject_bulk_business_writes(state)
