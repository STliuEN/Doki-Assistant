"""Replayable E6E7 replica, backup and fresh identity preflight. No host SQL access."""

import argparse
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
from ops.e5.verify_closure import (  # noqa: E402 - standalone CLI backend path bootstrap
    TARGET,
    TARGET_ID,
    inspect_container,
    protected_state,
    sha_file,
)


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def docker(*args, env=None, data=None):
    value = subprocess.run(["docker", *args], input=data, capture_output=True, env=env)
    if value.returncode:
        raise RuntimeError("Docker operation failed: " + args[0])
    return value.stdout


def sql(name, password, statement, user="root", database=None):
    args = ["exec", "-i", "--env", "MYSQL_PWD", name, "mysql", "-u" + user, "--default-character-set=utf8mb4", "-NB"]
    if database:
        args.append(database)
    return docker(*args, env=dict(os.environ, MYSQL_PWD=password), data=statement.encode("utf-8")).decode("utf-8").strip()


def dump(name, password, user, *, data_only=False):
    flags = [
        "--single-transaction",
        "--skip-lock-tables",
        "--skip-add-locks",
        "--no-tablespaces",
        "--set-gtid-purged=OFF",
        "--hex-blob",
        "--skip-comments",
        "--skip-extended-insert",
        "--order-by-primary",
        "--default-character-set=utf8mb4",
    ]
    if data_only:
        flags.append("--no-create-info")
    return docker("exec", "--env", "MYSQL_PWD", name, "mysqldump", "-u" + user, *flags, "doki_e4", env=dict(os.environ, MYSQL_PWD=password))


