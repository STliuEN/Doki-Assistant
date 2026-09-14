"""Real MySQL lease, process-lock, crash/restart and terminal cleanup rehearsal."""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
from ops.e5.acceptance_env import preflight, save  # noqa: E402 - standalone CLI backend path bootstrap


def launch(directory, pause=False):
    marker = "paused" if pause else "recovery"
    args = [
        sys.executable,
        "-X",
        "utf8",
        str(ROOT / "backend/ops/e5/acceptance_runtime.py"),
        "consumer",
        "--directory",
        str(directory),
        "--stop-file",
        str(directory / (marker + ".stop")),
    ]
    if pause:
        args.append("--pause-after-build")
    with (directory / (marker + ".log")).open("ab") as log:
        process = subprocess.Popen(args, cwd=ROOT, stdout=log, stderr=log, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    save(directory / (marker + "-process.json"), {"pid": process.pid, "args": args})
    return process


async def run(args):
    directory = args.directory.resolve()
    os.environ.update(preflight(directory))
    from app.db.db_config import AsyncSessionLocal, async_engine, verify_database_schema
    from app.jobs.repository import JobRepository
    from app.models.job_domain import Job
    from app.models.rag_runtime import RagArtifact, RagUserState
    from app.rag.projection.service import E5ProjectionService
    from app.rag.projection.settings import request_rebuild

    await verify_database_schema()
    owner = json.loads((directory / "api.private.json").read_text())["user"]["id"]
    output = directory / "lifecycle.json"
    result = json.loads(output.read_text()) if output.exists() else {"checks": []}

    async def state():
        async with AsyncSessionLocal() as db:
            value = await db.get(RagUserState, owner)
            job = await db.get(Job, value.job_id) if value.job_id else None
            return {
                "status": value.status,
                "job_id": value.job_id,
                "lease": str(job.lease_expires_at) if job else None,
                "fence": job.fencing_token if job else None,
            }

    try:
        if args.mode == "pause":
            process = launch(directory, True)
            for _ in range(120):
                if (directory / "build-paused.json").exists():
                    break
                if process.poll() is not None:
                    raise RuntimeError("Paused consumer exited; inspect its private log")
                await asyncio.sleep(1)
            else:
                raise RuntimeError("Build checkpoint timeout")
            first = await state()
            await asyncio.sleep(8)
            renewed = await state()
            assert first["status"] == renewed["status"] == "building" and first["fence"] == renewed["fence"]
            assert renewed["lease"] > first["lease"]
            result["checks"].append({"case": "long build heartbeat", "passed": True, "before": first, "after": renewed})
            duplicate = subprocess.run(
                [sys.executable, str(ROOT / "backend/ops/e5/acceptance_runtime.py"), "consumer", "--directory", str(directory)],
                capture_output=True,
                timeout=40,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            (directory / "duplicate-runner.log").write_bytes(duplicate.stdout + duplicate.stderr)
            assert duplicate.returncode != 0 and b"process lock" in duplicate.stderr
            result["checks"].append({"case": "second process rejected by SQL lock", "passed": True})
            result["paused"] = json.loads((directory / "build-paused.json").read_text())
        elif args.mode == "recover":
            import psutil

            recorded = json.loads((directory / "paused-process.json").read_text())
            process = psutil.Process(recorded["pid"])
            assert "--pause-after-build" in process.cmdline() and str(directory) in process.cmdline()
            before = await state()
            process.kill()
            process.wait(timeout=15)
            started = time.monotonic()
            recovered = launch(directory)
            for _ in range(180):
                if (await state())["status"] == "ready":
                    break
                if recovered.poll() is not None:
                    raise RuntimeError("Recovery consumer exited")
                await asyncio.sleep(1)
            else:
                raise RuntimeError("Crash recovery timeout")
            abandoned = result["paused"]["generation"]
            for _ in range(20):
                async with AsyncSessionLocal() as db:
                    artifact = await db.get(RagArtifact, abandoned)
                    if artifact.cleanup_status == "deleted":
                        break
                await asyncio.sleep(1)
            assert artifact.cleanup_status == "deleted"
            async with AsyncSessionLocal() as db:
                job = await db.get(Job, before["job_id"])
                assert job.status == "succeeded" and job.fencing_token > before["fence"]
                result["checks"].append(
                    {
                        "case": "kill restart and fenced reclaim",
                        "passed": True,
                        "job": job.id,
                        "before_fence": before["fence"],
                        "after_fence": job.fencing_token,
                        "cleanup": artifact.cleanup_status,
                        "seconds": round(time.monotonic() - started, 3),
                    }
                )
            (directory / "recovery.stop").touch()
            await asyncio.to_thread(recovered.wait, 20)
        elif args.mode == "cancel":
            async with AsyncSessionLocal() as db:
                queued = await request_rebuild(db, owner, "E5 queued cancellation acceptance")
                transition = await JobRepository(db).cancel(job_id=queued["job_id"], reason="E5 cancellation scenario")
                assert transition.accepted
                await db.commit()
            await E5ProjectionService(AsyncSessionLocal).reconcile()
            assert (await state())["status"] == "failed"
            result["checks"].append({"case": "cancelled queued job reconciles to failed", "passed": True})
        result["passed"] = all(row["passed"] for row in result["checks"])
        save(output, result)
        print(json.dumps({"mode": args.mode, "passed": result["passed"], "checks": len(result["checks"])}), flush=True)
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["pause", "recover", "cancel"])
    parser.add_argument("--directory", type=Path, required=True)
    asyncio.run(run(parser.parse_args()))
