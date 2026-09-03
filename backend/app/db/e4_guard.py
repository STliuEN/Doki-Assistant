"""Explicit E4 database resource allowlist and short-lived preflight guard.

E4 operates across more than one database endpoint.  Consequently the resource
set is supplied by the caller as a JSON document (or mapping), rather than being
hidden in this module or discovered from ``.env``.  This module only validates
identity and authorization facts; it does not start containers or make a
connection unless a caller explicitly injects an inspector.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, TypeAlias

from sqlalchemy import Connection, text
from sqlalchemy.engine import make_url

E4_MIGRATION_SWITCH = "I_UNDERSTAND_E4_MIGRATION"
E4_PREFLIGHT_ISSUANCE_SWITCH = "I_UNDERSTAND_E4_PREFLIGHT_ISSUANCE"
E4_PREFLIGHT_MAX_LIFETIME_SECONDS = 15 * 60
E4_PREFLIGHT_PURPOSES = frozenset(
    {
        "inventory",
        "snapshot",
        "backup",
        "dry-run",
        "migrate",
        "restore",
        "restore-forward",
        "switch",
        "runtime",
        "validate",
    }
)
E4_ROLES = frozenset({"source", "target", "restore"})
_SECRET_FIELD_NAMES = frozenset(
    {
        "api_key",
        "api_key_encrypted",
        "database_url",
        "dsn",
        "password",
        "passwd",
        "secret",
        "token",
    }
)


class E4GuardError(RuntimeError):
    """Raised when an E4 resource or preflight record is not fail-closed safe."""


@dataclass(frozen=True, slots=True)
class E4Target:
    """An exact, allowlisted database identity.

    ``credential_ref`` names a secret-manager entry or other external
    credential handle.  It is deliberately not the credential itself.
    """

    target_id: str
    role: str
    host: str
    port: int
    database: str
    server_uuid: str
    credential_ref: str
    read_only: bool

    @property
    def id(self) -> str:
        """Short alias useful to callers that use ``id`` for resource keys."""

        return self.target_id

    @property
    def name(self) -> str:
        """Compatibility alias for resource names in operational manifests."""

        return self.target_id


@dataclass(frozen=True, slots=True)
class E4MigrationGuard:
    database_url: str
    target: E4Target
    preflight: Mapping[str, Any]
    allowlist: tuple[E4Target, ...]


AllowlistSource: TypeAlias = Mapping[str, Any] | Sequence[Mapping[str, Any] | E4Target] | str | Path


def database_url_fingerprint(database_url: str) -> str:
    """Return a non-reversible fingerprint for the runtime DSN.

    The DSN may contain a password in memory, but the value returned here and
    written to a preflight record is only its SHA-256 digest.
    """

    if not isinstance(database_url, str) or not database_url:
        raise E4GuardError("E4 database URL is required")
    return hashlib.sha256(database_url.encode("utf-8")).hexdigest()


def approval_token_fingerprint(token: str) -> str:
    if not isinstance(token, str) or not token:
        raise E4GuardError("E4 approval token is required")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise E4GuardError("E4 allowlist contains non-JSON values") from exc


def _reject_secret_fields(value: object, *, path: str = "document") -> None:
    """Reject config/records that attempt to carry a secret inline."""

    if isinstance(value, Mapping):
        for key, child in value.items():
            if isinstance(key, str) and key.casefold() in _SECRET_FIELD_NAMES:
                raise E4GuardError(f"E4 {path} must use credential_ref, not inline secret material")
            _reject_secret_fields(child, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_secret_fields(child, path=f"{path}[{index}]")


def _json_document(source: AllowlistSource | Mapping[str, Any]) -> object:
    if isinstance(source, Mapping):
        return source
    if isinstance(source, (list, tuple)):
        return source
    if isinstance(source, Path):
        path = source
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise E4GuardError("E4 allowlist/preflight JSON document is invalid") from exc
    if isinstance(source, str):
        candidate = source.strip()
        if candidate.startswith("{") or candidate.startswith("["):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError as exc:
                raise E4GuardError("E4 allowlist/preflight JSON document is invalid") from exc
        path = Path(source)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise E4GuardError("E4 allowlist/preflight JSON document is invalid") from exc
    raise E4GuardError("E4 allowlist must be a mapping, JSON document, or path")


def _non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise E4GuardError(f"E4 allowlist {field_name} must be a non-empty string")
    return value


def _target_record_from_mapping(item: Mapping[str, Any], index: int) -> E4Target:
    if not isinstance(item, Mapping):
        raise E4GuardError(f"E4 allowlist target {index} must be a JSON object")
    _reject_secret_fields(item, path=f"allowlist.targets[{index}]")

    target_id = item.get("id", item.get("target_id", item.get("name")))
    target_id = _non_empty_string(target_id, f"target {index} id")
    role = item.get("role")
    if not isinstance(role, str) or role.casefold() not in E4_ROLES:
        raise E4GuardError(f"E4 allowlist target {target_id!r} has an unsupported role")
    normalized_role = role.casefold()
    host = _non_empty_string(item.get("host"), f"target {target_id!r} host")
    port = item.get("port")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise E4GuardError(f"E4 allowlist target {target_id!r} port is invalid")
    database = _non_empty_string(item.get("database"), f"target {target_id!r} database")
    server_uuid = _non_empty_string(item.get("server_uuid"), f"target {target_id!r} server_uuid")
    credential_ref = _non_empty_string(item.get("credential_ref"), f"target {target_id!r} credential_ref")

    read_only = item.get("read_only")
    if normalized_role == "source":
        if read_only is not True:
            raise E4GuardError(f"E4 source target {target_id!r} must be explicitly read_only")
    elif read_only is None:
        read_only = False
    elif not isinstance(read_only, bool):
        raise E4GuardError(f"E4 allowlist target {target_id!r} read_only is invalid")
    elif read_only is True:
        raise E4GuardError(f"E4 {normalized_role} target {target_id!r} must not be read_only")

    return E4Target(
        target_id=target_id,
        role=normalized_role,
        host=host,
        port=port,
        database=database,
        server_uuid=server_uuid,
        credential_ref=credential_ref,
        read_only=read_only,
    )


def _target_record_from_object(item: E4Target, index: int) -> E4Target:
    """Re-validate dataclass inputs instead of trusting caller construction."""

    return _target_record_from_mapping(
        {
            "id": item.target_id,
            "role": item.role,
            "host": item.host,
            "port": item.port,
            "database": item.database,
            "server_uuid": item.server_uuid,
            "credential_ref": item.credential_ref,
            "read_only": item.read_only,
        },
        index,
    )


def e4_target_record(target: E4Target) -> dict[str, object]:
    return {
        "id": target.target_id,
        "role": target.role,
        "host": target.host,
        "port": target.port,
        "database": target.database,
        "server_uuid": target.server_uuid,
        "credential_ref": target.credential_ref,
        "read_only": target.read_only,
    }


def _allowlist_record(targets: Iterable[E4Target]) -> dict[str, object]:
    records = [e4_target_record(target) for target in targets]
    records.sort(key=lambda item: str(item["id"]))
    return {"schema_version": 1, "targets": records}


def allowlist_fingerprint(allowlist: AllowlistSource) -> str:
    """Fingerprint the normalized allowlist without reading environment state."""

    targets = parse_e4_allowlist(allowlist)
    return hashlib.sha256(_canonical_json(_allowlist_record(targets)).encode("utf-8")).hexdigest()


def parse_e4_allowlist(allowlist: AllowlistSource) -> tuple[E4Target, ...]:
    """Parse and validate an explicit source/target/restore allowlist.

    The accepted JSON shape is ``{"schema_version": 1, "targets": [...]}``
    (``resources`` is accepted as a descriptive alias), or a bare JSON list.
    At least one read-only source and exactly one final target and restore target
    are required.  Port 3306 is intentionally treated like every other port;
    identity is established by the full allowlist tuple and server UUID.
    """

    # Internal callers may pass an already parsed tuple to avoid reparsing and
    # to ensure the fingerprint is calculated from exactly the same identities.
    if isinstance(allowlist, (list, tuple)) and allowlist and all(isinstance(item, E4Target) for item in allowlist):
        targets = tuple(
            _target_record_from_object(item, index)
            for index, item in enumerate(allowlist)
        )
    else:
        document = _json_document(allowlist)
        _reject_secret_fields(document, path="allowlist")
        if isinstance(document, Mapping):
            schema_version = document.get("schema_version", 1)
            if schema_version != 1:
                raise E4GuardError("unsupported E4 allowlist schema version")
            raw_targets = document.get("targets", document.get("resources"))
            # A role-keyed object is convenient for hand-authored config while
            # retaining the same normalized target records in the preflight.
            if raw_targets is None and any(key in document for key in E4_ROLES):
                role_targets: list[Mapping[str, Any]] = []
                for role in ("source", "target", "restore"):
                    value = document.get(role)
                    if value is None:
                        continue
                    values = value if isinstance(value, (list, tuple)) else [value]
                    for item in values:
                        if not isinstance(item, Mapping):
                            raise E4GuardError(f"E4 allowlist {role} entry must be a JSON object")
                        role_targets.append({**item, "role": role})
                raw_targets = role_targets
        else:
            raw_targets = document
        if not isinstance(raw_targets, (list, tuple)) or not raw_targets:
            raise E4GuardError("E4 allowlist targets must be a non-empty list")
        targets = tuple(
            _target_record_from_object(item, index)
            if isinstance(item, E4Target)
            else _target_record_from_mapping(item, index)
            for index, item in enumerate(raw_targets)
        )
    ids: set[str] = set()
    endpoints: set[tuple[str, int, str]] = set()
    for target in targets:
        if target.target_id in ids:
            raise E4GuardError(f"E4 allowlist target id {target.target_id!r} is duplicated")
        ids.add(target.target_id)
        # DNS host names are case-insensitive; keep the original spelling in
        # the record, but use a canonical comparison for duplicate endpoints.
        endpoint = (target.host.casefold(), target.port, target.database)
        if endpoint in endpoints:
            raise E4GuardError(f"E4 allowlist endpoint {endpoint!r} is duplicated")
        endpoints.add(endpoint)

    sources = [target for target in targets if target.role == "source"]
    finals = [target for target in targets if target.role == "target"]
    restores = [target for target in targets if target.role == "restore"]
    if not sources:
        raise E4GuardError("E4 allowlist requires at least one read-only source")
    if len(finals) != 1:
        raise E4GuardError("E4 allowlist requires exactly one final target")
    if len(restores) != 1:
        raise E4GuardError("E4 allowlist requires exactly one independent restore target")
    if (finals[0].host, finals[0].port, finals[0].database) == (
        restores[0].host,
        restores[0].port,
        restores[0].database,
    ):
        raise E4GuardError("E4 restore target must be independent from the final target")
    if finals[0].server_uuid == restores[0].server_uuid:
        raise E4GuardError("E4 restore target must use an independent MySQL server UUID")
    return targets


def approved_e4_target(allowlist: AllowlistSource, target_id: str) -> E4Target:
    targets = parse_e4_allowlist(allowlist)
    for target in targets:
        if target.target_id == target_id:
            return target
    raise E4GuardError(f"E4 target {target_id!r} is outside the explicit allowlist")


def parse_e4_target(
    database_url: str,
    allowlist: AllowlistSource,
    *,
    target_id: str | None = None,
    credential_ref: str | None = None,
) -> E4Target:
    """Bind a runtime DSN to one exact allowlisted identity."""

    if not isinstance(database_url, str) or not database_url:
        raise E4GuardError("E4 database URL is invalid")
    try:
        url = make_url(database_url)
    except Exception as exc:
        raise E4GuardError("E4 database URL is invalid") from exc
    if url.drivername != "mysql+aiomysql":
        raise E4GuardError("E4 database URL must use mysql+aiomysql")
    if not url.username or not url.password:
        raise E4GuardError("E4 database URL must include a runtime credential")
    try:
        url_port = url.port
    except ValueError as exc:
        raise E4GuardError("E4 database URL port is invalid") from exc
    if not url.host or url_port is None or not url.database:
        raise E4GuardError("E4 database URL must include exact host, port and database")

    targets = parse_e4_allowlist(allowlist)
    candidates = [
        target
        for target in targets
        if target.host.casefold() == url.host.casefold() and target.port == url_port and target.database == url.database
    ]
    if target_id is not None:
        candidates = [target for target in candidates if target.target_id == target_id]
    if credential_ref is not None:
        if not isinstance(credential_ref, str) or not credential_ref.strip():
            raise E4GuardError("E4 credential_ref is required")
        candidates = [target for target in candidates if target.credential_ref == credential_ref]
    if not candidates:
        raise E4GuardError("E4 database URL target is outside the explicit allowlist")
    if len(candidates) != 1:
        raise E4GuardError("E4 database URL matches multiple allowlisted targets; target_id is required")
    return candidates[0]


def _validated_purposes(*, purpose: str | None, purposes: Sequence[str] | None) -> tuple[str, ...]:
    if purposes is None:
        if purpose is None:
            raise E4GuardError("E4 preflight purpose is required")
        values: list[object] = [purpose]
    else:
        if isinstance(purposes, (str, bytes)):
            raise E4GuardError("E4 preflight purposes must be a list of strings")
        values = list(purposes)
        if purpose is not None and purpose not in values:
            raise E4GuardError("E4 purpose is not included in purposes")
    if not values or not all(isinstance(item, str) for item in values):
        raise E4GuardError("E4 preflight purposes must be a non-empty list of strings")
    if len(set(values)) != len(values):
        raise E4GuardError("E4 preflight purposes must not contain duplicates")
    if any(item not in E4_PREFLIGHT_PURPOSES for item in values):
        raise E4GuardError("E4 preflight contains an unsupported purpose")
    return tuple(values)  # type: ignore[return-value]


def _parse_timestamp(value: object, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise E4GuardError(f"E4 preflight {field_name} is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise E4GuardError(f"E4 preflight {field_name} is invalid") from exc
    if parsed.tzinfo is None:
        raise E4GuardError(f"E4 preflight {field_name} must include a timezone")
    return parsed.astimezone(UTC)


def _validated_database_facts(database_facts: Mapping[str, Any], target: E4Target) -> dict[str, str]:
    if not isinstance(database_facts, Mapping):
        raise E4GuardError("E4 preflight database facts are missing")
    database = database_facts.get("database", target.database)
    server_uuid = database_facts.get("server_uuid")
    if database != target.database:
        raise E4GuardError("E4 database name does not match the allowlist")
    if not isinstance(server_uuid, str) or not server_uuid.strip():
        raise E4GuardError("E4 preflight database server_uuid must be a non-empty string")
    if server_uuid != target.server_uuid:
        raise E4GuardError("E4 MySQL server UUID does not match the allowlist")
    return {"database": target.database, "server_uuid": server_uuid}


def inspect_database_identity(connection: Connection, target: E4Target) -> dict[str, str]:
    """Read only generic database identity facts from an already-open connection."""

    try:
        row = connection.execute(text("SELECT DATABASE(), @@server_uuid")).one()
    except Exception as exc:
        raise E4GuardError("unable to inspect E4 database identity") from exc
    database, server_uuid = row
    if database != target.database:
        raise E4GuardError("connected database does not match the E4 allowlist")
    if not isinstance(server_uuid, str) or not server_uuid.strip():
        raise E4GuardError("E4 MySQL server UUID is invalid")
    if server_uuid != target.server_uuid:
        raise E4GuardError("E4 MySQL server UUID does not match the allowlist")
    return {"database": database, "server_uuid": server_uuid}


def build_e4_preflight_record(
    *,
    database_url: str,
    allowlist: AllowlistSource,
    credential_ref: str,
    database_facts: Mapping[str, Any],
    issued_at: datetime,
    purpose: str | None = None,
    purposes: Sequence[str] | None = None,
    target_id: str | None = None,
    approval_token: str | None = None,
    lifetime_seconds: int = E4_PREFLIGHT_MAX_LIFETIME_SECONDS,
) -> dict[str, Any]:
    targets = parse_e4_allowlist(allowlist)
    target = parse_e4_target(database_url, targets, target_id=target_id, credential_ref=credential_ref)
    normalized_purposes = _validated_purposes(purpose=purpose, purposes=purposes)
    if not isinstance(issued_at, datetime) or issued_at.tzinfo is None:
        raise E4GuardError("E4 preflight issued_at must include a timezone")
    if not isinstance(lifetime_seconds, int) or isinstance(lifetime_seconds, bool) or not 0 < lifetime_seconds <= E4_PREFLIGHT_MAX_LIFETIME_SECONDS:
        raise E4GuardError("E4 preflight lifetime must be between 1 and 900 seconds")
    if not isinstance(credential_ref, str) or not credential_ref.strip():
        raise E4GuardError("E4 credential_ref is required")
    database = _validated_database_facts(database_facts, target)
    issued = issued_at.astimezone(UTC)
    record: dict[str, Any] = {
        "schema_version": 1,
        "issued_at": issued.isoformat(),
        "expires_at": (issued + timedelta(seconds=lifetime_seconds)).isoformat(),
        "purpose": normalized_purposes[0],
        "purposes": list(normalized_purposes),
        "dsn_sha256": database_url_fingerprint(database_url),
        "allowlist_sha256": allowlist_fingerprint(targets),
        "target": e4_target_record(target),
        "database": database,
    }
    if approval_token is not None:
        record["approval_token_sha256"] = approval_token_fingerprint(approval_token)
    validate_preflight_record(
        record,
        database_url=database_url,
        allowlist=targets,
        credential_ref=credential_ref,
        purpose=normalized_purposes[0],
        approval_token=approval_token,
        now=issued,
        target_id=target.target_id,
    )
    return record


DatabaseInspector: TypeAlias = Callable[[E4Target], Mapping[str, Any] | Awaitable[Mapping[str, Any]]]


async def issue_e4_preflight_record(
    *,
    database_url: str,
    allowlist: AllowlistSource,
    credential_ref: str,
    issuance_switch: str,
    database_inspector: DatabaseInspector | None = None,
    inspector: DatabaseInspector | None = None,
    purpose: str | None = None,
    purposes: Sequence[str] | None = None,
    target_id: str | None = None,
    approval_token: str | None = None,
    lifetime_seconds: int = E4_PREFLIGHT_MAX_LIFETIME_SECONDS,
) -> dict[str, Any]:
    """Issue a record after an explicitly injected, read-only identity check.

    No default engine, dotenv lookup, container inspection, or network fallback
    exists here.  Production callers must inject the already-approved resource
    inspector, which keeps accidental live-resource discovery impossible.
    """

    if issuance_switch != E4_PREFLIGHT_ISSUANCE_SWITCH:
        raise E4GuardError("E4 preflight issuance switch is not enabled")
    normalized_purposes = _validated_purposes(purpose=purpose, purposes=purposes)
    targets = parse_e4_allowlist(allowlist)
    target = parse_e4_target(database_url, targets, target_id=target_id, credential_ref=credential_ref)
    inspect_target = database_inspector or inspector
    if inspect_target is None:
        raise E4GuardError("E4 preflight requires an explicit database inspector")
    facts = inspect_target(target)
    if inspect.isawaitable(facts):
        facts = await facts
    return build_e4_preflight_record(
        database_url=database_url,
        allowlist=targets,
        credential_ref=credential_ref,
        database_facts=facts,
        issued_at=datetime.now(UTC),
        purpose=normalized_purposes[0],
        purposes=normalized_purposes,
        target_id=target.target_id,
        approval_token=approval_token,
        lifetime_seconds=lifetime_seconds,
    )


def validate_preflight_record(
    record: Mapping[str, Any],
    *,
    database_url: str,
    allowlist: AllowlistSource,
    credential_ref: str,
    purpose: str,
    target_id: str | None = None,
    approval_token: str | None = None,
    now: datetime | None = None,
) -> E4Target:
    """Validate that a preflight still authorizes one exact resource and purpose."""

    if not isinstance(record, Mapping):
        raise E4GuardError("E4 preflight record must be a JSON object")
    _reject_secret_fields(record, path="preflight")
    targets = parse_e4_allowlist(allowlist)
    target = parse_e4_target(database_url, targets, target_id=target_id, credential_ref=credential_ref)
    if record.get("schema_version") != 1:
        raise E4GuardError("unsupported E4 preflight schema version")
    record_purposes = record.get("purposes")
    normalized_purposes = _validated_purposes(purpose=None, purposes=record_purposes if isinstance(record_purposes, Sequence) else None)
    if record.get("purpose") != normalized_purposes[0]:
        raise E4GuardError("E4 preflight purpose field is inconsistent")
    if not isinstance(purpose, str) or purpose not in E4_PREFLIGHT_PURPOSES:
        raise E4GuardError("E4 preflight purpose is unsupported")
    if purpose not in normalized_purposes:
        raise E4GuardError(f"E4 preflight does not authorize {purpose!r}")

    issued_at = _parse_timestamp(record.get("issued_at"), "issued_at")
    expires_at = _parse_timestamp(record.get("expires_at"), "expires_at")
    checked_at = (now or datetime.now(UTC)).astimezone(UTC)
    lifetime = (expires_at - issued_at).total_seconds()
    if not issued_at <= checked_at < expires_at or lifetime <= 0 or lifetime > E4_PREFLIGHT_MAX_LIFETIME_SECONDS:
        raise E4GuardError("E4 preflight is not currently valid")
    if record.get("dsn_sha256") != database_url_fingerprint(database_url):
        raise E4GuardError("E4 database URL fingerprint does not match preflight")
    if record.get("allowlist_sha256") != allowlist_fingerprint(targets):
        raise E4GuardError("E4 allowlist fingerprint does not match preflight")
    if approval_token is not None:
        if record.get("approval_token_sha256") != approval_token_fingerprint(approval_token):
            raise E4GuardError("E4 approval token does not match preflight")
    elif "approval_token_sha256" in record:
        raise E4GuardError("E4 approval token is required for this preflight")

    recorded_target = record.get("target")
    if not isinstance(recorded_target, Mapping) or dict(recorded_target) != e4_target_record(target):
        raise E4GuardError("E4 preflight target does not match the explicit allowlist")
    database = record.get("database")
    if not isinstance(database, Mapping) or dict(database) != {"database": target.database, "server_uuid": target.server_uuid}:
        raise E4GuardError("E4 preflight database identity does not match the allowlist")
    return target


def _read_preflight(preflight: Mapping[str, Any] | str | Path) -> Mapping[str, Any]:
    document = _json_document(preflight)  # type: ignore[arg-type]
    if not isinstance(document, Mapping):
        raise E4GuardError("E4 preflight record must be a JSON object")
    return document


def load_guard_from_config(
    purpose: str,
    *,
    database_url: str,
    allowlist: AllowlistSource,
    credential_ref: str,
    preflight: Mapping[str, Any] | str | Path,
    target_id: str | None = None,
    approval_token: str | None = None,
    now: datetime | None = None,
) -> E4MigrationGuard:
    """Load a guard from explicit config values; never consults process env."""

    targets = parse_e4_allowlist(allowlist)
    record = _read_preflight(preflight)
    target = validate_preflight_record(
        record,
        database_url=database_url,
        allowlist=targets,
        credential_ref=credential_ref,
        purpose=purpose,
        target_id=target_id,
        approval_token=approval_token,
        now=now,
    )
    return E4MigrationGuard(database_url=database_url, target=target, preflight=record, allowlist=targets)


def verify_database_identity(connection: Connection, guard: E4MigrationGuard) -> None:
    expected = guard.preflight.get("database")
    if not isinstance(expected, Mapping):
        raise E4GuardError("E4 preflight database identity is missing")
    actual = inspect_database_identity(connection, guard.target)
    if dict(actual) != dict(expected):
        raise E4GuardError("E4 MySQL database identity drifted after preflight")


def verify_database_fingerprint(connection: Connection, guard: E4MigrationGuard) -> None:
    """E2/E3-compatible alias for the generic E4 identity verification."""

    verify_database_identity(connection, guard)