def prepare(destination, *, source_directory=None, empty_schema=False):
    destination = destination.resolve()
    if not destination.is_relative_to(ROOT / ".runtime") or destination.exists():
        raise ValueError("Use a new directory under workspace .runtime")
    destination.mkdir(parents=True)
    original = inspect_container(TARGET)
    assert original["Id"] == TARGET_ID and original["State"]["Running"]
    assert original["NetworkSettings"]["Ports"]["3306/tcp"] == [{"HostIp": "127.0.0.1", "HostPort": "33427"}]
    credentials = json.loads((ROOT / ".runtime/e4/live-credentials.json").read_text(encoding="utf-8"))
    before = protected_state()
    source_name, source_password, source_user = TARGET, credentials["target_password"], "doki_e4_app"
    if source_directory is not None:
        environment(source_directory)  # Pins exact replica ID, loopback port and database before backup.
        source = json.loads((source_directory / "credentials.private.json").read_text(encoding="utf-8"))
        source_name, source_password, source_user = source["container"], source["password"], source["username"]
    content = dump(source_name, source_password, source_user)
    assert content.count(b"\n") > 500 and not content.startswith(b"\xef\xbb\xbf")
    backup = destination / "target-current.sql"
    backup.write_bytes(content)
    target_digest = hashlib.sha256(dump(source_name, source_password, source_user, data_only=True)).hexdigest()
    name = "doki-e6e7-accept-" + uuid4().hex[:8]
    private = {
        "container": name,
        "network": name + "-net",
        "volume": name + "-data",
        "root_password": secrets.token_hex(24),
        "password": secrets.token_hex(24),
        "approval_token": secrets.token_hex(24),
        "chroma": str(destination / "chroma"),
        "database": "doki_e4",
        "username": "doki_e6e7_accept",
    }
    save(destination / "credentials.private.json", private)
    # Pin the selected port in HostConfig so Docker restart preserves the endpoint.
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        replica_port = reservation.getsockname()[1]
    assert replica_port not in {3306, 33427}
    docker("network", "create", "--label", "doki.stage=e6e7-acceptance", private["network"])
    docker("volume", "create", "--label", "doki.stage=e6e7-acceptance", private["volume"])
    docker(
        "run",
        "-d",
        "--name",
        name,
        "--label",
        "doki.stage=e6e7-acceptance",
        "--network",
        private["network"],
        "--memory",
        "2g",
        "--cpus",
        "2",
        "-p",
        f"127.0.0.1:{replica_port}:3306",
        "-v",
        private["volume"] + ":/var/lib/mysql",
        "--health-cmd",
        "mysqladmin ping -h 127.0.0.1 --silent",
        "--health-interval",
        "2s",
        "--health-timeout",
        "2s",
        "--health-retries",
        "60",
        "--env",
        "MYSQL_ROOT_PASSWORD",
        "--env",
        "MYSQL_DATABASE",
        "--env",
        "MYSQL_USER",
        "--env",
        "MYSQL_PASSWORD",
        original["Image"],
        env=dict(
            os.environ,
            MYSQL_ROOT_PASSWORD=private["root_password"],
            MYSQL_DATABASE="doki_e4",
            MYSQL_USER=private["username"],
            MYSQL_PASSWORD=private["password"],
        ),
    )
    for _ in range(120):
        try:
            # Require final TCP listener; the image's temporary init server has no TCP.
            docker(
                "exec",
                "--env",
                "MYSQL_PWD",
                name,
                "mysql",
                "--protocol=TCP",
                "-h127.0.0.1",
                "-uroot",
                "-NBe",
                "SELECT 1",
                env=dict(os.environ, MYSQL_PWD=private["root_password"]),
            )
            break
        except RuntimeError:
            time.sleep(1)
    else:
        raise RuntimeError("Replica readiness timeout; retain resources for diagnosis")
    value = inspect_container(name)
    private.update(port=int(value["NetworkSettings"]["Ports"]["3306/tcp"][0]["HostPort"]), container_id=value["Id"], image_id=value["Image"])
    save(destination / "credentials.private.json", private)
    server_uuid = sql(name, private["root_password"], "SELECT @@server_uuid")
    target = {
        "id": name,
        "role": "target",
        "host": "127.0.0.1",
        "port": private["port"],
        "database": "doki_e4",
        "server_uuid": server_uuid,
        "credential_ref": "e6e7-acceptance-app",
        "database_username": private["username"],
        "read_only": False,
        "container_name": name,
        "container_id": value["Id"],
        "image_reference": value["Config"]["Image"],
        "image_id": value["Image"],
        "network": private["network"],
    }
    save(destination / "allowlist.json", {"schema_version": 1, "stage": "E6E7", "targets": [target]})
    if empty_schema:
        assert sql(name, private["root_password"], "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='doki_e4'") == "0"
        migrated = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND,
            env=preflight(destination, ("migrate", "runtime", "validate")),
            capture_output=True,
        )
        (destination / "empty-schema.log").write_bytes(migrated.stdout + migrated.stderr)
        if migrated.returncode:
            raise RuntimeError("Fresh empty schema migration failed; see empty-schema.log")
        revision = sql(name, private["password"], "SELECT version_num FROM alembic_version", private["username"], "doki_e4")
        assert revision == "20260914_0010_e6e7_sql_authority"
        save(destination / "empty-schema.json", {"status": "passed", "revision": revision, "container": name})
    # This destination was created in this invocation and contains no user data.
    docker(
        "exec", "-i", "--env", "MYSQL_PWD", name, "mysql", "-uroot", "doki_e4", env=dict(os.environ, MYSQL_PWD=private["root_password"]), data=content
    )
    restored_digest = hashlib.sha256(dump(name, private["root_password"], "root", data_only=True)).hexdigest()
    assert target_digest == restored_digest
    tables = sql(
        name, private["root_password"], "SELECT table_name FROM information_schema.tables WHERE table_schema='doki_e4' ORDER BY table_name"
    ).splitlines()
    counts = {table: int(sql(name, private["root_password"], "SELECT COUNT(*) FROM `" + table + "`", database="doki_e4")) for table in tables}
    assert protected_state() == before
    save(
        destination / "restore.json",
        {
            "status": "passed",
            "source_container": source_name,
            "empty_schema_passed": empty_schema,
            "backup_sha256": sha_file(backup),
            "backup_bytes": len(content),
            "target_digest": target_digest,
            "restored_digest": restored_digest,
            "table_counts": counts,
            "target": target,
            "new_api_before": before,
            "new_api_after": protected_state(),
            "global_flags": sql(TARGET, credentials["target_password"], "SELECT @@global.read_only, @@global.super_read_only", "doki_e4_app"),
            "resource_policy": "retained; never remove historical resources",
        },
    )
    print(json.dumps({"replica": name, "port": private["port"], "restored": len(counts), "digest_equal": True}), flush=True)


