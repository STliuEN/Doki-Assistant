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

E2_MIGRATION_SWITCH = "I_UNDERSTAND_E2_MIGRATION"
E2_PREFLIGHT_ISSUANCE_SWITCH = "I_UNDERSTAND_E2_PREFLIGHT_ISSUANCE"
E2_NETWORK = "doki-e2-20260828-net"
E2_PREFLIGHT_MAX_LIFETIME_SECONDS = 15 * 60
E2_PREFLIGHT_PURPOSES = frozenset({"dump", "inventory", "migrate", "restore", "restore-forward", "runner"})
_E2_DATABASE_QUERY = {"charset": "utf8mb4"}
_NON_DEDICATED_DATABASE_USERS = {"root"}


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
    if not isinstance(database_url, str) or not database_url:
        raise E2GuardError("E2_DATABASE_URL is invalid")
    try:
        url = make_url(database_url)
    except Exception as exc:
        raise E2GuardError("E2_DATABASE_URL is invalid") from exc
    if url.drivername != "mysql+aiomysql":
        raise E2GuardError("E2_DATABASE_URL must use mysql+aiomysql")
    if not url.username or not url.password:
        raise E2GuardError("E2_DATABASE_URL must include a dedicated username and password")
    if url.username.casefold() in _NON_DEDICATED_DATABASE_USERS:
        raise E2GuardError("E2_DATABASE_URL must not use a privileged shared database username")
    key = (url.host, url.port, url.database)
    target = _TARGETS.get(key)
    if target is None:
        raise E2GuardError("E2_DATABASE_URL target is outside the approved host/port/database allowlist")
    if dict(url.query) != _E2_DATABASE_QUERY:
        raise E2GuardError("E2_DATABASE_URL query must be exactly charset=utf8mb4")
    return target


def e2_target_record(target: E2Target) -> dict[str, object]:
    """Return the exact target facts that a preflight record must bind."""

    return {
        "role": target.role,
        "host": target.host,
        "port": target.port,
        "database": target.database,
        "container_name": target.container_name,
    }


def approved_e2_target(role: str) -> E2Target:
    """Return the immutable target definition for a supported E2 role."""

    if role == "source":
        return _TARGETS[("127.0.0.1", 33317, "doki_e2")]
    if role == "restore":
        return _TARGETS[("127.0.0.1", 33318, "doki_e2")]
    raise E2GuardError(f"unsupported E2 target role: {role}")


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


def _validated_container_facts(target: E2Target, facts: Mapping[str, Any]) -> dict[str, object]:
    if not isinstance(facts, Mapping):
        raise E2GuardError("E2 container inspection facts are invalid")
    normalized: dict[str, object] = {}
    for key in ("container_name", "container_id", "image_id", "image_reference"):
        value = facts.get(key)
        if not isinstance(value, str) or not value:
            raise E2GuardError(f"E2 container {key} is invalid")
        normalized[key] = value
    if facts.get("container_name") != target.container_name:
        raise E2GuardError("E2 container name is outside the approved topology")
    if facts.get("running") is not True:
        raise E2GuardError("E2 container is not running")
    if facts.get("networks") != [E2_NETWORK]:
        raise E2GuardError("E2 container network is outside the approved topology")
    if facts.get("host_ports") != [target.port]:
        raise E2GuardError("E2 container host port is outside the approved topology")
    return normalized


def _validated_purposes(purposes: object) -> tuple[str, ...]:
    if not isinstance(purposes, list) or not all(isinstance(item, str) for item in purposes):
        raise E2GuardError("E2 preflight purposes must be a list of strings")
    if not purposes:
        raise E2GuardError("E2 preflight purposes must not be empty")
    if len(set(purposes)) != len(purposes):
        raise E2GuardError("E2 preflight purposes must not contain duplicates")
    if any(item not in E2_PREFLIGHT_PURPOSES for item in purposes):
        raise E2GuardError("E2 preflight contains an unsupported purpose")
    return tuple(purposes)


def _validated_server_uuid(database_facts: Mapping[str, Any]) -> str:
    if not isinstance(database_facts, Mapping):
        raise E2GuardError("E2 preflight database facts are missing")
    server_uuid = database_facts.get("server_uuid")
    if not isinstance(server_uuid, str) or not server_uuid.strip():
        raise E2GuardError("E2 preflight database server_uuid must be a non-empty string")
    return server_uuid


