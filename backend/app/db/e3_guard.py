from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping

from sqlalchemy import Connection, text
from sqlalchemy.engine import make_url

E3_MIGRATION_SWITCH = "I_UNDERSTAND_E3_MIGRATION"
E3_PREFLIGHT_ISSUANCE_SWITCH = "I_UNDERSTAND_E3_PREFLIGHT_ISSUANCE"
E3_NETWORK = "doki-e3-20260831-net"
E3_PREFLIGHT_MAX_LIFETIME_SECONDS = 15 * 60
E3_PREFLIGHT_PURPOSES = frozenset({"migrate", "runtime", "import", "restore", "restore-forward"})
_E3_DATABASE_QUERY = {"charset": "utf8mb4"}
_NON_DEDICATED_DATABASE_USERS = {"root", "mysql"}


class E3GuardError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class E3Target:
    role: str
    host: str
    port: int
    database: str
    container_name: str


@dataclass(frozen=True, slots=True)
class E3MigrationGuard:
    database_url: str
    target: E3Target
    preflight: Mapping[str, Any]


_TARGETS = {
    ("127.0.0.1", 33327, "doki_e3"): E3Target(
        role="target",
        host="127.0.0.1",
        port=33327,
        database="doki_e3",
        container_name="doki-e3-20260831-mysql",
    ),
    ("127.0.0.1", 33328, "doki_e3"): E3Target(
        role="restore",
        host="127.0.0.1",
        port=33328,
        database="doki_e3",
        container_name="doki-e3-20260831-mysql-restore",
    ),
}


def database_url_fingerprint(database_url: str) -> str:
    return hashlib.sha256(database_url.encode("utf-8")).hexdigest()


def approval_token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def parse_e3_target(database_url: str) -> E3Target:
    if not isinstance(database_url, str) or not database_url:
        raise E3GuardError("E3_DATABASE_URL is invalid")
    try:
        url = make_url(database_url)
    except Exception as exc:
        raise E3GuardError("E3_DATABASE_URL is invalid") from exc
    if url.drivername != "mysql+aiomysql":
        raise E3GuardError("E3_DATABASE_URL must use mysql+aiomysql")
    if not url.username or not url.password or url.username.casefold() in _NON_DEDICATED_DATABASE_USERS:
        raise E3GuardError("E3_DATABASE_URL must use a dedicated application username")
    target = _TARGETS.get((url.host, url.port, url.database))
    if target is None:
        raise E3GuardError("E3_DATABASE_URL target is outside the E3 allowlist")
    if dict(url.query) != _E3_DATABASE_QUERY:
        raise E3GuardError("E3_DATABASE_URL query must be exactly charset=utf8mb4")
    return target


def e3_target_record(target: E3Target) -> dict[str, object]:
    return {
        "role": target.role,
        "host": target.host,
        "port": target.port,
        "database": target.database,
        "container_name": target.container_name,
    }


def inspect_e3_container(container_name: str) -> dict[str, Any]:
    result = subprocess.run(["docker", "inspect", container_name], capture_output=True, check=False, text=True, timeout=15)
    if result.returncode != 0:
        raise E3GuardError(f"approved E3 container {container_name!r} is unavailable")
    try:
        item = json.loads(result.stdout)[0]
        networks = sorted(item["NetworkSettings"]["Networks"])
        ports = item["NetworkSettings"]["Ports"].get("3306/tcp") or []
        host_ports = sorted(int(entry["HostPort"]) for entry in ports if entry.get("HostIp") in {"127.0.0.1", "::1"})
        return {
            "container_name": item["Name"].lstrip("/"),
            "container_id": item["Id"],
            "image_id": item["Image"],
            "image_reference": item["Config"]["Image"],
            "running": bool(item["State"]["Running"]),
            "healthy": (item.get("State", {}).get("Health") or {}).get("Status") == "healthy",
            "networks": networks,
            "host_ports": host_ports,
        }
    except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise E3GuardError("docker inspect returned an invalid E3 container description") from exc


def _validate_container(target: E3Target, facts: Mapping[str, Any]) -> dict[str, object]:
    if not isinstance(facts, Mapping):
        raise E3GuardError("E3 container inspection facts are invalid")
    if facts.get("container_name") != target.container_name or facts.get("running") is not True:
        raise E3GuardError("E3 container name or running state is invalid")
    if facts.get("healthy") is not True:
        raise E3GuardError("E3 container health check is not green")
    if facts.get("networks") != [E3_NETWORK] or facts.get("host_ports") != [target.port]:
        raise E3GuardError("E3 container network or host port is outside the allowlist")
    normalized: dict[str, object] = {}
    for key in ("container_name", "container_id", "image_id", "image_reference"):
        value = facts.get(key)
        if not isinstance(value, str) or not value:
            raise E3GuardError(f"E3 container {key} is invalid")
        normalized[key] = value
    if normalized["image_reference"] != "mysql:8.4":
        raise E3GuardError("E3 container image must be mysql:8.4")
    return normalized