def environment(directory):
    from sqlalchemy import URL

    directory = directory.resolve()
    value = json.loads((directory / "credentials.private.json").read_text(encoding="utf-8"))
    current = inspect_container(value["container"])
    assert value["container"].startswith("doki-e6e7-accept-") and current["Id"] == value["container_id"]
    assert current["NetworkSettings"]["Ports"]["3306/tcp"] == [{"HostIp": "127.0.0.1", "HostPort": str(value["port"])}]
    assert value["port"] not in {3306, 33427}
    url = URL.create(
        "mysql+aiomysql",
        username=value["username"],
        password=value["password"],
        host="127.0.0.1",
        port=value["port"],
        database=value["database"],
        query={"charset": "utf8mb4"},
    )
    env = dict(
        os.environ,
        E4_DATABASE_URL=url.render_as_string(hide_password=False),
        E4_MIGRATION_ENABLED="I_UNDERSTAND_E4_MIGRATION",
        E4_ALLOWLIST_FILE=str(directory / "allowlist.json"),
        E4_CREDENTIAL_REF="e6e7-acceptance-app",
        E4_TARGET_ID=value["container"],
        E4_APPROVAL_TOKEN=value["approval_token"],
        E4_RUNNER_ENABLED="true",
        E5_RAG_ENABLED="true",
        E6E7_ENABLED="true",
        E5_CHROMA_PERSIST_DIRECTORY=value["chroma"],
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        PYTHONUTF8="1",
        OLLAMA_BASE_URL="http://127.0.0.1:11434",
        TEXT_EMBEDDING_MODEL_NAME="qwen3-embedding:0.6b",
        ENV="dev",
        RATE_LIMIT_ENABLED="false",
        JOB_LEASE_SECONDS="12",
        JOB_HEARTBEAT_SECONDS="3",
        JOB_POLL_SECONDS="0.2",
        JOB_SHUTDOWN_DRAIN_SECONDS="3",
    )
    return env


def preflight(directory, purposes=("runtime",)):
    env = environment(directory)
    output = directory.resolve() / ("preflight-" + uuid4().hex[:8] + ".json")
    result = subprocess.run(
        [
            sys.executable,
            str(BACKEND / "scripts/e4_preflight.py"),
            "--output",
            str(output),
            "--purposes",
            *purposes,
            "--issuance-switch",
            "I_UNDERSTAND_E4_PREFLIGHT_ISSUANCE",
        ],
        capture_output=True,
        env=env,
    )
    if result.returncode:
        raise RuntimeError("Fresh E6E7 identity preflight failed: " + result.stdout.decode(errors="replace"))
    env["E4_PREFLIGHT_FILE"] = str(output)
    # Bind code and valid backup to the new E6E7 invocation; shared E4 guard validates exact resources.
    save(
        output.with_suffix(".e6e7.json"),
        {
            "stage": "E6E7",
            "preflight_sha256": sha_file(output),
            "backup_sha256": sha_file(directory / "target-current.sql"),
            "purposes": list(purposes),
            "code": {str(path.relative_to(ROOT)): sha_file(path) for path in sorted((BACKEND / "app/skills").glob("*.py"))},
        },
    )
    return env


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--source-directory", type=Path)
    parser.add_argument("--empty-schema", action="store_true")
    arguments = parser.parse_args()
    prepare(arguments.directory, source_directory=arguments.source_directory, empty_schema=arguments.empty_schema)
