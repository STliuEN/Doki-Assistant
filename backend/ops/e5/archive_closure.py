"""Collect and seal the completed local E5 evidence without credentials or source bodies.

This archival tool reads fixed task directories only; it never operates live services.
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BATCH = ROOT / "project_changes/2026-09-10-e5-ar4-rag-projection"
PUBLIC = BATCH / "artifacts"
REPLICA = ROOT / ".runtime/e5-acceptance-20260914-v2"
FINAL = ROOT / ".runtime/e5-final-20260914"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def clean(value):
    if isinstance(value, dict):
        forbidden = {"password", "secret", "access_token", "refresh_token", "authorization", "cookie", "source_titles"}
        return {key: clean(item) for key, item in value.items() if key.lower() not in forbidden}
    if isinstance(value, list):
        return [clean(item) for item in value]
    return value


SOURCES = {
    "target-execution.json": (FINAL / "execution.json", "passed"),
    "target-smoke.json": (FINAL / "target-smoke.json", "verification_passed"),
    "final-audit.json": (FINAL / "final-audit.json", "passed"),
    "task-cleanup.json": (FINAL / "task-cleanup.json", "passed"),
    "restore-current.json": (REPLICA / "restore.json", "status"),
    "replica-rebuild.json": (REPLICA / "rebuild.json", "status"),
    "schema-upgrades.json": (REPLICA / "schema-upgrades.json", "passed"),
    "quality-results.json": (REPLICA / "quality-results.json", "passed"),
    "http-queued.json": (REPLICA / "http-queued.json", "passed"),
    "lifecycle.json": (REPLICA / "lifecycle.json", "passed"),
    "faults.json": (REPLICA / "faults.json", "passed"),
    "filesystem-corrupt.json": (REPLICA / "filesystem-corrupt.json", "passed"),
    "filesystem-permission.json": (REPLICA / "filesystem-permission.json", "passed"),
}


def collect():
    for name, (source, key) in SOURCES.items():
        value = read(source)
        assert value[key] is True or value[key] == "passed", name
        save(PUBLIC / name, clean(value))
    shutil.copyfile(FINAL / "line-endings.json", PUBLIC / "line-endings.json")
    # Preserve the exact frozen plan bytes, so its pre-test SHA remains independently verifiable.
    shutil.copyfile(REPLICA / "quality-plan.json", PUBLIC / "quality-plan.json")
    quality = read(PUBLIC / "quality-results.json")
    assert sha(PUBLIC / "quality-plan.json") == quality["plan_sha256"]
    assert read(PUBLIC / "quality-plan.json")["frozen_at"] < quality["started_at"]
    captures = []
    images = PUBLIC / "browser"
    images.mkdir(exist_ok=True)
    names = ("queued", "building", "ready", "query-saved", "index-queued", "failed", "restarted", "chunks", "upload", "uploaded", "api-restarted")
    for name in names:
        source = REPLICA / ("browser-" + name + ".txt")
        text = source.read_text(encoding="utf-8")
        assert "### Error" not in text
        result = json.loads(text.split("### Result", 1)[1].split("###", 1)[0].strip())
        screenshot = ROOT / "output/playwright" / ("e5-" + name + ".png")
        shutil.copyfile(screenshot, images / screenshot.name)
        captures.append({"name": name, "result": result, "screenshot": "browser/" + screenshot.name, "raw_capture_sha256": sha(source)})
    by_name = {item["name"]: item["result"] for item in captures}
    assert by_name["building"]["state"] == "building" and by_name["building"]["index_edit_disabled"]
    assert by_name["failed"]["state"] == "failed"
    assert by_name["ready"]["state"] == "ready"
    assert by_name["api-restarted"]["top_k"] == "3" and by_name["api-restarted"]["chunk_size"] == "800"
    assert by_name["api-restarted"]["state"] == "ready"
    assert by_name["chunks"]["verified_chunk_visible"]
    assert by_name["upload"]["queued_message"] == 1 and by_name["upload"]["ready_message"] == 0
    assert by_name["uploaded"]["queued_message"] == 0 and by_name["uploaded"]["ready_message"] == 1
    save(
        PUBLIC / "browser.json",
        {
            "passed": True,
            "browser": "Edge via Playwright CLI",
            "captures": captures,
            "api_restart": {"before_pid": 49084, "after_pid": 41872, "same_replica": True},
            "scope": "Real routers in scoped API harness; full main lifespan and Redis not evaluated",
        },
    )
    save(
        PUBLIC / "human-label-confirmation.json",
        {
            "date": "2026-09-14",
            "confirmed": True,
            "count": 8,
            "user_reply": "确认这 8 条来源映射（推荐）",
            "source": "explicit user reply in this session",
            "timing": "User source verification after model results; labels and thresholds frozen before testing",
            "independent_blind_annotation": False,
            "plan_sha256": quality["plan_sha256"],
        },
    )


def check_public_secrets():
    sensitive = []

    def extract(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if re.search(r"password|secret|(?:^|_)token$", key, re.I) and isinstance(item, str) and len(item) >= 12:
                    sensitive.append(item)
                else:
                    extract(item)
        elif isinstance(value, list):
            for item in value:
                extract(item)

    for path in list(REPLICA.glob("*.private.json")) + [ROOT / ".runtime/e4/live-credentials.json", FINAL / "invocation.private.json"]:
        extract(read(path))
    for path in PUBLIC.rglob("*"):
        if path.is_file() and path.suffix in {".json", ".txt", ".md"}:
            content = path.read_text(encoding="utf-8-sig")
            assert not any(secret in content for secret in sensitive), "Credential value found in public artifact: " + path.name
            assert not re.search(r"eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}", content), "JWT in " + path.name


def validate():
    for name, (_source, key) in SOURCES.items():
        value = read(PUBLIC / name)
        assert value[key] is True or value[key] == "passed", name
    execution = read(PUBLIC / "target-execution.json")
    assert execution["executed"] and execution["runner"]["succeeded_count"] == 2
    for name, digest in execution["code"].items():
        assert sha(ROOT / name.replace("\\", "/")) == digest, "Application changed after target execution: " + name
    audit = read(PUBLIC / "final-audit.json")
    assert len(audit["fk_checks"]) == 52 and all(row["orphans"] == 0 for row in audit["fk_checks"])
    assert sorted(row["chunks"] for row in audit["collections"]) == [0, 0, 11, 57]
    assert audit["no_untracked_chroma_collections"]
    assert execution["after"] == audit["inventory"]
    quality = read(PUBLIC / "quality-results.json")
    plan = read(PUBLIC / "quality-plan.json")
    assert sha(PUBLIC / "quality-plan.json") == quality["plan_sha256"]
    for name, result in quality["branches"].items():
        assert len(result["cases"]) == 8 and all(case["valid"] for case in result["cases"])
        assert result["source_hit_at_5"] >= plan["minimum_source_hit_at_5"]
        assert result["warm_sample_p95"] <= plan["warm_sample_p95_seconds"][name]
        assert result["cold_seconds"] <= plan["cold_max_seconds"]
    assert read(PUBLIC / "browser.json")["passed"]
    assert read(PUBLIC / "human-label-confirmation.json")["confirmed"]
    check_public_secrets()


def record(path):
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path), "bytes": path.stat().st_size}


def seal():
    validate()
    checks = read(PUBLIC / "checks.json")
    assert checks["status"] == "passed" and all(item["exit_code"] == 0 for item in checks["checks"])
    assert checks["backend_passed"] == 529 and checks["frontend_passed"] == 29
    verdict = {
        "schema_version": 2,
        "stage": "E5/S4/AR-4",
        "status": "closed",
        "status_zh": "已关闭",
        "closed_at": datetime.now(UTC).isoformat(),
        "decision_owner": "Codex under explicit user execution/closure authorization",
        "scope": "Windows local single instance; SQL runner concurrency 1",
        "gates": {"C" + str(i): "passed" for i in range(1, 7)},
        "acceptance": {"V%02d" % i: "passed" for i in range(1, 10)},
        "remaining_e5_blockers": [],
        "waivers": [],
        "human_labels_confirmed": True,
        "label_timing": "Frozen by Codex before testing; explicitly confirmed by user after testing; not independent blind labels",
        "follow_on_stages": "not_activated",
        "frozen": ["E6", "SKILL-GATE", "ARCH-GATE", "product 7-10"],
        "limitations": [
            "HyDE Q4 missed: 7/8; frozen minimum 0.75 met",
            "Only eight local relevance cases; sample p95 from seven warm requests",
            "Six historical e4.note.enrich dead letters retained",
            "Scoped API harness: full main/Redis/MCP/deployment not tested",
            "Native Linux/macOS and production RPO/RTO/high concurrency not tested",
            "Historical procedural deviations preserved",
        ],
    }
    save(PUBLIC / "closure-review.json", verdict)
    changed = set()
    for args in (["git", "-c", "core.autocrlf=false", "diff", "--name-only"], ["git", "ls-files", "--others", "--exclude-standard"]):
        changed.update(subprocess.check_output(args, cwd=ROOT).decode("utf-8").splitlines())
    files = {ROOT / name for name in changed if name.startswith(("backend/", "front/", "docs/")) and (ROOT / name).is_file()}
    files.update((ROOT / "backend/app/rag/projection").glob("*.py"))
    files.update((ROOT / "backend/ops/e5").glob("*.*"))
    files.update(BATCH.glob("*.md"))
    files.update(
        ROOT / path
        for path in ("backend/pyproject.toml", "front/package.json", "front/package-lock.json", "front/vite.config.ts", "scripts/check-docs.ps1")
        if (ROOT / path).is_file()
    )
    current_artifacts = [p for p in PUBLIC.rglob("*") if p.is_file() and p != PUBLIC / "evidence-index.json"]
    originals = [source for source, _ in SOURCES.values()] + [REPLICA / "quality-plan.json", FINAL / "preflight.json", FINAL / "allowlist.json"]
    originals += [FINAL / "target-before-final.sql", REPLICA / "target-current.sql"]
    save(
        PUBLIC / "evidence-index.json",
        {
            "schema_version": 2,
            "stage": "E5",
            "status": "closed",
            "recorded_at": datetime.now(UTC).isoformat(),
            "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip(),
            "working_tree": "Uncommitted changes; hashes below are actual final files, not only HEAD",
            "current_files": [record(p) for p in sorted(files)],
            "artifacts": [record(p) for p in sorted(current_artifacts)],
            "private_source_receipts": [record(p) for p in originals],
            "privacy": "Private originals are path/hash/length receipts only; no credentials, dumps or source bodies copied",
            "history": "artifacts/history contains superseded reports; old smoke/inventory/restore artifacts remain historical",
            "index_hash_policy": "This index intentionally excludes its own hash",
        },
    )


def verify():
    validate()
    index = read(PUBLIC / "evidence-index.json")
    for group in ("current_files", "artifacts", "private_source_receipts"):
        for row in index[group]:
            assert sha(ROOT / row["path"]) == row["sha256"], row["path"]
    assert read(PUBLIC / "closure-review.json")["status"] == index["status"] == "closed"
    print(json.dumps({"verified": True, "current_files": len(index["current_files"]), "artifacts": len(index["artifacts"])}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--seal", action="store_true")
    mode.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        verify()
    elif args.seal:
        seal()
        verify()
    else:
        collect()
        validate()
        print("Evidence collected and validated; final seal requires current successful checks")