def inspect_database_fingerprint(connection: Connection, target: E2Target) -> dict[str, str]:
    """Read and validate the live immutable database facts for an E2 target."""

    try:
        row = connection.execute(
            text(
                "SELECT DATABASE(), @@server_uuid, @@session.time_zone, @@session.sql_mode, "
                "@@global.max_allowed_packet, @@session.transaction_isolation"
            )
        ).one()
        database, server_uuid, time_zone, sql_mode, max_packet, isolation = row
    except Exception as exc:
        raise E2GuardError("unable to inspect E2 database fingerprint") from exc
    if database != target.database:
        raise E2GuardError("connected database does not match E2 preflight")
    if not isinstance(server_uuid, str) or not server_uuid.strip():
        raise E2GuardError("E2 MySQL server UUID is invalid")
    if time_zone not in {"+00:00", "UTC"}:
        raise E2GuardError("E2 MySQL session timezone must be UTC")
    sql_modes = {item.strip().upper() for item in str(sql_mode).split(",")}
    if "STRICT_TRANS_TABLES" not in sql_modes:
        raise E2GuardError("E2 MySQL strict SQL mode is required")
    try:
        packet_bytes = int(max_packet)
    except (TypeError, ValueError) as exc:
        raise E2GuardError("E2 MySQL max_allowed_packet is invalid") from exc
    if packet_bytes < 256 * 1024 * 1024:
        raise E2GuardError("E2 MySQL max_allowed_packet must be at least 256 MiB")
    if str(isolation).upper().replace("_", "-") != "REPEATABLE-READ":
        raise E2GuardError("E2 MySQL default isolation must remain REPEATABLE READ")
    return {"server_uuid": server_uuid}


def build_e2_preflight_record(
    *,
    database_url: str,
    approval_token: str,
    purposes: list[str],
    container_facts: Mapping[str, Any],
    database_facts: Mapping[str, Any],
    issued_at: datetime,
    lifetime_seconds: int = E2_PREFLIGHT_MAX_LIFETIME_SECONDS,
) -> dict[str, Any]:
    """Build a short-lived E2 preflight record from already-inspected facts."""

    if not isinstance(approval_token, str) or not approval_token:
        raise E2GuardError("E2 approval token is required")
    target = parse_e2_target(database_url)
    normalized_purposes = _validated_purposes(purposes)
    if not isinstance(issued_at, datetime) or issued_at.tzinfo is None:
        raise E2GuardError("preflight issued_at must include a timezone")
    if not isinstance(lifetime_seconds, int) or not 0 < lifetime_seconds <= E2_PREFLIGHT_MAX_LIFETIME_SECONDS:
        raise E2GuardError("E2 preflight lifetime must be between 1 and 900 seconds")
    normalized_issued_at = issued_at.astimezone(UTC)
    normalized_container = _validated_container_facts(target, container_facts)
    server_uuid = _validated_server_uuid(database_facts)
    record: dict[str, Any] = {
        "schema_version": 1,
        "issued_at": normalized_issued_at.isoformat(),
        "expires_at": (normalized_issued_at + timedelta(seconds=lifetime_seconds)).isoformat(),
        "purposes": list(normalized_purposes),
        "dsn_sha256": database_url_fingerprint(database_url),
        "approval_token_sha256": approval_token_fingerprint(approval_token),
        "target": e2_target_record(target),
        "container": normalized_container,
        "database": {"server_uuid": server_uuid},
    }
    validate_preflight_record(
        record,
        database_url=database_url,
        approval_token=approval_token,
        purpose=normalized_purposes[0],
        now=normalized_issued_at,
        container_facts=container_facts,
    )
    return record


