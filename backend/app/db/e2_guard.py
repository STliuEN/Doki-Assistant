from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from sqlalchemy import Connection, text
from sqlalchemy.engine import make_url

E2_MIGRATION_SWITCH = "I_UNDERSTAND_E2_MIGRATION"
E2_NETWORK = "doki-e2-20260828-net"


class E2GuardError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class E2Target:
    role: str
    host: str
    port: int
    database: str
    container_name: str


@dataclass(frozen=True, slots=True)
class E2MigrationGuard:
    database_url: str
    target: E2Target
    preflight: Mapping[str, Any]


_TARGETS = {
    ("127.0.0.1", 33317, "doki_e2"): E2Target(
        role="source",
        host="127.0.0.1",
        port=33317,
        database="doki_e2",
        container_name="doki-e2-20260828-mysql",
    ),
    ("127.0.0.1", 33318, "doki_e2"): E2Target(
        role="restore",
        host="127.0.0.1",
        port=33318,
        database="doki_e2",
        container_name="doki-e2-20260828-mysql-restore",
    ),
}


def database_url_fingerprint(database_url: str) -> str:
    return hashlib.sha256(database_url.encode("utf-8")).hexdigest()


def approval_token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def parse_e2_target(database_url: str) -> E2Target:
    try:
        url = make_url(database_url)
    except Exception as exc:
        raise E2GuardError("E2_DATABASE_URL is invalid") from exc
    if url.drivername != "mysql+aiomysql":
        raise E2GuardError("E2_DATABASE_URL must use mysql+aiomysql")
    if not url.username or not url.password:
        raise E2GuardError("E2_DATABASE_URL must include a dedicated username and password")
    key = (url.host, url.port, url.database)
    target = _TARGETS.get(key)
    if target is None:
        raise E2GuardError("E2_DATABASE_URL target is outside the approved host/port/database allowlist")
    if dict(url.query).get("charset") != "utf8mb4":
        raise E2GuardError("E2_DATABASE_URL must set charset=utf8mb4")
    return target


