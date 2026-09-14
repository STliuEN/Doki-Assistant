"""Persisted Chroma/SQL faults and actual authenticated routes on the E5 replica."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
from ops.e5.acceptance_env import preflight, save  # noqa: E402 - standalone CLI backend path bootstrap
from ops.e5.http_acceptance import client  # noqa: E402 - standalone CLI backend path bootstrap


async def run(args):
    directory = args.directory.resolve()
    os.environ.update(preflight(directory))
    os.environ["AUTH_JWT_SECRET"] = json.loads((directory / "auth.private.json").read_text())["secret"]
    login, owner = client(directory)
    token = login.headers["Authorization"]
    login.close()
    from sqlalchemy import select

    from app.db.db_config import AsyncSessionLocal, async_engine, verify_database_schema
    from app.jobs.e4_runtime import build_e4_runner
    from app.models.projection_domain import RagGenerationHead
    from app.models.rag_runtime import RagArtifact, RagUserState
    from app.rag.projection.chroma_adapter import ChromaProjectionAdapter
    from app.rag.projection.embedding import embedding_model
    from app.rag.projection.query import query_user
    from app.rag.projection.settings import request_rebuild

    await verify_database_schema()
    from fastapi import FastAPI

    from app.core.business_boundary import BusinessBoundaryMiddleware
    from app.core.failed_response_register import register_exception_handlers
    from app.router.chat import chat_router
    from app.router.knowledge_router import knowledge_router
    from app.router.note_router import note_router
    from app.router.user import user_router

    app = FastAPI()
    app.add_middleware(BusinessBoundaryMiddleware)
    register_exception_handlers(app)
    for router in (chat_router, note_router, knowledge_router, user_router):
        app.include_router(router)
    results = {"owner": owner, "cases": []}

    async def rebuild():
        async with AsyncSessionLocal() as db:
            await request_rebuild(db, owner, "E5 fault recovery")
        runtime = build_e4_runner(environ=os.environ)
        await runtime.start()
        try:
            for _ in range(120):
                async with AsyncSessionLocal() as db:
                    value = await db.get(RagUserState, owner)
                    if value.status == "ready":
                        return
                await asyncio.sleep(1)
            raise RuntimeError("Fault recovery timeout")
        finally:
            await runtime.stop()
            await runtime.engine.dispose()

    async def collection(kind):
        async with AsyncSessionLocal() as db:
            head = await db.scalar(select(RagGenerationHead).where(RagGenerationHead.owner_scope_id == owner, RagGenerationHead.index_kind == kind))
            artifact = await db.get(RagArtifact, head.active_generation_id)
        adapter = ChromaProjectionAdapter(embedding_model)
        return adapter._client().get_collection(artifact.collection_name, embedding_function=None), artifact

    try:
        await rebuild()
        async with AsyncSessionLocal() as db:
            state = await db.get(RagUserState, owner)
            original_query = state.query_config
            state.query_config = {**original_query, "rerank": False, "notes": False}
            await db.commit()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://e5", headers={"Authorization": token}
        ) as http:
            healthy = await http.post("/chat/rag/query", json={"query": "紫色水獭"})
            assert healthy.status_code == 200
            for fault in ("owner", "format", "content", "missing_notes"):
                store, artifact = await collection("notes" if fault == "missing_notes" else "knowledge")
                metadata = store.metadata
                saved = None
                if fault == "owner":
                    store.modify(metadata={**metadata, "e5_owner": "00000000-0000-4000-8000-000000000001"})
                elif fault == "format":
                    store.modify(metadata={**metadata, "e5_format": 999})
                elif fault == "content":
                    saved = store.get(include=["documents", "metadatas", "embeddings"])
                    store.update(ids=saved["ids"], documents=["unauthorized injected content" for _ in saved["ids"]], embeddings=saved["embeddings"])
                else:
                    ChromaProjectionAdapter(embedding_model)._client().delete_collection(artifact.collection_name)
                try:
                    response = await http.post("/chat/rag/query", json={"query": "紫色水獭"})
                    assert response.status_code == 503, (fault, response.text)
                    error = response.json()["data"]
                    assert error["status"] == "degraded" and error["job_id"]
                    # Every other reader fails closed while core SQL reads continue.
                    for path, params in (("/note/search", {"q": "紫色水獭"}), ("/knowledge/chunks", {"filename": "e5-acceptance.txt"})):
                        negative = await http.get(path, params=params)
                        assert negative.status_code == 503 and negative.json()["data"]["job_id"] == error["job_id"]
                    assert (await http.get("/user/detail/")).status_code == 200
                    assert (await http.get("/user/sessions/")).status_code == 200
                    assert (await http.get("/knowledge/detail", params={"filename": "e5-acceptance.txt"})).status_code == 200
                    results["cases"].append(
                        {
                            "fault": fault,
                            "http": 503,
                            "reason": error["degraded_reason"],
                            "repair_job": error["job_id"],
                            "core_auth_sessions_original": 200,
                            "passed": True,
                        }
                    )
                finally:
                    if fault in {"owner", "format"}:
                        store.modify(metadata=metadata)
                    elif fault == "content":
                        store.update(ids=saved["ids"], documents=saved["documents"], embeddings=saved["embeddings"], metadatas=saved["metadatas"])
                await rebuild()
                save(directory / "faults.json", results)
            for fault, controls in (
                ("hyde_digest", {"hyde": True, "hyde_model_digest": "0" * 64}),
                ("hyde_missing", {"hyde": True, "hyde_model": "e5-deliberately-missing:latest", "hyde_model_digest": None}),
                ("reranker_digest", {"rerank": True, "reranker_model_digest": "0" * 64}),
            ):
                async with AsyncSessionLocal() as db:
                    state = await db.get(RagUserState, owner)
                    state.query_config = {**original_query, "rerank": False, **controls}
                    await db.commit()
                try:
                    response = await http.post("/chat/rag/query", json={"query": "紫色水獭"})
                    assert response.status_code == 503
                    assert response.json()["data"]["job_id"] is None
                    async with AsyncSessionLocal() as db:
                        assert (await db.get(RagUserState, owner)).status == "ready"
                    assert (await http.get("/user/detail/")).status_code == 200
                    results["cases"].append(
                        {"fault": fault, "http": 503, "reason": response.json()["data"]["degraded_reason"], "spurious_rebuild": False, "passed": True}
                    )
                finally:
                    async with AsyncSessionLocal() as db:
                        state = await db.get(RagUserState, owner)
                        state.query_config = original_query
                        await db.commit()
            # Real authenticated agent tool and foreign-id rejection.
            from app.agent.tool_context import get_current_user_id_from_context, set_current_user_id
            from app.agent.tools.rag_summary.tool import rag_summary_tool

            previous_owner = get_current_user_id_from_context()
            set_current_user_id(owner)
            try:
                answer = await rag_summary_tool.ainvoke({"query": "紫色水獭"})
                assert "紫色水獭" in answer
                foreign = await rag_summary_tool.ainvoke({"query": "紫色水獭", "user_id": "00000000-0000-4000-8000-000000000001"})
                assert "不匹配" in foreign
            finally:
                set_current_user_id(previous_owner)
            results["cases"].append({"fault": "agent owner context", "passed": True})
        async with AsyncSessionLocal() as db:
            isolated = await query_user(
                db, owner, "private", query_config_override={"source_ids": ["488b62a4-fa82-4e3e-8ca6-ab73e888fe68"], "rerank": False}
            )
            assert not isolated.hits
        results["cases"].append({"fault": "foreign source filter", "passed": True})
        results["passed"] = all(value["passed"] for value in results["cases"])
        save(directory / "faults.json", results)
        print(json.dumps({"passed": results["passed"], "cases": len(results["cases"])}), flush=True)
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    asyncio.run(run(parser.parse_args()))
