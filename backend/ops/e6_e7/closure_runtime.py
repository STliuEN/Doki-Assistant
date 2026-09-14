"""Rebuild derived Chroma only on the pinned E6/E7 acceptance replica."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))


async def rebuild(directory):
    from sqlalchemy import select

    from app.db.db_config import AsyncSessionLocal, async_engine, verify_database_schema
    from app.jobs.e4_runtime import build_e4_runner
    from app.models.identity_domain import User
    from app.models.rag_runtime import RagUserState
    from app.rag.projection.settings import request_rebuild, status
    from ops.e6_e7.acceptance_env import save

    await verify_database_schema()
    runtime = build_e4_runner(environ=dict(os.environ, E4_RUNNER_ENABLED="true"))
    assert runtime is not None
    try:
        await runtime.start()
        async with AsyncSessionLocal() as db:
            owners = list(await db.scalars(select(User.id)))
        for owner in owners:
            async with AsyncSessionLocal() as db:
                await request_rebuild(db, owner, "E6/E7 SQL-only recovery to new Chroma")
        requeued = set()
        for iteration in range(600):
            async with AsyncSessionLocal() as db:
                states = list(await db.scalars(select(RagUserState)))
                if len(states) == len(owners) and all(row.status == "ready" for row in states):
                    report = {"status": "passed", "owners": [await status(db, owner) | {"owner": owner} for owner in owners]}
                    save(directory / "rebuild.json", report)
                    print(json.dumps({"rebuild": "passed", "owners": len(owners)}), flush=True)
                    return
                if iteration % 20 == 0:
                    print(
                        json.dumps({"waiting": [{"owner": row.user_id, "status": row.status, "error": row.error_code} for row in states]}), flush=True
                    )
                terminal_owners = [row.user_id for row in states if row.status == "failed" and row.error_code == "rag_job_incomplete"]
            for owner in terminal_owners:
                if owner not in requeued:
                    async with AsyncSessionLocal() as db:
                        await request_rebuild(db, owner, "E6/E7 rebuild after originating revoked job reached terminal state")
                    requeued.add(owner)
            await asyncio.sleep(1)
        raise RuntimeError("Replica rebuild did not converge; inspect jobs and state")
    finally:
        await runtime.stop()
        await runtime.engine.dispose()
        await async_engine.dispose()


def main():
    from ops.e6_e7.acceptance_env import preflight

    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    os.environ.update(preflight(directory))
    asyncio.run(rebuild(directory))


if __name__ == "__main__":
    main()