def _parse_timestamp(value: object, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise E2GuardError(f"preflight {field_name} is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise E2GuardError(f"preflight {field_name} is invalid") from exc
    if parsed.tzinfo is None:
        raise E2GuardError(f"preflight {field_name} must include a timezone")
    return parsed.astimezone(UTC)


def inspect_e2_container(container_name: str) -> dict[str, Any]:
    result = subprocess.run(
        ["docker", "inspect", container_name],
        capture_output=True,
        check=False,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        raise E2GuardError(f"approved E2 container {container_name!r} is unavailable")
    try:
        items = json.loads(result.stdout)
        item = items[0]
        networks = sorted(item["NetworkSettings"]["Networks"])
        ports = item["NetworkSettings"]["Ports"].get("3306/tcp") or []
        host_ports = sorted(int(entry["HostPort"]) for entry in ports if entry.get("HostIp") in {"127.0.0.1", "::1"})
        return {
            "container_name": item["Name"].lstrip("/"),
            "container_id": item["Id"],
            "image_id": item["Image"],
            "image_reference": item["Config"]["Image"],
            "running": bool(item["State"]["Running"]),
            "networks": networks,
            "host_ports": host_ports,
        }
    except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise E2GuardError("docker inspect returned an invalid E2 container description") from exc


def validate_preflight_record(
    record: Mapping[str, Any],
    *,
    database_url: str,
    approval_token: str,
    purpose: str,
    now: datetime | None = None,
    container_facts: Mapping[str, Any] | None = None,
) -> E2Target:
    target = parse_e2_target(database_url)
    if record.get("schema_version") != 1:
        raise E2GuardError("unsupported E2 preflight schema version")
    if purpose not in record.get("purposes", []):
        raise E2GuardError(f"E2 preflight does not authorize {purpose!r}")
    issued_at = _parse_timestamp(record.get("issued_at"), "issued_at")
    expires_at = _parse_timestamp(record.get("expires_at"), "expires_at")
    checked_at = (now or datetime.now(UTC)).astimezone(UTC)
    if not issued_at <= checked_at < expires_at:
        raise E2GuardError("E2 preflight is not currently valid")
    if (expires_at - issued_at).total_seconds() > 15 * 60:
        raise E2GuardError("E2 preflight lifetime exceeds 15 minutes")
    if record.get("dsn_sha256") != database_url_fingerprint(database_url):
        raise E2GuardError("E2 database URL fingerprint does not match preflight")
    if record.get("approval_token_sha256") != approval_token_fingerprint(approval_token):
        raise E2GuardError("E2 approval token does not match preflight")
    expected_target = {
        "role": target.role,
        "host": target.host,
        "port": target.port,
        "database": target.database,
        "container_name": target.container_name,
    }
    if record.get("target") != expected_target:
        raise E2GuardError("E2 preflight target does not match the approved allowlist")

    facts = container_facts or inspect_e2_container(target.container_name)
    for key in ("container_name", "container_id", "image_id", "image_reference"):
        if record.get("container", {}).get(key) != facts.get(key):
            raise E2GuardError(f"E2 container {key} drifted after preflight")
    if not facts.get("running"):
        raise E2GuardError("E2 container is not running")
    if facts.get("networks") != [E2_NETWORK]:
        raise E2GuardError("E2 container network is outside the approved topology")
    if facts.get("host_ports") != [target.port]:
        raise E2GuardError("E2 container host port is outside the approved topology")
    return target


def load_guard_from_environment(
    purpose: str,
    *,
    environ: Mapping[str, str] | None = None,
    inspector: Callable[[str], Mapping[str, Any]] = inspect_e2_container,
) -> E2MigrationGuard:
    values = environ or os.environ
    if values.get("E2_MIGRATION_ENABLED") != E2_MIGRATION_SWITCH:
        raise E2GuardError("E2 migration switch is not enabled")
    database_url = values.get("E2_DATABASE_URL", "")
    approval_token = values.get("E2_APPROVAL_TOKEN", "")
    preflight_name = values.get("E2_PREFLIGHT_FILE", "")
    if not database_url or not approval_token or not preflight_name:
        raise E2GuardError("E2_DATABASE_URL, E2_APPROVAL_TOKEN and E2_PREFLIGHT_FILE are required")
    preflight_path = Path(preflight_name).resolve()
    if not preflight_path.is_file():
        raise E2GuardError("E2 preflight file does not exist")
    try:
        record = json.loads(preflight_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise E2GuardError("E2 preflight file is invalid") from exc
    target = parse_e2_target(database_url)
    facts = inspector(target.container_name)
    validate_preflight_record(
        record,
        database_url=database_url,
        approval_token=approval_token,
        purpose=purpose,
        container_facts=facts,
    )
    return E2MigrationGuard(database_url=database_url, target=target, preflight=record)


def verify_database_fingerprint(connection: Connection, guard: E2MigrationGuard) -> None:
    row = connection.execute(
        text(
            "SELECT DATABASE(), @@server_uuid, @@session.time_zone, @@session.sql_mode, "
            "@@global.max_allowed_packet, @@session.transaction_isolation"
        )
    ).one()
    database, server_uuid, time_zone, sql_mode, max_packet, isolation = row
    if database != guard.target.database:
        raise E2GuardError("connected database does not match E2 preflight")
    if server_uuid != guard.preflight.get("database", {}).get("server_uuid"):
        raise E2GuardError("MySQL server UUID drifted after E2 preflight")
    if time_zone not in {"+00:00", "UTC"}:
        raise E2GuardError("E2 MySQL session timezone must be UTC")
    if "STRICT_TRANS_TABLES" not in str(sql_mode).split(","):
        raise E2GuardError("E2 MySQL strict SQL mode is required")
    if int(max_packet) < 256 * 1024 * 1024:
        raise E2GuardError("E2 MySQL max_allowed_packet must be at least 256 MiB")
    if str(isolation).upper().replace("_", "-") != "REPEATABLE-READ":
        raise E2GuardError("E2 MySQL default isolation must remain REPEATABLE READ")

