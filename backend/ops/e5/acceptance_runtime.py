"""Scoped real E5 routers/consumer on the acceptance replica; excludes unrelated bootstraps."""

import argparse
import asyncio
import json
import os
import secrets
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
from ops.e5.acceptance_env import preflight, save  # noqa: E402 - standalone CLI backend path bootstrap


async def run(args):
    from sqlalchemy import select

    from app.db.db_config import AsyncSessionLocal, verify_database_schema
    from app.models.identity_domain import User

    await verify_database_schema()
    if args.mode == "sources":
        from app.rag.projection.sources import parse, read_sources

        async with AsyncSessionLocal() as db:
            for owner in await db.scalars(select(User.id)):
                for source in await read_sources(db, owner):
                    print(
                        json.dumps(
                            {
                                "owner": owner,
                                "id": source.id,
                                "kind": source.kind,
                                "title": source.title,
                                "excerpt": "\n".join(text for _, text in parse(source))[:850],
                            },
                            ensure_ascii=False,
                        )
                    )
        from app.db.db_config import async_engine

        await async_engine.dispose()
        return
    from app.jobs.e4_runtime import build_e4_runner

    runtime = build_e4_runner(environ=os.environ)
    if args.mode == "rebuild":
        from app.rag.projection.settings import request_rebuild

        async with AsyncSessionLocal() as db:
            owners = list(await db.scalars(select(User.id)))
        for owner in owners:
            async with AsyncSessionLocal() as db:
                await request_rebuild(db, owner, "E5 restore-to-new-Chroma acceptance")
    if args.pause_after_build:
        from app.rag.projection.chroma_adapter import ChromaProjectionAdapter
        from app.rag.projection.embedding import embedding_model

        adapter = ChromaProjectionAdapter(embedding_model)
        original = adapter.build

        async def paused(**kwargs):
            receipt = await original(**kwargs)
            save(args.directory / "build-paused.json", {"pid": os.getpid(), "generation": kwargs["generation"], "collection": kwargs["collection"]})
            await asyncio.Event().wait()
            return receipt

        adapter.build = paused
        runtime.projection.adapter = adapter
    await runtime.start()
    save(args.directory / ("consumer-started-" + str(os.getpid()) + ".json"), runtime.runner.snapshot.as_dict())
    print(json.dumps({"consumer": "running", "pid": os.getpid()}), flush=True)
    try:
        from app.models.rag_runtime import RagUserState

        for _ in range(1800):
            if args.stop_file and args.stop_file.exists():
                break
            if args.mode == "rebuild":
                async with AsyncSessionLocal() as db:
                    states = list(await db.scalars(select(RagUserState)))
                    if states and all(value.status == "ready" for value in states):
                        save(
                            args.directory / "rebuild.json",
                            {
                                "status": "passed",
                                "owners": [{"owner": s.user_id, "revision": s.revision, "status": s.status} for s in states],
                                "runner": runtime.runner.snapshot.as_dict(),
                            },
                        )
                        print("All replica owners ready", flush=True)
                        break
            await asyncio.sleep(1)
        else:
            raise RuntimeError("Consumer acceptance timeout")
    finally:
        await runtime.stop()
        await runtime.engine.dispose()
        from app.db.db_config import async_engine

        await async_engine.dispose()


def serve(args):
    import uvicorn
    from fastapi import FastAPI

    from app.core.business_boundary import BusinessBoundaryMiddleware
    from app.core.failed_response_register import register_exception_handlers
    from app.db.db_config import async_engine, verify_database_schema
    from app.router.chat import chat_router
    from app.router.health import health_router
    from app.router.job_router import job_router
    from app.router.knowledge_router import knowledge_router
    from app.router.note_router import note_router
    from app.router.rag_router import rag_router
    from app.router.user import user_router

    @asynccontextmanager
    async def lifespan(_app):
        await verify_database_schema()
        yield
        await async_engine.dispose()

    app = FastAPI(lifespan=lifespan)
    app.add_middleware(BusinessBoundaryMiddleware)
    register_exception_handlers(app)
    for router in (rag_router, knowledge_router, note_router, chat_router, user_router, health_router, job_router):
        app.include_router(router)
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["sources", "rebuild", "consumer", "serve"])
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--pause-after-build", action="store_true")
    parser.add_argument("--stop-file", type=Path)
    parser.add_argument("--port", type=int, default=18050)
    args = parser.parse_args()
    args.directory = args.directory.resolve()
    os.environ.update(preflight(args.directory))
    secret_file = args.directory / "auth.private.json"
    if not secret_file.exists():
        save(secret_file, {"secret": secrets.token_hex(32), "login_name": "e5-browser-" + uuid4().hex[:8], "password": secrets.token_hex(16)})
    os.environ["AUTH_JWT_SECRET"] = json.loads(secret_file.read_text())["secret"]
    if args.mode == "serve":
        serve(args)
    else:
        asyncio.run(run(args))


if __name__ == "__main__":
    main()
