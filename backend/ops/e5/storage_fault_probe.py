"""Probe actual filesystem corruption/ACL refusal through real E5 ASGI routes."""

import argparse
import asyncio
import csv
import json
import os
import subprocess
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
    authorization = login.headers["Authorization"]
    login.close()
    from app.db.db_config import AsyncSessionLocal, async_engine, verify_database_schema
    from app.jobs.e4_runtime import build_e4_runner
    from app.models.rag_runtime import RagUserState
    from app.rag.projection.settings import request_rebuild

    await verify_database_schema()

    async def rebuild():
        async with AsyncSessionLocal() as db:
            await request_rebuild(db, owner, "Storage fault recovery")
        runtime = build_e4_runner(environ=os.environ)
        await runtime.start()
        try:
            for _ in range(90):
                async with AsyncSessionLocal() as db:
                    if (await db.get(RagUserState, owner)).status == "ready":
                        return
                await asyncio.sleep(1)
            raise RuntimeError("Storage fault recovery timeout")
        finally:
            await runtime.stop()
            await runtime.engine.dispose()

    from fastapi import FastAPI

    from app.core.failed_response_register import register_exception_handlers
    from app.router.chat import chat_router
    from app.router.user import user_router

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(chat_router)
    app.include_router(user_router)
    original_path = os.environ["E5_CHROMA_PERSIST_DIRECTORY"]
    path = directory / ("filesystem-" + args.fault)
    path.mkdir(exist_ok=False)
    if args.fault == "corrupt":
        (path / "chroma.sqlite3").write_bytes(b"E5 deliberate invalid SQLite header; preserve for evidence\n")
    sid = None
    try:
        if args.fault == "permission":
            # Deny only read access in a brand-new task directory. WRITE_DAC remains
            # available to remove this exact explicit deny in finally.
            output = subprocess.check_output(["whoami", "/user", "/fo", "csv", "/nh"], text=True)
            sid = list(csv.reader([output.strip()]))[0][1]
            subprocess.run(["icacls", str(path), "/deny", "*" + sid + ":(OI)(CI)(R)"], capture_output=True, check=True)
            try:
                list(path.iterdir())
                raise AssertionError("ACL fault did not deny directory reads")
            except PermissionError:
                pass
        os.environ["E5_CHROMA_PERSIST_DIRECTORY"] = str(path)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://e5", headers={"Authorization": authorization}
        ) as c:
            response = await c.post("/chat/rag/query", json={"query": "紫色水獭"})
            assert response.status_code == 503, response.text
            error = response.json()["data"]
            assert error["degraded_reason"].startswith("chroma_") and error["job_id"]
            core = await c.get("/user/detail/")
            assert core.status_code == 200
            record = {
                "fault": args.fault,
                "real_filesystem_fault": True,
                "http": 503,
                "reason": error["degraded_reason"],
                "core_auth": 200,
                "repair_job": error["job_id"],
                "passed": True,
            }
    finally:
        os.environ["E5_CHROMA_PERSIST_DIRECTORY"] = original_path
        if sid:
            subprocess.run(["icacls", str(path), "/remove:d", "*" + sid], capture_output=True, check=True)
            assert path.is_dir() and list(path.iterdir()) is not None
        await rebuild()
        await async_engine.dispose()
    save(directory / ("filesystem-" + args.fault + ".json"), record)
    print(json.dumps(record), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("fault", choices=["corrupt", "permission"])
    parser.add_argument("--directory", type=Path, required=True)
    asyncio.run(run(parser.parse_args()))
