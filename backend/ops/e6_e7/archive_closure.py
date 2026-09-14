"""Seal fixed E6/E7 evidence; credentials and SQL bodies remain private."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
BATCH = ROOT / "project_changes/2026-09-14-e6-e7-ar5-joint"
PUBLIC = BATCH / "artifacts"
FINAL = ROOT / ".runtime/e6e7-target-closure-20260914"
ACCEPT = ROOT / ".runtime/e6e7-closure-acceptance-20260914"
RESTORE = ROOT / ".runtime/e6e7-sql-only-restore-20260914"
HTTP = ROOT / ".runtime/e6e7-http-final-20260915"
BACKUP = ROOT / ".runtime/e6e7-final-target-backup-20260915"
INDEX = PUBLIC / "closure-index-20260915.json"
DECISION = PUBLIC / "closure-decision-20260915.json"
SOURCES = {
    "target": FINAL / "target-closure.json",
    "target-audit": FINAL / "target-final-audit.json",
    "acceptance": ACCEPT / "closure-acceptance.json",
    "empty-schema": RESTORE / "empty-schema.json",
    "restore": RESTORE / "restore.json",
    "restore-sql": RESTORE / "restore-verified-sql.json",
    "restore-chroma": RESTORE / "restore-verified-chroma.json",
    "rebuild": RESTORE / "rebuild.json",
    "http": HTTP / "http-closure.json",
    "restart-sql": HTTP / "restore-verified-sql.json",
    "target-backup": BACKUP / "restore.json",
}


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def receipt(path):
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path), "bytes": path.stat().st_size}


def validate_reports():
    reports = {name: read(path) for name, path in SOURCES.items()}
    assert all(item["status"] == "passed" for item in reports.values())
    for name, count in (("acceptance", 10), ("http", 7)):
        assert len(reports[name]["checks"]) == count and all(item["passed"] for item in reports[name]["checks"])
    target = reports["target-audit"]
    assert target["counts"]["skill_imports"] == 0
    assert target["stable_legacy_packages_verified"] == 10
    assert sum(item["status"] == "enabled" and item["grant_valid"] for item in target["skills"]) == 8
    assert target["administrators"]["distinct_ids"] and target["administrators"]["security_password_verified"]
    baseline = read(PUBLIC / "preparation.json")["new_api"]
    assert target["new_api"] == baseline and target["mysql_global_flags"] == [0, 0]
    assert reports["target"]["media"]["rolled_back"]
    for name, directory in (("restore", RESTORE), ("target-backup", BACKUP)):
        report = reports[name]
        assert report["target_digest"] == report["restored_digest"] and len(report["table_counts"]) == 42
        assert sha(directory / "target-current.sql") == report["backup_sha256"]
        assert report["new_api_before"] == report["new_api_after"] == baseline
    assert reports["restore"]["empty_schema_passed"]
    for name in ("restore-sql", "restore-chroma", "restart-sql"):
        report = reports[name]
        assert all(report[key] for key in (
            "sql_only", "package_raw_canonical_resource_verified", "source_image_download_batch_verified",
            "revoked_run_denied", "authorization_audit_verified",
        ))
        assert report["legacy_package_path"] == "absent" and report["foreign_keys"] >= 9
    chroma = reports["restore-chroma"]
    assert chroma["chroma_validation"] and chroma["missing_chroma_fail_closed"] == "chroma_read_failed"
    assert sorted(row["chunks"] for row in chroma["chroma"]) == [0, 0, 0, 1, 13, 58]
    assert all(row["status"] == "ready" for row in reports["rebuild"]["owners"])
    assert reports["http"]["new_api_before"] == reports["http"]["new_api_after"] == baseline
    assert read(FINAL / "browser-login.json")["loginSucceeded"]
    return reports


def junit(path, expected):
    suites = ET.parse(path).getroot().iter("testsuite")
    totals = {key: 0 for key in ("tests", "failures", "errors", "skipped")}
    for suite in suites:
        for key in totals:
            totals[key] += int(suite.get(key, "0"))
    assert totals == {"tests": expected, "failures": 0, "errors": 0, "skipped": 0}, path.name
    return totals | {"evidence": receipt(path)}


def live_check():
    private = read(FINAL / "security-admin.private.json")
    with httpx.Client(base_url="http://127.0.0.1:18000", timeout=30, trust_env=False) as client:
        def get(path):
            response = client.get(path)
            assert response.status_code == 200, path
            return response.json()["data"]

        ready, runner = get("/health/ready"), get("/health/runner")
        assert ready["status"] == "ok" and ready["dependencies"]["chroma_projection"]["status"] == "owner_scoped"
        assert runner["status"] == "running" and runner["concurrency"] == 1 and runner["last_error"] is None
        response = client.post("/user/login/", json={key: private[key] for key in ("username", "password")})
        assert response.status_code == 200, "Security administrator HTTP login failed"
        data = response.json()["data"]
        assert data["user"]["username"] == private["username"]
        client.headers["Authorization"] = "Bearer " + data["token"]
        try:
            skill = next(item for item in read(SOURCES["target-audit"])["skills"] if item["status"] == "enabled")
            permission = get("/skills/" + skill["skill_id"] + "/authorization")
            assert permission["can_decide"] is True and permission["can_request"] is False
        finally:
            assert client.post("/user/logout/").status_code == 200
    return {
        "status": "passed", "recorded_at": datetime.now(UTC).isoformat(), "ready": ready, "runner": runner,
        "security_admin": private["username"], "login_verified": True, "can_decide": True, "can_request": False,
        "verification_session_logged_out": True,
    }


def command(args, cwd=ROOT):
    env = os.environ.copy()
    env["PATH"] = "C:/nvm4w/nodejs;" + env.get("PATH", "")
    result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, timeout=120)
    row = {
        "command": subprocess.list2cmdline([str(arg) for arg in args]), "cwd": cwd.relative_to(ROOT).as_posix(),
        "exit_code": result.returncode, "output": (result.stdout + result.stderr).decode("utf-8", errors="replace"),
    }
    assert result.returncode == 0, row
    print("passed: " + row["command"], flush=True)
    return row


def check_secrets():
    secrets = set()

    def extract(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if re.search(r"password|secret|(?:^|_)token$", key, re.I) and isinstance(item, str) and len(item) >= 8:
                    secrets.add(item)
                else:
                    extract(item)
        elif isinstance(value, list):
            for item in value:
                extract(item)

    for directory in (FINAL, ACCEPT, RESTORE, HTTP, BACKUP, ROOT / ".runtime/e6e7-target-20260914"):
        for path in directory.glob("*.private.json"):
            extract(read(path))
    paths = list(BATCH.rglob("*.json")) + list(BATCH.rglob("*.md"))
    paths += list((ROOT / "backend/ops/e6_e7").glob("*.py"))
    for path in paths:
        content = path.read_text(encoding="utf-8-sig")
        assert not any(value in content for value in secrets), "Private value in " + path.name
        assert not re.search(r"eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}", content), "JWT in " + path.name


def seal_index():
    changed = set()
    for args in (["git", "-c", "core.autocrlf=false", "diff", "--name-only"], ["git", "ls-files", "--others", "--exclude-standard"]):
        changed.update(subprocess.check_output(args, cwd=ROOT).decode("utf-8").splitlines())
    files = {ROOT / name for name in changed if name.startswith(("backend/", "front/", "docs/")) and (ROOT / name).is_file()}
    files.update(BATCH.glob("*.md"))
    files.update((ROOT / "backend/ops/e6_e7").glob("*.*"))
    originals = list(SOURCES.values()) + [FINAL / "browser-login.json", FINAL / "backend-final.xml", FINAL / "frontend-final.xml"]
    originals += [RESTORE / "target-current.sql", BACKUP / "target-current.sql", HTTP / "http-sse-events.json"]
    originals += [ROOT / ".runtime/e6e7-target-20260914/target-before-e6e7.sql"]
    artifacts = sorted(path for path in PUBLIC.rglob("*") if path.is_file() and path != INDEX)
    save(INDEX, {
        "stage": "E6E7", "status": "closed", "recorded_at": datetime.now(UTC).isoformat(),
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip(),
        "working_tree": "Uncommitted accumulated E5/E6/E7 changes; file hashes describe the tested workspace",
        "current_files": [receipt(path) for path in sorted(files)],
        "artifacts": [receipt(path) for path in artifacts],
        "private_source_receipts": [receipt(path) for path in originals],
        "privacy": "No credential file or SQL body copied; private sources recorded by path/hash/bytes only",
        "history": "Preparation index and early final-decision remain historical; this index excludes its own hash",
    })


def verify():
    for group in ("current_files", "artifacts", "private_source_receipts"):
        for row in read(INDEX)[group]:
            assert receipt(ROOT / row["path"]) == row, row["path"]
    assert read(DECISION)["status"] == read(INDEX)["status"] == "closed"
    check_secrets()
    print(json.dumps({"verified": True, "stage": "E6E7", "status": "closed"}))


def collect():
    reports = validate_reports()
    for name, value in reports.items():
        save(PUBLIC / ("closure-" + name + "-20260915.json"), value)
    save(PUBLIC / "closure-browser-login-20260915.json", read(FINAL / "browser-login.json"))
    browser = PUBLIC / "closure-browser"
    browser.mkdir(exist_ok=True)
    for name in ("e6e7-security-admin.png", "e6e7-security-authorization.png"):
        shutil.copyfile(ROOT / "output/playwright" / name, browser / name)
    checks = {"status": "passed", "backend": junit(FINAL / "backend-final.xml", 539),
              "frontend": junit(FINAL / "frontend-final.xml", 29), "checks": []}
    commands = [
        ([str(ROOT / "backend/.venv/Scripts/ruff.exe"), "check", "backend/ops/e6_e7", "backend/app/router/health.py",
          "backend/app/services/agent_run_service.py", "backend/tests/test_e6_e7_health.py", "backend/tests/test_e4_business_authority.py"], ROOT),
        ([sys.executable, "-m", "compileall", "-q", "backend/app", "backend/ops/e6_e7", "backend/alembic", "backend/tests"], ROOT),
        (["git", "diff", "--check"], ROOT),
        (["C:/nvm4w/nodejs/npm.cmd", "run", "lint"], ROOT / "front"),
        (["C:/nvm4w/nodejs/npm.cmd", "run", "build"], ROOT / "front"),
    ]
    for args, cwd in commands:
        checks["checks"].append(command(args, cwd))
    save(PUBLIC / "closure-live-20260915.json", live_check())
    checks["checks"].append(command([sys.executable, "-X", "utf8", "backend/ops/e6_e7/target_audit.py", str(FINAL)]))
    save(PUBLIC / "closure-target-audit-20260915.json", read(SOURCES["target-audit"]))
    save(PUBLIC / "closure-checks-20260915.json", checks)
    verdict = {
        "stage": "E6E7/AR-5", "status": "closed", "closed_at": datetime.now(UTC).isoformat(),
        "scope": "Local Windows single instance, SQL authority, A/limited-B Skills, runner concurrency 1",
        "authorization": "User requested completing remaining blockers and creating a new administrator using their name",
        "acceptance": {"JV%02d" % number: "passed" for number in range(1, 10)},
        "remaining_in_scope_blockers": [], "waivers": [], "backend_passed": 539, "frontend_passed": 29,
        "target": "127.0.0.1:33427/doki_e4", "schema": "20260914_0010_e6e7_sql_authority",
        "target_counts": read(SOURCES["target-audit"])["counts"], "enabled_skills": 8,
        "disabled_unsupported": ["mcp-smoke-test", "public-info-lookup"],
        "security_admin": "STliuEN-security-admin", "human_reviewers_claimed": 1,
        "role_boundary": "Distinct application identities; not two independently reviewing humans",
        "evidence_matrix": "../contracts.md", "review": "../closure-review.md",
        "supersedes": "e6-e7-final-decision.json (historical incomplete report; imports count corrected to zero)",
        "new_api_unchanged": True, "mysql_global_flags": [0, 0], "legacy_inputs_retained": True,
        "excluded": ["E8", "physical deletion", "C/scripts/external MCP", "production deployment and RPO/RTO"],
        "frozen": ["SKILL-GATE", "ARCH-GATE", "product work packages 7-10"],
        "limitations": ["Detailed coverage boundaries in contracts.md", "Synthetic fixtures on real SQL/model",
                        "Grants expire in about 30 days; renewal requires another approval", "Historical failed attempts retained"],
    }
    save(DECISION, verdict)
    seal_index()
    try:
        checks["checks"].append(command(["powershell", "-NoProfile", "-File", "scripts/check-docs.ps1"]))
        save(PUBLIC / "closure-checks-20260915.json", checks)
        seal_index()
        verify()
    except Exception:
        save(DECISION, verdict | {"status": "verification_failed"})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    verify() if args.verify else collect()
