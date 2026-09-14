"""Read-only E5 inventory and UTF-8 query evidence; never starts a consumer.

Run from any directory with backend/.venv/Scripts/python.exe. Credentials stay
in .runtime; private output contains metadata/digests, never document bodies or secrets.
"""

import argparse
import asyncio
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
TARGET = "doki-e4-20260903-mysql"
TARGET_ID = "35efc06e8a3b377ace2d9ac7e99f9d78ceb8c9a7a73464cc23701413f1d37182"
TARGET_UUID = "0c0d3e33-a743-11f1-af41-ea47e0ceb469"
CORPUS_OWNER = "2e2c05f2-d031-527e-b463-93c9f0cccbfa"
EMPTY_OWNER = "f4aff4a5-2f5a-535a-825f-b6a906d9cd12"


def sha_file(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def inspect_container(name):
    result = subprocess.run(["docker", "inspect", name], capture_output=True, check=True)
    return json.loads(result.stdout)[0]


def protected_state():
    value = inspect_container("new-api")
    return {"id": value["Id"], "started_at": value["State"]["StartedAt"], "restart_count": value["RestartCount"], "status": value["State"]["Status"]}


def prepare():
    target = inspect_container(TARGET)
    if target["Id"] != TARGET_ID or target["State"]["Status"] != "running":
        raise ValueError("E5 target identity or runtime state changed")
    ports = target["NetworkSettings"]["Ports"]["3306/tcp"]
    if ports != [{"HostIp": "127.0.0.1", "HostPort": "33427"}]:
        raise ValueError("E5 target endpoint changed")
    from sqlalchemy import URL

    private = json.loads((ROOT / ".runtime/e4/live-credentials.json").read_text(encoding="utf-8"))
    url = URL.create(
        "mysql+aiomysql",
        username="doki_e4_app",
        password=private["target_password"],
        host="127.0.0.1",
        port=33427,
        database="doki_e4",
        query={"charset": "utf8mb4"},
    )
    # Import compatibility only: no E4 launcher, runtime guard, or consumer runs.
    os.environ.update(
        E4_MIGRATION_ENABLED="I_UNDERSTAND_E4_MIGRATION",
        E4_RUNNER_ENABLED="false",
        E4_DATABASE_URL=url.render_as_string(hide_password=False),
        E5_RAG_ENABLED="true",
        E5_CHROMA_PERSIST_DIRECTORY=str(ROOT / ".runtime/e5-20260914/chroma-live"),
        OLLAMA_BASE_URL="http://127.0.0.1:11434",
        TEXT_EMBEDDING_MODEL_NAME="qwen3-embedding:0.6b",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        PYTHONUTF8="1",
    )
    sys.path.insert(0, str(BACKEND))
    return url


async def inventory(factory):
    from sqlalchemy import text

    async with factory() as db:
        identity = (await db.execute(text("SELECT @@server_uuid, DATABASE(), @@global.read_only, @@global.super_read_only"))).one()
        if identity[0] != TARGET_UUID or identity[1] != "doki_e4":
            raise ValueError("E5 database fingerprint changed")
        queries = {
            "schema": "SELECT version_num FROM alembic_version",
            "source_counts": "SELECT 'knowledge' AS kind, canonical_user_id AS owner, status, COUNT(*) AS n FROM knowledge_source_documents "
            "GROUP BY canonical_user_id,status UNION ALL SELECT 'notes', canonical_user_id, 'included', COUNT(*) "
            "FROM notes GROUP BY canonical_user_id",
            "states": "SELECT user_id,status,revision,query_revision,source_digest,query_config,index_config,job_id,error_code "
            "FROM rag_user_states ORDER BY user_id",
            "heads": "SELECT owner_scope_id,index_kind,active_generation_id,staging_generation_id,revision "
            "FROM rag_generation_heads ORDER BY owner_scope_id,index_kind",
            "artifacts": "SELECT generation_id,collection_name,chunk_count,cleanup_status,manifest_digest,embedding_config "
            "FROM rag_artifacts ORDER BY generation_id",
            "jobs": "SELECT job_type,status,COUNT(*) AS n FROM jobs GROUP BY job_type,status ORDER BY job_type,status",
            "sources": "SELECT canonical_id,canonical_user_id,artifact_digest,content_digest FROM knowledge_source_documents ORDER BY canonical_id",
            "notes": "SELECT canonical_id,canonical_user_id,content_digest FROM notes ORDER BY canonical_id",
        }
        result = {key: [dict(row) for row in (await db.execute(text(sql))).mappings()] for key, sql in queries.items()}
        result["global_flags_observed"] = list(identity[2:])
        result["source_titles"] = [
            dict(row)
            for row in (
                await db.execute(text("SELECT canonical_id,original_filename AS title FROM knowledge_source_documents ORDER BY canonical_id"))
            ).mappings()
        ]
        return result


def reranker_preflight():
    config = json.loads((BACKEND / "data/reranker_config.json").read_text(encoding="utf-8"))
    path = (BACKEND / config["model_path"]).resolve()
    if not path.is_relative_to((BACKEND / "models").resolve()):
        raise ValueError("Reranker must be inside the existing backend/models cache")
    index = path / "model.safetensors.index.json"
    names = sorted(set(json.loads(index.read_text(encoding="utf-8"))["weight_map"].values()))
    required = [
        path / name for name in (*names, "config.json", "tokenizer.json", "tokenizer_config.json", "modules.json", "1_LogitScore/config.json")
    ]
    if any(not item.is_file() or item.stat().st_size == 0 for item in required):
        raise ValueError("Incomplete local model; downloads are outside this verification")
    return {
        "model": config["model_name"],
        "configured_device": config["device"],
        "files": [{"name": item.relative_to(path).as_posix(), "bytes": item.stat().st_size, "sha256": sha_file(item)} for item in required],
    }


async def run(args):
    url = prepare()
    from sqlalchemy import event
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(url, pool_size=2, max_overflow=0, hide_parameters=True)

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def read_only(_connection, _cursor, statement, _parameters, _context, _many):
        if not statement.lstrip().upper().startswith(("SELECT ", "SHOW ")):
            raise RuntimeError("Closure verification rejected non-read SQL")

    factory = async_sessionmaker(engine, expire_on_commit=False)
    result = {
        "schema_version": 1,
        "recorded_at": datetime.now(UTC).isoformat(),
        "code_commit": subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
        "script_sha256": sha_file(Path(__file__)),
        "new_api_before": protected_state(),
        "cases": [],
    }
    result["before"] = await inventory(factory)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    save()
    try:
        if not args.inventory_only:
            import httpx

            from app.rag.projection.query import query_user

            result["reranker"] = await asyncio.to_thread(reranker_preflight)
            async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
                response = await client.get("http://127.0.0.1:11434/api/tags")
                response.raise_for_status()
                result["ollama_models"] = [{"name": item["name"], "digest": item["digest"]} for item in response.json()["models"]]
            # Freeze exact UTF-8 input and branch controls before invoking models.
            query = "计算机技术专业的课程有哪些？"
            cases = [
                (
                    name,
                    CORPUS_OWNER,
                    {"bm25": name in {"bm25", "combined"}, "hyde": name in {"hyde", "combined"}, "rerank": name in {"rerank", "combined"}},
                )
                for name in ("vector", "bm25", "hyde", "rerank", "combined")
            ]
            cases.append(("empty_owner", EMPTY_OWNER, {"bm25": True, "hyde": False, "rerank": False}))
            result["frozen_query"] = query
            result["query_sha256"] = hashlib.sha256(query.encode("utf-8")).hexdigest()
            result["frozen_cases"] = [{"name": name, "owner": owner, "config": {"top_k": 5, **config}} for name, owner, config in cases]
            result["criteria"] = "Branch smoke only: finite scores, <=5 hits, correct source owner/generation. No relevance or latency threshold."
            save()
            source_owners = {row["canonical_id"]: row["canonical_user_id"] for key in ("sources", "notes") for row in result["before"][key]}
            for case in result["frozen_cases"]:
                started = time.monotonic()
                print(json.dumps({"starting": case["name"]}), flush=True)
                record = {**case}
                try:
                    async with factory() as db:
                        answer = await query_user(db, case["owner"], query, query_config_override=case["config"])
                    record.update(
                        status=answer.status,
                        hit_count=len(answer.hits),
                        generations=answer.generation,
                        hits=[
                            {
                                "chunk_id": hit.chunk.id,
                                "source_id": hit.chunk.source_id,
                                "kind": hit.chunk.index_kind,
                                "score": hit.score,
                                "text_sha256": hashlib.sha256(hit.chunk.text.encode()).hexdigest(),
                            }
                            for hit in answer.hits
                        ],
                    )
                    record["smoke_passed"] = (
                        answer.status == "ready"
                        and len(answer.hits) <= 5
                        and (len(answer.hits) == 0 if case["name"] == "empty_owner" else len(answer.hits) > 0)
                        and all(
                            source_owners.get(hit.chunk.source_id) == case["owner"]
                            and math.isfinite(hit.score)
                            and hit.generation == answer.generation.get(hit.chunk.index_kind)
                            for hit in answer.hits
                        )
                    )
                except Exception as error:
                    record.update(status="error", error_code=getattr(error, "code", type(error).__name__), smoke_passed=False)
                record["elapsed_seconds"] = round(time.monotonic() - started, 3)
                result["cases"].append(record)
                save()
                print(json.dumps({key: record[key] for key in ("name", "status", "smoke_passed", "elapsed_seconds")}), flush=True)
        result["after"] = await inventory(factory)
        result["new_api_after"] = protected_state()
        result["sql_inventory_unchanged"] = result["before"] == result["after"]
        result["new_api_unchanged"] = result["new_api_before"] == result["new_api_after"]
        result["verification_passed"] = (
            result["sql_inventory_unchanged"]
            and result["new_api_unchanged"]
            and all(case["smoke_passed"] for case in result["cases"])
            and (args.inventory_only or len(result["cases"]) == 6)
        )
        result["completed_at"] = datetime.now(UTC).isoformat()
        save()
        return result["verification_passed"]
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--inventory-only", action="store_true")
    sys.exit(0 if asyncio.run(run(parser.parse_args())) else 1)
