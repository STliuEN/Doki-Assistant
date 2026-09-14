"""Frozen corpus-specific labels and real local model evaluation; no SQL writes."""

import argparse
import asyncio
import hashlib
import json
import math
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
from ops.e5.acceptance_env import environment, save  # noqa: E402 - standalone CLI backend path bootstrap
from ops.e5.verify_closure import CORPUS_OWNER, EMPTY_OWNER, protected_state, sha_file  # noqa: E402 - standalone CLI backend path bootstrap


async def run(args):
    os.environ.update(environment(args.directory))
    from sqlalchemy import event
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.rag.projection.contracts import IndexConfig
    from app.rag.projection.sources import digest, read_sources, source_manifest, split_sources

    engine = create_async_engine(os.environ["E4_DATABASE_URL"], hide_parameters=True)

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def only_reads(_conn, _cursor, statement, *_args):
        if not statement.lstrip().upper().startswith(("SELECT ", "SHOW ")):
            raise RuntimeError("Quality evaluation SQL writes forbidden")

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        sources = await read_sources(db, CORPUS_OWNER)
    plan_path = args.directory / "quality-plan.json"
    if args.freeze:
        if plan_path.exists():
            raise ValueError("Frozen plan already exists")
        definitions = [
            ("人工智能方向", "人工智能方向专业学位有哪些研究方向，例如大语言模型和多模态信息融合？", "knowledge"),
            ("计算机技术方向", "电子信息计算机技术专业硕士点始建于哪一年？", "knowledge"),
            ("计算机科学与技术专业研究生培养方案.docx", "计算机科学与技术学术硕士的学科代码、学制和最低学分是多少？", "knowledge"),
            ("软件工程专业", "软件工程学科是哪一年获批硕士学位授权点和开始招收研究生的？", "knowledge"),
            ("新一代", "新一代电子信息技术专业的类别领域代码、学位类型和学分要求是什么？", "knowledge"),
            ("创新成果", "申请博士学位的研究生创新成果中，SCI期刊和报纸理论版文章的认定要求是什么？", "knowledge"),
            ("全工具链测试笔记", "哪条笔记用于后端日志检查并验证 create_note_tool 是否正常工作？", "notes"),
            ("毕业要求速查表", "哪条笔记写有 GPA 不低于 2.0、论文查重率低于 15% 和答辩通过的通用要求？", "notes"),
        ]
        cases = []
        for index, (title_part, query, kind) in enumerate(definitions):
            selected = [source for source in sources if title_part in source.title and source.kind == kind]
            assert len(selected) == 1, title_part
            cases.append(
                {
                    "id": "Q" + str(index + 1),
                    "query": query,
                    "notes": kind == "notes",
                    "expected_source_ids": [selected[0].id],
                    "label_basis": "explicit passage in SQL original: " + selected[0].title,
                }
            )
        save(
            plan_path,
            {
                "frozen_at": datetime.now(UTC).isoformat(),
                "labeler": "Codex; source-grounded, not independent human labels",
                "scope": "Small local regression set; no general retrieval-quality claim",
                "source_manifest_digest": digest(source_manifest(sources)),
                "top_k": 5,
                "minimum_source_hit_at_5": 0.75,
                "maximum_unauthorized_hits": 0,
                "cold_max_seconds": 180,
                "warm_sample_p95_seconds": {"vector": 10, "bm25": 10, "hyde": 30, "reranker": 60, "combined": 60},
                "bm25_only_minimum_source_hit_at_5": 0.75,
                "cases": cases,
            },
        )
        print(json.dumps({"frozen": str(plan_path), "sha256": sha_file(plan_path), "cases": len(cases)}), flush=True)
        await engine.dispose()
        return
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert digest(source_manifest(sources)) == plan["source_manifest_digest"]
    from app.rag.projection.contracts import QueryConfig
    from app.rag.projection.embedding import model_snapshot
    from app.rag.projection.local_reranker import model_fingerprint
    from app.rag.projection.query import query_user
    from app.rag.projection.query_branches import bind_query_models, bm25
    from app.rag.projection.snapshot import read_snapshot

    result = {
        "started_at": datetime.now(UTC).isoformat(),
        "plan_sha256": sha_file(plan_path),
        "new_api_before": protected_state(),
        "branches": {},
        "errors": [],
    }
    output = args.directory / "quality-results.json"
    save(output, result)
    try:
        snapshot = await read_snapshot(factory, CORPUS_OWNER)
        result["embedding"] = await model_snapshot(snapshot.embedding)
        result["reranker"] = await model_fingerprint("qwen3-reranker-4b")
        pinned = await bind_query_models(QueryConfig(hyde=True).model_dump(), snapshot.embedding["base_url"])
        result["query_models"] = pinned
        chunks = await asyncio.to_thread(split_sources, sources, IndexConfig.model_validate(snapshot.index))
        lexical = []
        for case in plan["cases"]:
            candidates = chunks["knowledge"] + (chunks["notes"] if case["notes"] else [])
            hits = bm25(candidates, case["query"], 5)
            lexical.append(
                {
                    "id": case["id"],
                    "source_ids": [hit.chunk.source_id for hit in hits],
                    "hit": any(hit.chunk.source_id in case["expected_source_ids"] for hit in hits),
                }
            )
        result["bm25_only"] = {"cases": lexical, "source_hit_at_5": sum(c["hit"] for c in lexical) / len(lexical)}
        authorized = {source.id for source in sources}
        for branch in ("vector", "bm25", "hyde", "reranker", "combined"):
            records = []
            result["branches"][branch] = {"cases": records}
            for case in plan["cases"]:
                controls = {
                    **pinned,
                    "top_k": 5,
                    "bm25": branch in {"bm25", "combined"},
                    "hyde": branch in {"hyde", "combined"},
                    "rerank": branch in {"reranker", "combined"},
                    "notes": case["notes"],
                }
                ticks = []
                done = asyncio.Event()

                async def ticker():
                    previous = time.monotonic()
                    while not done.is_set():
                        await asyncio.sleep(0.05)
                        current = time.monotonic()
                        ticks.append(current - previous)
                        previous = current

                task = asyncio.create_task(ticker())
                started = time.monotonic()
                record = {"id": case["id"]}
                try:
                    async with factory() as db:
                        answer = await query_user(db, CORPUS_OWNER, case["query"], query_config_override=controls)
                    record.update(
                        hit=any(hit.chunk.source_id in case["expected_source_ids"] for hit in answer.hits),
                        valid=len(answer.hits) <= 5
                        and all(
                            hit.chunk.source_id in authorized
                            and math.isfinite(hit.score)
                            and hit.generation == answer.generation[hit.chunk.index_kind]
                            for hit in answer.hits
                        ),
                        hits=[
                            {
                                "chunk_id": hit.chunk.id,
                                "source_id": hit.chunk.source_id,
                                "generation": hit.generation,
                                "score": hit.score,
                                "text_sha256": hashlib.sha256(hit.chunk.text.encode()).hexdigest(),
                            }
                            for hit in answer.hits
                        ],
                    )
                except Exception as error:
                    record.update(hit=False, valid=False, error=getattr(error, "code", type(error).__name__))
                    result["errors"].append({"branch": branch, **record})
                finally:
                    done.set()
                    await task
                record.update(seconds=round(time.monotonic() - started, 3), event_loop_max_gap=round(max(ticks, default=0), 3))
                records.append(record)
                save(output, result)
                print(
                    json.dumps(
                        {"branch": branch, "id": case["id"], "hit": record["hit"], "seconds": record["seconds"], "error": record.get("error")}
                    ),
                    flush=True,
                )
            warm = sorted(record["seconds"] for record in records[1:])
            result["branches"][branch].update(
                source_hit_at_5=sum(record["hit"] for record in records) / len(records),
                warm_sample_p95=warm[math.ceil(len(warm) * 0.95) - 1],
                cold_seconds=records[0]["seconds"],
            )
        async with factory() as db:
            empty = await query_user(db, EMPTY_OWNER, plan["cases"][0]["query"], query_config_override={"rerank": False})
        result["empty_owner_isolated"] = not empty.hits
        result["new_api_after"] = protected_state()
        result["passed"] = (
            not result["errors"]
            and result["empty_owner_isolated"]
            and result["new_api_before"] == result["new_api_after"]
            and result["bm25_only"]["source_hit_at_5"] >= plan["bm25_only_minimum_source_hit_at_5"]
            and all(
                value["source_hit_at_5"] >= plan["minimum_source_hit_at_5"]
                and value["warm_sample_p95"] <= plan["warm_sample_p95_seconds"][branch]
                and value["cold_seconds"] <= plan["cold_max_seconds"]
                and all(row["valid"] for row in value["cases"])
                for branch, value in result["branches"].items()
            )
        )
        result["completed_at"] = datetime.now(UTC).isoformat()
        save(output, result)
        print(json.dumps({"passed": result["passed"]}), flush=True)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--freeze", action="store_true")
    asyncio.run(run(parser.parse_args()))