def _validate_purposes(purposes: object) -> tuple[str, ...]:
    if not isinstance(purposes, list) or not all(isinstance(item, str) for item in purposes):
        raise E3GuardError("E3 preflight purposes must be a list of strings")
    if not purposes or len(set(purposes)) != len(purposes):
        raise E3GuardError("E3 preflight purposes must be non-empty and unique")
    if any(item not in E3_PREFLIGHT_PURPOSES for item in purposes):
        raise E3GuardError("E3 preflight contains an unsupported purpose")
    return tuple(purposes)


def _validate_server_uuid(database_facts: object) -> str:
    if not isinstance(database_facts, Mapping):
        raise E3GuardError("E3 preflight database facts are missing")
    server_uuid = database_facts.get("server_uuid")
    if not isinstance(server_uuid, str) or not server_uuid.strip():
        raise E3GuardError("E3 preflight database server_uuid must be a non-empty string")
    return server_uuid


def inspect_database_fingerprint(connection: Connection, target: E3Target) -> dict[str, str]:
    try:
        row = connection.execute(
            text(
                "SELECT DATABASE(), @@server_uuid, @@session.time_zone, @@session.sql_mode, "
                "@@global.max_allowed_packet, @@session.transaction_isolation"
            )
        ).one()
    except Exception as exc:
        raise E3GuardError("unable to inspect E3 database fingerprint") from exc
    database, server_uuid, time_zone, sql_mode, max_packet, isolation = row
    if database != target.database or not isinstance(server_uuid, str) or not server_uuid.strip():
        raise E3GuardError("E3 database identity is invalid")
    if time_zone not in {"+00:00", "UTC"}:
        raise E3GuardError("E3 MySQL session timezone must be UTC")
    if "STRICT_TRANS_TABLES" not in {item.strip().upper() for item in str(sql_mode).split(",")}:
        raise E3GuardError("E3 MySQL strict SQL mode is required")
    try:
        packet_bytes = int(max_packet)
    except (TypeError, ValueError) as exc:
        raise E3GuardError("E3 MySQL max_allowed_packet is invalid") from exc
    if packet_bytes < 256 * 1024 * 1024:
        raise E3GuardError("E3 MySQL max_allowed_packet must be at least 256 MiB")
    if str(isolation).upper().replace("_", "-") != "REPEATABLE-READ":
        raise E3GuardError("E3 MySQL isolation must remain REPEATABLE READ")
    return {"server_uuid": server_uuid}


def build_e3_preflight_record(
    *,
    database_url: str,
    approval_token: str,
    purposes: list[str],
    container_facts: Mapping[str, Any],
    database_facts: Mapping[str, Any],
    issued_at: datetime,
    lifetime_seconds: int = E3_PREFLIGHT_MAX_LIFETIME_SECONDS,
) -> dict[str, Any]:
    target = parse_e3_target(database_url)
    if not isinstance(approval_token, str) or not approval_token:
        raise E3GuardError("E3 approval token is required")
    normalized_purposes = _validate_purposes(purposes)
    if not isinstance(issued_at, datetime) or issued_at.tzinfo is None:
        raise E3GuardError("E3 preflight issued_at must include timezone")
    if not isinstance(lifetime_seconds, int) or not 0 < lifetime_seconds <= E3_PREFLIGHT_MAX_LIFETIME_SECONDS:
        raise E3GuardError("E3 preflight lifetime is invalid")
    container = _validate_container(target, container_facts)
    server_uuid = _validate_server_uuid(database_facts)
    issued = issued_at.astimezone(UTC)
    return {
        "schema_version": 1,
        "issued_at": issued.isoformat(),
        "expires_at": (issued + timedelta(seconds=lifetime_seconds)).isoformat(),
        "purposes": list(normalized_purposes),
        "dsn_sha256": database_url_fingerprint(database_url),
        "approval_token_sha256": approval_token_fingerprint(approval_token),
        "target": e3_target_record(target),
        "container": container,
        "database": {"server_uuid": server_uuid},
    }


