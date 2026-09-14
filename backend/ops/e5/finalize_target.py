"""Explicit guarded E5 target cutover after replica acceptance. Never host SQL 3306."""

import argparse
import asyncio
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
from ops.e5.acceptance_env import dump, save  # noqa: E402 - standalone CLI backend path bootstrap
from ops.e5.verify_closure import (  # noqa: E402 - standalone CLI backend path bootstrap
    CORPUS_OWNER,
    EMPTY_OWNER,
    TARGET,
    TARGET_UUID,
    inspect_container,
    inventory,
    prepare,
    protected_state,
    sha_file,
)


async def run(args):
    directory = args.directory.resolve()
    if directory.exists() or not directory.is_relative_to(ROOT / ".runtime"):
        raise ValueError("Use a new E5 execution evidence directory")
    directory.mkdir()
    url = prepare()  # Pins exact original E5 container ID and loopback port 33427.
    container = inspect_container(TARGET)
    private = json.loads((ROOT / ".runtime/e4/live-credentials.json").read_text())
    backup = directory / "target-before-final.sql"
    backup.write_bytes(dump(TARGET, private["target_password"], "doki_e4_app"))
    assert backup.read_bytes().count(b"\n") > 500
    allowlist = {
        "schema_version": 1,
        "stage": "E5",
        "targets": [
            {
                "id": "e5-final-target",
                "role": "target",
                "host": "127.0.0.1",
                "port": 33427,
                "database": "doki_e4",
                "server_uuid": TARGET_UUID,
                "credential_ref": "e5-final-app",
                "database_username": "doki_e4_app",
                "read_only": False,
                "container_name": TARGET,
                "container_id": container["Id"],
                "image_reference": container["Config"]["Image"],
                "image_id": container["Image"],
                "network": "doki-e4-20260903-net",
            }
        ],
    }
    save(directory / "allowlist.json", allowlist)
    approval = secrets.token_hex(24)
    save(directory / "invocation.private.json", {"approval_token": approval})
    env = dict(
        os.environ,
        E4_ALLOWLIST_FILE=str(directory / "allowlist.json"),
        E4_TARGET_ID="e5-final-target",
        E4_CREDENTIAL_REF="e5-final-app",
        E4_APPROVAL_TOKEN=approval,
        E4_RUNNER_ENABLED="true",
        E4_PREFLIGHT_FILE=str(directory / "preflight.json"),
        JOB_LEASE_SECONDS="60",
        JOB_HEARTBEAT_SECONDS="15",
        JOB_POLL_SECONDS="0.5",
        JOB_SHUTDOWN_DRAIN_SECONDS="5",
    )
    issued = subprocess.run(
        [
            sys.executable,
            str(ROOT / "backend/scripts/e4_preflight.py"),
            "--output",
            env["E4_PREFLIGHT_FILE"],
            "--purposes",
            "runtime",
            "--issuance-switch",
            "I_UNDERSTAND_E4_PREFLIGHT_ISSUANCE",
        ],
        env=env,
        capture_output=True,
    )
    assert issued.returncode == 0, "Final E5 preflight failed"
    os.environ.update(env)
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.db.business_authority import BusinessSession
    from app.db.uow import SqlUnitOfWork
    from app.jobs.e4_runtime import build_e4_runner
    from app.models.rag_runtime import RagUserState
    from app.rag.projection.contracts import QueryConfig
    from app.rag.projection.settings import request_rebuild, save_query

    engine = create_async_engine(url, pool_size=2, max_overflow=0, hide_parameters=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, sync_session_class=BusinessSession)
    result = {
        "stage": "E5",
        "before": await inventory(factory),
        "backup_sha256": sha_file(backup),
        "new_api_before": protected_state(),
        "preflight_sha256": sha_file(directory / "preflight.json"),
        "code": {str(p.relative_to(ROOT)): sha_file(p) for p in sorted((ROOT / "backend/app/rag/projection").glob("*.py"))},
        "executed": False,
    }
    save(directory / "execution.json", result)
    runtime = None
    try:
        if args.execute:
            assert {row["user_id"] for row in result["before"]["states"]} == {CORPUS_OWNER, EMPTY_OWNER}
            assert all(row["status"] in {"succeeded", "dead_letter", "cancelled"} for row in result["before"]["jobs"])
            runtime = build_e4_runner(environ=env)
            await runtime.start()  # Holds SQL process lock before enqueuing work.
            result["process_lock"] = runtime.runner.snapshot.as_dict()
            async with SqlUnitOfWork(factory) as uow:
                db = uow.require_session()
                for owner in (CORPUS_OWNER, EMPTY_OWNER):
                    state = await db.get(RagUserState, owner)
                    await save_query(db, owner, QueryConfig.model_validate(state.query_config), state.query_revision)
                    await request_rebuild(db, owner, "E5 final acceptance: pin query model identity and republish verified complete corpus")
                await uow.commit()
            result["executed"] = True
            save(directory / "execution.json", result)
            started = time.monotonic()
            for _ in range(600):
                async with factory() as db:
                    states = [await db.get(RagUserState, owner) for owner in (CORPUS_OWNER, EMPTY_OWNER)]
                    if all(state.status == "ready" for state in states):
                        break
                await asyncio.sleep(1)
            else:
                raise RuntimeError("Final target rebuild timeout")
            result["rebuild_seconds"] = round(time.monotonic() - started, 3)
            await runtime.stop()
            result["runner"] = runtime.runner.snapshot.as_dict()
        result["after"] = await inventory(factory)
        result["new_api_after"] = protected_state()
        for key in ("sources", "notes"):
            fields = (
                ("canonical_id", "canonical_user_id", "artifact_digest")
                if key == "sources"
                else ("canonical_id", "canonical_user_id", "content_digest")
            )
            assert [[r[f] for f in fields] for r in result["before"][key]] == [[r[f] for f in fields] for r in result["after"][key]]
        assert result["new_api_before"] == result["new_api_after"]
        assert result["after"]["global_flags_observed"] == [0, 0]
        result["passed"] = bool(args.execute) and all(row["status"] == "ready" for row in result["after"]["states"])
        save(directory / "execution.json", result)
        print(json.dumps({"passed": result["passed"], "executed": result["executed"], "rebuild_seconds": result.get("rebuild_seconds")}), flush=True)
    except Exception as error:
        result["error"] = getattr(error, "code", type(error).__name__)
        save(directory / "execution.json", result)
        raise
    finally:
        if runtime is not None:
            await runtime.stop()
            await runtime.engine.dispose()
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    asyncio.run(run(parser.parse_args()))
