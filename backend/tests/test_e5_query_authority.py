import asyncio
from dataclasses import replace

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.failed_response_register import register_exception_handlers
from app.models.note import Note
from app.models.projection_domain import RagGenerationHead
from app.models.rag_runtime import RagUserState
from app.rag.projection import query as module
from app.rag.projection.contracts import ProjectionUnavailable
from tests.test_e5_rag_projection import OTHER, OWNER, adapter, e5_database, note, runner, snapshot


async def prepare(factory, store, monkeypatch):
    async with factory() as db:
        row = note(tags=[], category="study")
        db.add(row)
        await db.commit()
        identifier = row.id
    consumer = await runner(factory, store)
    assert await consumer.run_once()
    monkeypatch.setattr(module, "ChromaProjectionAdapter", lambda _: store)
    monkeypatch.setattr(module, "model_snapshot", snapshot)
    return identifier


def test_query_rejects_candidate_injected_after_validation(tmp_path, monkeypatch):
    async def scenario():
        async with e5_database(tmp_path / "db", monkeypatch) as factory:
            store = adapter(tmp_path / "chroma")
            await prepare(factory, store, monkeypatch)
            original = store.chunks

            async def chunks(**kwargs):
                values = await original(**kwargs)
                return [replace(value, source_id=OTHER, text="foreign private content") for value in values]

            store.chunks = chunks
            async with factory() as db:
                with pytest.raises(ProjectionUnavailable, match="rag_candidate_invalid"):
                    await module.query_user(db, OWNER, "private", query_config_override={"rerank": False})
    asyncio.run(scenario())


@pytest.mark.parametrize("mutation", ["delete", "rebuild", "query_config"])
def test_fresh_return_snapshot_observes_mid_query_changes(tmp_path, monkeypatch, mutation):
    async def scenario():
        async with e5_database(tmp_path / "db", monkeypatch) as factory:
            store = adapter(tmp_path / "chroma")
            identifier = await prepare(factory, store, monkeypatch)
            plain = async_sessionmaker(factory.kw["bind"], expire_on_commit=False)
            original = store.query
            changed = False

            async def query(**kwargs):
                nonlocal changed
                values = await original(**kwargs)
                if not changed:
                    changed = True
                    async with plain() as writer:
                        if mutation == "delete":
                            await writer.delete(await writer.get(Note, identifier))
                        elif mutation == "rebuild":
                            await writer.execute(update(RagUserState).values(status="building"))
                        else:
                            await writer.execute(update(RagUserState).values(query_revision=RagUserState.query_revision + 1))
                        await writer.commit()
                return values

            store.query = query
            async with factory() as db:
                await db.get(RagUserState, OWNER)  # Deliberately seed a stale caller identity map.
                with pytest.raises(ProjectionUnavailable):
                    await module.query_user(db, OWNER, "private", query_config_override={"rerank": False})
    asyncio.run(scenario())


def test_notes_false_still_checks_notes_health_and_owner(tmp_path, monkeypatch):
    async def scenario():
        async with e5_database(tmp_path / "db", monkeypatch) as factory:
            store = adapter(tmp_path / "chroma")
            await prepare(factory, store, monkeypatch)
            async with factory() as db:
                with pytest.raises(ProjectionUnavailable, match="rebuild_in_progress"):
                    await module.query_user(db, OTHER, "private", query_config_override={"rerank": False})
                head = await db.scalar(select(RagGenerationHead).where(RagGenerationHead.index_kind == "notes"))
                await store.delete(collection=store.locator("notes", head.active_generation_id), owner=OWNER, generation=head.active_generation_id)
                with pytest.raises(ProjectionUnavailable):
                    await module.query_user(db, OWNER, "private", query_config_override={"notes": False, "rerank": False})
    asyncio.run(scenario())


def test_query_filters_sources_for_vector_and_bm25(tmp_path, monkeypatch):
    async def scenario():
        async with e5_database(tmp_path / "db", monkeypatch) as factory:
            store = adapter(tmp_path / "chroma")
            await prepare(factory, store, monkeypatch)
            async with factory() as db:
                result = await module.query_user(db, OWNER, "private", query_config_override={"rerank": False, "source_ids": [OTHER]})
                assert result.status == "ready" and not result.hits
    asyncio.run(scenario())


def test_e5_errors_have_uniform_http_envelope():
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/notes/search")
    async def failing():
        raise ProjectionUnavailable("chroma_query_failed", job_id="job")

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/notes/search")
        assert response.status_code == 503
        assert response.json()["data"] == {"status": "degraded", "degraded_reason": "chroma_query_failed", "job_id": "job"}
    asyncio.run(scenario())


def test_rag_tool_requires_authenticated_context(monkeypatch):
    from app.agent.tools.rag_summary import tool as tool_module
    monkeypatch.setattr(tool_module, "E5_RAG_ENABLED", True)
    monkeypatch.setattr(tool_module, "get_current_user_id_from_context", lambda: None)
    result = asyncio.run(tool_module.rag_summary_tool.ainvoke({"query": "private", "user_id": OWNER}))
    assert "认证上下文" in result
