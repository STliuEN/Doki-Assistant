"""Restore a binary E5 dump to a fresh, unexposed MySQL container.

No target DDL/DML, host SQL connection, existing volume reuse or deletion.
Credentials are passed through environment names, never shell interpolation.
Run from the repository root using backend/.venv/Scripts/python.exe.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import time


def docker(*args, env=None, stdin=None):
    result = subprocess.run(["docker", *args], env=env, stdin=stdin, capture_output=True)
    if result.returncode:
        raise RuntimeError(f"Docker operation failed ({args[0]}): " + result.stderr.decode(errors="replace")[:600])
    return result.stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dump", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    content = args.dump.read_bytes()
    if content.count(b"\n") < 100 or not content.startswith(b"-- MySQL dump"):
        raise ValueError("Not a validated binary MySQL dump")
    target = "doki-e4-20260903-mysql"
    baseline = json.loads(docker("inspect", target))[0]
    if baseline["Id"] != "35efc06e8a3b377ace2d9ac7e99f9d78ceb8c9a7a73464cc23701413f1d37182":
        raise ValueError("Target identity changed")
    protected = json.loads(docker("inspect", "new-api"))[0]
    suffix = secrets.token_hex(4)
    name = "doki-e5-restore-" + suffix
    volume = name + "-data"
    env = dict(os.environ, MYSQL_ROOT_PASSWORD=secrets.token_hex(32))
    docker("volume", "create", "--label", "doki.stage=e5-restore", volume)
    docker("run", "--name", name, "--network", "none", "--memory", "2g", "--cpus", "2",
           "--label", "doki.stage=e5-restore", "--env", "MYSQL_ROOT_PASSWORD",
           "--env", "MYSQL_DATABASE=doki_e4", "--mount", f"type=volume,src={volume},dst=/var/lib/mysql",
           "-d", baseline["Image"], env=env)
    credential_path = args.output.with_suffix(".private.json")
    credential_path.write_text(json.dumps({"container": name, "root_password": env["MYSQL_ROOT_PASSWORD"]}), encoding="utf-8")
    exec_env = dict(os.environ, MYSQL_PWD=env["MYSQL_ROOT_PASSWORD"])
    # The temporary initialization server uses port 0. Require the final TCP server.
    deadline = time.monotonic() + 120
    while True:
        probe = subprocess.run(["docker", "exec", "--env", "MYSQL_PWD", name, "mysql", "-uroot", "-h127.0.0.1",
                                "-NBe", "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name='doki_e4'"],
                               env=exec_env, capture_output=True)
        if probe.returncode == 0 and probe.stdout.strip() == b"1":
            break
        if time.monotonic() > deadline:
            raise RuntimeError("Independent restore server initialization timed out; preserve volume")
        time.sleep(1)
    with args.dump.open("rb") as dump_file:
        docker("exec", "-i", "--env", "MYSQL_PWD", name, "mysql", "-uroot", "--binary-mode=1", "doki_e4",
               stdin=dump_file, env=exec_env)
    def query(container, sql, env, user):
        return docker("exec", "--env", "MYSQL_PWD", container, "mysql", "-u" + user, "-NBe", sql, env=env).decode().strip()
    tables = query(name, "SELECT table_name FROM information_schema.tables WHERE table_schema='doki_e4' ORDER BY table_name", exec_env, "root").splitlines()
    credentials = json.loads(Path(".runtime/e4/live-credentials.json").read_text(encoding="utf-8"))
    target_env = dict(os.environ, MYSQL_PWD=credentials["target_password"])
    counts = {}
    for table in tables:
        if not table.replace("_", "").isalnum():
            raise ValueError("Unexpected table name")
        sql = f"SELECT COUNT(*) FROM doki_e4.`{table}`"
        original = int(query(target, sql, target_env, "doki_e4_app"))
        restored = int(query(name, sql, exec_env, "root"))
        if original != restored:
            raise ValueError("Row count mismatch in " + table)
        counts[table] = restored
    flags = ["--single-transaction", "--skip-lock-tables", "--skip-add-locks", "--no-tablespaces",
             "--set-gtid-purged=OFF", "--hex-blob", "--skip-comments", "--skip-extended-insert", "--order-by-primary", "--no-create-info"]
    def data_digest(container, env, user):
        data = docker("exec", "--env", "MYSQL_PWD", container, "mysqldump", "-u" + user, *flags, "doki_e4", env=env)
        return hashlib.sha256(data).hexdigest()
    target_digest = data_digest(target, target_env, "doki_e4_app")
    restored_digest = data_digest(name, exec_env, "root")
    if target_digest != restored_digest:
        raise ValueError("Restored SQL data differs from target")
    current = json.loads(docker("inspect", "new-api"))[0]
    if (current["Id"], current["State"]["StartedAt"], current["RestartCount"]) != (protected["Id"], protected["State"]["StartedAt"], protected["RestartCount"]):
        raise ValueError("new-api runtime identity changed")
    record = {"status": "passed", "dump": str(args.dump), "dump_sha256": hashlib.sha256(content).hexdigest(),
              "dump_newlines": content.count(b"\n"), "restore_container": name, "restore_volume": volume,
              "schema_revision": query(name, "SELECT version_num FROM doki_e4.alembic_version", exec_env, "root"),
              "table_counts": counts, "target_data_digest": target_digest, "restored_data_digest": restored_digest,
              "new_api_unchanged": True, "target_global_flags_observed": query(target, "SELECT @@global.read_only, @@global.super_read_only", target_env, "doki_e4_app")}
    args.output.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in record.items() if k != "table_counts"}), flush=True)


if __name__ == "__main__":
    main()
