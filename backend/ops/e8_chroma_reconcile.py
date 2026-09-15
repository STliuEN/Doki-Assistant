"""Validate every restored SQL RAG generation against its rebuilt Chroma data."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))


async def main(directory):
    from sqlalchemy import select

    from app.db.db_config import AsyncSessionLocal, async_engine, verify_database_schema
    from app.models.identity_domain import User
    from app.rag.projection.chroma_adapter import ChromaProjectionAdapter
    from app.rag.projection.embedding import embedding_model
    from app.rag.projection.snapshot import read_snapshot
    from app.rag.projection.sources import split_sources

    await verify_database_schema()
    rows = []
    async with AsyncSessionLocal() as db:
        owners = list(await db.scalars(select(User.id)))
    adapter = ChromaProjectionAdapter(embedding_model)
    for owner in owners:
        snapshot = await read_snapshot(AsyncSessionLocal, owner)
        expected = await asyncio.to_thread(split_sources, snapshot.sources, snapshot.index)
        for kind, artifact in snapshot.artifacts.items():
            await adapter.validate(
                collection=artifact["collection"], owner=owner, generation=artifact["generation"], chunks=expected[kind], receipt=artifact["receipt"]
            )
            rows.append(
                {
                    "owner": owner,
                    "kind": kind,
                    "generation": artifact["generation"],
                    "chunks": len(expected[kind]),
                    "ids_digest": artifact["receipt"]["ids_digest"],
                }
            )
    await async_engine.dispose()
    report = {
        "stage": "E8",
        "status": "passed",
        "owners": len(owners),
        "artifacts": rows,
        "authority": "SQL snapshot -> rebuilt Chroma",
        "legacy_fallback": False,
    }
    out = directory / "chroma-reconciliation.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "passed", "owners": len(owners), "artifacts": len(rows)}))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("directory", type=Path)
    a = p.parse_args()
    d = a.directory.resolve()
    from ops.e6_e7.acceptance_env import preflight

    os.environ.update(
        preflight(d, ("runtime", "validate")),
        E8_ENABLED="true",
        E6E7_ENABLED="true",
        E5_RAG_ENABLED="true",
        SKILL_STORAGE_DIR=str(d / "absent-legacy-packages"),
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
    )
    asyncio.run(main(d))
