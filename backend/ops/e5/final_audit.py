"""Read-only final FK/source/head/artifact audit of the exact E5 target."""

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
from ops.e5.acceptance_env import save  # noqa: E402 - standalone CLI backend path bootstrap
from ops.e5.verify_closure import inventory, prepare, protected_state  # noqa: E402 - standalone CLI backend path bootstrap


async def run(output):
    url = prepare()
    from sqlalchemy import event, text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.rag.projection.chroma_adapter import ChromaProjectionAdapter
    from app.rag.projection.embedding import embedding_model
    from app.rag.projection.snapshot import read_snapshot
    from app.rag.projection.sources import split_sources

    engine = create_async_engine(url, pool_size=2, max_overflow=0, hide_parameters=True)

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def readonly(_conn, _cursor, statement, *_args):
        if not statement.lstrip().upper().startswith(("SELECT ", "SHOW ")):
            raise RuntimeError("Final audit is read-only")

    factory = async_sessionmaker(engine, expire_on_commit=False)
    result = {"fk_checks": [], "collections": [], "new_api": protected_state()}
    try:
        result["inventory"] = await inventory(factory)
        async with factory() as db:
            rows = (
                (
                    await db.execute(
                        text(
                            "SELECT TABLE_NAME, CONSTRAINT_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME "
                            "FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=DATABASE() AND REFERENCED_TABLE_NAME IS NOT NULL "
                            "ORDER BY TABLE_NAME, CONSTRAINT_NAME, ORDINAL_POSITION"
                        )
                    )
                )
                .mappings()
                .all()
            )
            groups = {}
            for row in rows:
                groups.setdefault((row["TABLE_NAME"], row["CONSTRAINT_NAME"], row["REFERENCED_TABLE_NAME"]), []).append(row)

            def identifier(value):
                assert value.replace("_", "").isalnum()
                return "`" + value + "`"

            for (table, constraint, parent), columns in groups.items():
                joins = " AND ".join("c." + identifier(r["COLUMN_NAME"]) + "=p." + identifier(r["REFERENCED_COLUMN_NAME"]) for r in columns)
                nonnull = " AND ".join("c." + identifier(r["COLUMN_NAME"]) + " IS NOT NULL" for r in columns)
                statement = (
                    "SELECT COUNT(*) FROM "
                    + identifier(table)
                    + " c LEFT JOIN "
                    + identifier(parent)
                    + " p ON "
                    + joins
                    + " WHERE "
                    + nonnull
                    + " AND p."
                    + identifier(columns[0]["REFERENCED_COLUMN_NAME"])
                    + " IS NULL"
                )
                count = await db.scalar(text(statement))
                assert count == 0, constraint
                result["fk_checks"].append({"constraint": constraint, "table": table, "orphans": count})
        adapter = ChromaProjectionAdapter(embedding_model)
        active_names = []
        for state in result["inventory"]["states"]:
            snapshot = await read_snapshot(factory, state["user_id"])
            chunks = await asyncio.to_thread(split_sources, snapshot.sources, snapshot.index)
            for kind, artifact in snapshot.artifacts.items():
                await adapter.validate(
                    collection=artifact["collection"],
                    owner=state["user_id"],
                    generation=artifact["generation"],
                    chunks=chunks[kind],
                    receipt=artifact["receipt"],
                )
                active_names.append(artifact["collection"])
                result["collections"].append(
                    {"owner": state["user_id"], "kind": kind, "generation": artifact["generation"], "chunks": len(chunks[kind])}
                )
        all_names = sorted(value.name for value in adapter._client().list_collections())
        assert all_names == sorted(active_names)
        assert all(value["cleanup_status"] in {"retained", "deleted"} for value in result["inventory"]["artifacts"])
        assert all(value["staging_generation_id"] is None for value in result["inventory"]["heads"])
        assert result["inventory"]["global_flags_observed"] == [0, 0]
        result["reranker_sidecar_sha256"] = hashlib.sha256((ROOT / "backend/data/reranker_config.json").read_bytes()).hexdigest()
        result["no_untracked_chroma_collections"] = True
        result["passed"] = True
        save(output, result)
        print(json.dumps({"passed": True, "foreign_keys": len(result["fk_checks"]), "active_collections": len(all_names)}), flush=True)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(run(parser.parse_args().output))