async def issue_e2_preflight_record(
    *,
    database_url: str,
    approval_token: str,
    purposes: list[str],
    issuance_switch: str,
    lifetime_seconds: int = E2_PREFLIGHT_MAX_LIFETIME_SECONDS,
    inspector: Callable[[str], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Inspect a named E2 target and issue a record without consulting dotenv."""

    if issuance_switch != E2_PREFLIGHT_ISSUANCE_SWITCH:
        raise E2GuardError("E2 preflight issuance switch is not enabled")
    if not isinstance(approval_token, str) or not approval_token:
        raise E2GuardError("E2 approval token is required")
    _validated_purposes(purposes)
    if not isinstance(lifetime_seconds, int) or not 0 < lifetime_seconds <= E2_PREFLIGHT_MAX_LIFETIME_SECONDS:
        raise E2GuardError("E2 preflight lifetime must be between 1 and 900 seconds")
    target = parse_e2_target(database_url)
    inspect_container = inspector or inspect_e2_container
    container_facts = inspect_container(target.container_name)
    _validated_container_facts(target, container_facts)

    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(database_url, pool_size=1, max_overflow=0, echo=False)
    try:
        async with engine.connect() as connection:
            database_facts = await connection.run_sync(lambda sync: inspect_database_fingerprint(sync, target))
    finally:
        await engine.dispose()
    return build_e2_preflight_record(
        database_url=database_url,
        approval_token=approval_token,
        purposes=purposes,
        container_facts=container_facts,
        database_facts=database_facts,
        issued_at=datetime.now(UTC),
        lifetime_seconds=lifetime_seconds,
    )


def validate_preflight_record(
    record: Mapping[str, Any],
    *,
    database_url: str,
    approval_token: str,
    purpose: str,
    now: datetime | None = None,
    container_facts: Mapping[str, Any] | None = None,
    container_inspector: Callable[[str], Mapping[str, Any]] | None = None,
) -> E2Target:
    if not isinstance(record, Mapping):
        raise E2GuardError("E2 preflight record must be a JSON object")
    target = parse_e2_target(database_url)
    if record.get("schema_version") != 1:
        raise E2GuardError("unsupported E2 preflight schema version")
    purposes = _validated_purposes(record.get("purposes"))
    if not isinstance(purpose, str) or purpose not in E2_PREFLIGHT_PURPOSES:
        raise E2GuardError("E2 preflight purpose is unsupported")
    if purpose not in purposes:
        raise E2GuardError(f"E2 preflight does not authorize {purpose!r}")
    issued_at = _parse_timestamp(record.get("issued_at"), "issued_at")
    expires_at = _parse_timestamp(record.get("expires_at"), "expires_at")
    checked_at = (now or datetime.now(UTC)).astimezone(UTC)
    if not issued_at <= checked_at < expires_at:
        raise E2GuardError("E2 preflight is not currently valid")
    if (expires_at - issued_at).total_seconds() > E2_PREFLIGHT_MAX_LIFETIME_SECONDS:
        raise E2GuardError("E2 preflight lifetime exceeds 15 minutes")
    if record.get("dsn_sha256") != database_url_fingerprint(database_url):
        raise E2GuardError("E2 database URL fingerprint does not match preflight")
    if record.get("approval_token_sha256") != approval_token_fingerprint(approval_token):
        raise E2GuardError("E2 approval token does not match preflight")
    expected_target = e2_target_record(target)
    target_record = record.get("target")
    if not isinstance(target_record, Mapping) or target_record != expected_target:
        raise E2GuardError("E2 preflight target does not match the approved allowlist")
    _validated_server_uuid(record.get("database"))

    inspect_container = container_inspector or inspect_e2_container
    facts = container_facts if container_facts is not None else inspect_container(target.container_name)
    normalized_facts = _validated_container_facts(target, facts)
    container_record = record.get("container")
    if not isinstance(container_record, Mapping):
        raise E2GuardError("E2 preflight container facts are missing")
    for key in ("container_name", "container_id", "image_id", "image_reference"):
        if container_record.get(key) != normalized_facts[key]:
            raise E2GuardError(f"E2 container {key} drifted after preflight")
    return target


def load_guard_from_environment(
    purpose: str,
    *,
    environ: Mapping[str, str] | None = None,
    inspector: Callable[[str], Mapping[str, Any]] | None = None,
) -> E2MigrationGuard:
    values = environ if environ is not None else os.environ
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
    target = validate_preflight_record(
        record,
        database_url=database_url,
        approval_token=approval_token,
        purpose=purpose,
        container_inspector=inspector,
    )
    return E2MigrationGuard(database_url=database_url, target=target, preflight=record)


def verify_database_fingerprint(connection: Connection, guard: E2MigrationGuard) -> None:
    expected_server_uuid = _validated_server_uuid(guard.preflight.get("database"))
    actual = inspect_database_fingerprint(connection, guard.target)
    if actual["server_uuid"] != expected_server_uuid:
        raise E2GuardError("MySQL server UUID drifted after E2 preflight")
