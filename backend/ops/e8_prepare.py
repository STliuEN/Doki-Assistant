"""Prepare E8 deletion/deployment/recovery gates without destructive actions."""

import argparse
import hashlib
import json
import socket
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / ".runtime"
BATCH = ROOT / "project_changes/2026-09-15-e8-ar6-preparation"
ARTIFACTS = BATCH / "artifacts"
TARGET = "doki-e4-20260903-mysql"
NEW_API = "new-api"


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def docker_inspect(name):
    result = subprocess.run(["docker", "inspect", name], capture_output=True, check=True)
    value = json.loads(result.stdout)[0]
    state = value["State"]
    return {
        "id": value["Id"], "name": value["Name"].lstrip("/"), "image": value["Config"].get("Image"),
        "status": state["Status"], "running": state["Running"], "started_at": state.get("StartedAt"),
        "finished_at": state.get("FinishedAt"), "restart_count": value.get("RestartCount", 0),
        "ports": value.get("HostConfig", {}).get("PortBindings", {}),
        "volumes": sorted(value.get("Mounts", [{}])[0].get("Name", "") for _ in [0]) if value.get("Mounts") else [],
    }


def path_inventory(path):
    if not path.exists():
        return {"path": path.relative_to(ROOT).as_posix(), "exists": False, "files": 0, "bytes": 0}
    files = 0
    total = 0
    for item in path.rglob("*"):
        if item.is_symlink() or not item.is_file():
            continue
        files += 1
        total += item.stat().st_size
    return {"path": path.relative_to(ROOT).as_posix(), "exists": True, "files": files, "bytes": total}


def port(port):
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ARTIFACTS / "e8-preparation-20260915.json")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(BATCH.resolve()):
        raise ValueError("E8 preparation evidence must stay in its batch")
    output.parent.mkdir(parents=True, exist_ok=True)
    target = docker_inspect(TARGET)
    new_api = docker_inspect(NEW_API)
    e6e7_preparation = ROOT / "project_changes/2026-09-14-e6-e7-ar5-joint/artifacts/preparation.json"
    e6e7_new_api = json.loads(e6e7_preparation.read_text(encoding="utf-8"))["new_api"]
    backup = RUNTIME / "e6e7-final-target-backup-20260915/target-current.sql"
    historical_decision = ROOT / "project_changes/2026-09-14-e6-e7-ar5-joint/artifacts/closure-decision-20260915.json"
    historical_index = ROOT / "project_changes/2026-09-14-e6-e7-ar5-joint/artifacts/closure-index-20260915.json"
    report = {
        "stage": "E8/AR-6", "status": "preparation_ready_with_gates", "recorded_at": datetime.now(UTC).isoformat(),
        "authorization": "User approved E6/E7 closure and preparation of E8",
        "scope": "Local Windows single instance; prepare-only; no deletion, shutdown, migration, or gate unlock",
        "target": {"expected_name": TARGET, "expected_host": "127.0.0.1", "expected_port": 33427,
                   "expected_database": "doki_e4", "observed": target},
        "new_api": {"observed": new_api, "e6e7_historical_baseline": e6e7_new_api,
                    "historical_delta": {"same_id": new_api["id"] == e6e7_new_api["id"],
                                         "started_at_changed": new_api["started_at"] != e6e7_new_api["started_at"],
                                         "restart_count_changed": new_api["restart_count"] != e6e7_new_api["restart_count"]},
                    "action": "observe only; no configuration, permission, or process change"},
        "service_ports": {str(item): port(item) for item in (18000, 18001, 18020, 18080, 11434, 11451)},
        "historical_e6e7": {
            "decision": {"path": historical_decision.relative_to(ROOT).as_posix(), "sha256": sha(historical_decision)},
            "index": {"path": historical_index.relative_to(ROOT).as_posix(), "sha256": sha(historical_index)},
            "status": json.loads(historical_decision.read_text(encoding="utf-8"))["status"],
        },
        "backup": {"path": backup.relative_to(ROOT).as_posix(), "exists": backup.exists(),
                   "bytes": backup.stat().st_size if backup.exists() else 0,
                   "sha256": sha(backup) if backup.exists() else None,
                   "policy": "retain; do not overwrite during preparation"},
        "preparation_documents": {
            "dependency_map": (BATCH / "dependency-map.md").relative_to(ROOT).as_posix(),
            "runbook": (BATCH / "e8-runbook.md").relative_to(ROOT).as_posix(),
            "plan": (BATCH / "plan.md").relative_to(ROOT).as_posix(),
        },
        "legacy_candidates": [path_inventory(ROOT / relative) for relative in (
            "DjangoUserService", "backend/data/chromadb", "backend/data/extracted_images",
            "backend/data/md5_hex_store", "backend/data/skill_packages", "backend/data/skill_packages/objects",
            "images", "extracted_images", "md5_hex_store", "skill_packages",
        )],
        "disposition": [
            {"item": "Django runtime chain", "state": "retain_until_E8_deployment_smoke_and_rollback_pass", "delete_enabled": False},
            {"item": "Redis correctness dependency",
             "state": "prove_unused_by_business_correctness_then_remove_in_deployment_fixture", "delete_enabled": False},
            {"item": "legacy YAML/Registry/MD5/directory adapters",
             "state": "map_each_reference_then remove_by_allowlist", "delete_enabled": False},
            {"item": "old Chroma generations and filesystem objects",
             "state": "retain_until_SQL_restore_and_rebuild_are_accepted", "delete_enabled": False},
            {"item": "new-api", "state": "excluded_external_resource", "delete_enabled": False},
        ],
        "required_gates": [
            "Fresh target preflight and data-only backup with digest recorded immediately before any cutover",
            "Empty-schema migration, target restore, and populated target restore-forward with FK/digest/audit reconciliation",
            "FastAPI-only install/start/stop/upgrade/rollback/recover runbook exercised on isolated fixtures",
            "Core login/session/Skill/RAG/chat/note/export smoke on empty, restored, and current migrated databases",
            "Measured RPO/RTO and a documented application write pause; no MySQL global read_only or host-wide lock",
            "Separate explicit user approval for each physical deletion and for SKILL-GATE/ARCH-GATE decisions",
        ],
        "blockers": [
            "E8 destructive execution has not been authorized; this artifact records preparation only",
            "Django/Redis/legacy filesystem reference graph and deployment runbook still require implementation and isolated proof",
        ],
        "observations": [
            "Target was restarted before this preparation probe and is currently healthy; its start time is recorded above",
            "new-api is running and was only inspected; its current runtime baseline is recorded separately from historical E6/E7 evidence",
            "All historical containers, volumes, networks, failed inputs, backups, and private credentials remain retained",
        ],
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": report["status"], "output": output.relative_to(ROOT).as_posix(),
                      "target_running": target["running"], "new_api_running": new_api["running"],
                      "deletion_enabled": False}))


if __name__ == "__main__":
    main()