async def issue_e3_preflight_record(
    *,
    database_url: str,
    approval_token: str,
    purposes: list[str],
    issuance_switch: str,
    lifetime_seconds: int = E3_PREFLIGHT_MAX_LIFETIME_SECONDS,
    inspector: Callable[[str], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if issuance_switch != E3_PREFLIGHT_ISSUANCE_SWITCH:
        raise E3GuardError("E3 preflight issuance switch is not enabled")
    _validate_purposes(purposes)
    if not isinstance(lifetime_seconds, int) or not 0 < lifetime_seconds <= E3_PREFLIGHT_MAX_LIFETIME_SECONDS:
        raise E3GuardError("E3 preflight lifetime is invalid")
    target = parse_e3_target(database_url)
    inspect_container = inspector or inspect_e3_container
    container_facts = inspect_container(target.container_name)
    _validate_container(target, container_facts)

    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(database_url, pool_size=1, max_overflow=0, echo=False)
    try:
        async with engine.connect() as connection:
            database_facts = await connection.run_sync(lambda sync: inspect_database_fingerprint(sync, target))
    finally:
        await engine.dispose()
    return build_e3_preflight_record(
        database_url=database_url,
        approval_token=approval_token,
        purposes=purposes,
        container_facts=container_facts,
        database_facts=database_facts,
        issued_at=datetime.now(UTC),
        lifetime_seconds=lifetime_seconds,
    )


def _parse_timestamp(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise E3GuardError(f"preflight {name} is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise E3GuardError(f"preflight {name} is invalid") from exc
    if parsed.tzinfo is None:
        raise E3GuardError(f"preflight {name} must include timezone")
    return parsed.astimezone(UTC)


def validate_preflight_record(
    record: Mapping[str, Any],
    *,
    database_url: str,
    approval_token: str,
    purpose: str,
    now: datetime | None = None,
    container_facts: Mapping[str, Any] | None = None,
    container_inspector: Callable[[str], Mapping[str, Any]] | None = None,
) -> E3Target:
    if not isinstance(record, Mapping):
        raise E3GuardError("E3 preflight record must be a JSON object")
    target = parse_e3_target(database_url)
    if record.get("schema_version") != 1:
        raise E3GuardError("unsupported E3 preflight schema version")
    purposes = _validate_purposes(record.get("purposes"))
    if not isinstance(purpose, str) or purpose not in E3_PREFLIGHT_PURPOSES:
        raise E3GuardError("E3 preflight purpose is unsupported")
    if purpose not in purposes:
        raise E3GuardError("E3 preflight does not authorize this purpose")
    issued_at = _parse_timestamp(record.get("issued_at"), "issued_at")
    expires_at = _parse_timestamp(record.get("expires_at"), "expires_at")
    checked_at = (now or datetime.now(UTC)).astimezone(UTC)
    if not issued_at <= checked_at < expires_at or (expires_at - issued_at).total_seconds() > E3_PREFLIGHT_MAX_LIFETIME_SECONDS:
        raise E3GuardError("E3 preflight is not currently valid")
    if record.get("dsn_sha256") != database_url_fingerprint(database_url) or record.get("approval_token_sha256") != approval_token_fingerprint(
        approval_token
    ):
        raise E3GuardError("E3 preflight fingerprint does not match")
    expected_target = e3_target_record(target)
    target_record = record.get("target")
    if not isinstance(target_record, Mapping) or target_record != expected_target:
        raise E3GuardError("E3 preflight target is outside the allowlist")
    _validate_server_uuid(record.get("database"))
    inspector = container_inspector or inspect_e3_container
    facts = container_facts if container_facts is not None else inspector(target.container_name)
    normalized = _validate_container(target, facts)
    recorded = record.get("container")
    if not isinstance(recorded, Mapping) or any(recorded.get(key) != normalized[key] for key in normalized):
        raise E3GuardError("E3 container drifted after preflight")
    return target


def load_guard_from_environment(
    purpose: str, *, environ: Mapping[str, str] | None = None, inspector: Callable[[str], Mapping[str, Any]] | None = None
) -> E3MigrationGuard:
    values = environ if environ is not None else os.environ
    if values.get("E3_MIGRATION_ENABLED") != E3_MIGRATION_SWITCH:
        raise E3GuardError("E3 migration switch is not enabled")
    database_url = values.get("E3_DATABASE_URL", "")
    approval_token = values.get("E3_APPROVAL_TOKEN", "")
    preflight_name = values.get("E3_PREFLIGHT_FILE", "")
    if not database_url or not approval_token or not preflight_name:
        raise E3GuardError("E3_DATABASE_URL, E3_APPROVAL_TOKEN and E3_PREFLIGHT_FILE are required")
    preflight_path = Path(preflight_name).resolve()
    try:
        record = json.loads(preflight_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise E3GuardError("E3 preflight file is invalid") from exc
    target = validate_preflight_record(
        record, database_url=database_url, approval_token=approval_token, purpose=purpose, container_inspector=inspector
    )
    return E3MigrationGuard(database_url=database_url, target=target, preflight=record)


def verify_database_fingerprint(connection: Connection, guard: E3MigrationGuard) -> None:
    expected = guard.preflight.get("database", {}).get("server_uuid") if isinstance(guard.preflight.get("database"), Mapping) else None
    actual = inspect_database_fingerprint(connection, guard.target)
    if actual["server_uuid"] != expected:
        raise E3GuardError("E3 MySQL server UUID drifted after preflight")
