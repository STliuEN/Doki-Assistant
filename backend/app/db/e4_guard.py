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
import os
import subprocess
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
E4_MIGRATION_PURPOSES = frozenset({"backup", "migrate", "restore", "restore-forward", "switch", "runtime"})
E4_ROLES = frozenset({"source", "target", "restore"})
_E4_PURPOSES_BY_ROLE = {
    "source": frozenset({"inventory", "snapshot", "backup", "dry-run", "validate"}),
    "target": frozenset({"inventory", "snapshot", "backup", "dry-run", "migrate", "switch", "runtime", "validate"}),
    "restore": frozenset({"inventory", "restore", "restore-forward", "validate"}),
}
_E4_DATABASE_QUERY = {"charset": "utf8mb4"}
_NON_DEDICATED_DATABASE_USERS = frozenset({"root", "mysql"})
_PROTECTED_TOPOLOGY_PREFIXES = ("doki-e1-", "doki-e2-", "doki-e3-")
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
E4_ENVIRONMENT_NAMES = frozenset(
    {
        "E4_MIGRATION_ENABLED",
        "E4_DATABASE_URL",
        "E4_ALLOWLIST_FILE",
        "E4_CREDENTIAL_REF",
        "E4_TARGET_ID",
        "E4_PREFLIGHT_FILE",
        "E4_APPROVAL_TOKEN",
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
    container_name: str | None = None
    container_id: str | None = None
    image_reference: str | None = None
    network: str | None = None
    image_id: str | None = None
    database_username: str | None = None

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


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _non_empty_string(value, field_name)


def _reject_protected_topology_identity(target_id: str, value: str | None, field_name: str) -> None:
    if value is not None and value.casefold().startswith(_PROTECTED_TOPOLOGY_PREFIXES):
        raise E4GuardError(f"E4 allowlist target {target_id!r} cannot reuse a protected E1/E2/E3 {field_name}")


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
    database_username = _non_empty_string(
        item.get("database_username"),
        f"target {target_id!r} database_username",
    )
    if database_username.casefold() in _NON_DEDICATED_DATABASE_USERS:
        raise E4GuardError(f"E4 allowlist target {target_id!r} must use a dedicated database_username")

    raw_container = item.get("container")
    if raw_container is not None and not isinstance(raw_container, Mapping):
        raise E4GuardError(f"E4 allowlist target {target_id!r} container must be an object")
    container = raw_container if isinstance(raw_container, Mapping) else {}
    container_name = _optional_string(
        item.get("container_name", container.get("container_name")),
        f"target {target_id!r} container_name",
    )
    container_id = _optional_string(
        item.get("container_id", container.get("container_id")),
        f"target {target_id!r} container_id",
    )
    image_reference = _optional_string(
        item.get("image_reference", container.get("image_reference")),
        f"target {target_id!r} image_reference",
    )
    network = _optional_string(
        item.get("network", container.get("network")),
        f"target {target_id!r} network",
    )
    image_id = _optional_string(
        item.get("image_id", container.get("image_id")),
        f"target {target_id!r} image_id",
    )
    topology_values = (container_name, container_id, image_reference, network, image_id)
    if any(value is not None for value in topology_values) and not all(value is not None for value in topology_values):
        raise E4GuardError(
            f"E4 allowlist target {target_id!r} topology requires container_name, container_id, image_reference, network and image_id"
        )
    _reject_protected_topology_identity(target_id, container_name, "container_name")
    _reject_protected_topology_identity(target_id, network, "network")

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
        container_name=container_name,
        container_id=container_id,
        image_reference=image_reference,
        network=network,
        image_id=image_id,
        database_username=database_username,
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
            "container_name": item.container_name,
            "container_id": item.container_id,
            "image_reference": item.image_reference,
            "network": item.network,
            "image_id": item.image_id,
            "database_username": item.database_username,
        },
        index,
    )


def e4_target_record(target: E4Target) -> dict[str, object]:
    record: dict[str, object] = {
        "id": target.target_id,
        "role": target.role,
        "host": target.host,
        "port": target.port,
        "database": target.database,
        "server_uuid": target.server_uuid,
        "credential_ref": target.credential_ref,
        "database_username": target.database_username,
        "read_only": target.read_only,
    }
    for field in ("container_name", "container_id", "image_reference", "network", "image_id"):
        value = getattr(target, field)
        if value is not None:
            record[field] = value
    return record


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
    container_ids: set[str] = set()
    container_names: set[str] = set()
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
        if target.container_id is not None:
            if target.container_id in container_ids:
                raise E4GuardError(f"E4 allowlist container_id {target.container_id!r} is duplicated")
            container_ids.add(target.container_id)
        if target.container_name is not None:
            normalized_container_name = target.container_name.casefold()
            if normalized_container_name in container_names:
                raise E4GuardError(f"E4 allowlist container_name {target.container_name!r} is duplicated")
            container_names.add(normalized_container_name)

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
    if finals[0].container_id is not None and finals[0].container_id == restores[0].container_id:
        raise E4GuardError("E4 restore target must use an independent container identity")
    if finals[0].credential_ref == restores[0].credential_ref:
        raise E4GuardError("E4 target and restore must use independent credential references")
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
    if not url.username or not url.password or url.username.casefold() in _NON_DEDICATED_DATABASE_USERS:
        raise E4GuardError("E4 database URL must use a dedicated application username")
    try:
        url_port = url.port
    except ValueError as exc:
        raise E4GuardError("E4 database URL port is invalid") from exc
    if not url.host or url_port is None or not url.database:
        raise E4GuardError("E4 database URL must include exact host, port and database")
    if dict(url.query) != _E4_DATABASE_QUERY:
        raise E4GuardError("E4 database URL query must be exactly charset=utf8mb4")

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
    candidates = [target for target in candidates if target.database_username == url.username]
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


def _requires_migration_switch(purposes: Sequence[str]) -> bool:
    return any(item in E4_MIGRATION_PURPOSES for item in purposes)


def _validate_purposes_for_target(target: E4Target, purposes: Sequence[str]) -> None:
    unsupported = sorted(set(purposes) - _E4_PURPOSES_BY_ROLE[target.role])
    if unsupported:
        joined = ", ".join(unsupported)
        raise E4GuardError(f"E4 target role {target.role!r} does not authorize purpose(s): {joined}")


def _has_container_topology(target: E4Target) -> bool:
    return any(
        value is not None
        for value in (target.container_name, target.container_id, target.image_reference, target.network, target.image_id)
    )


def _migration_switch_fingerprint() -> str:
    return hashlib.sha256(E4_MIGRATION_SWITCH.encode("utf-8")).hexdigest()


def _validated_migration_switch(
    purposes: Sequence[str],
    migration_switch: str | None,
    *,
    recorded_fingerprint: object = None,
) -> None:
    required = _requires_migration_switch(purposes)
    if required and migration_switch != E4_MIGRATION_SWITCH:
        raise E4GuardError("E4 migration switch is not enabled for this purpose")
    if migration_switch is not None and migration_switch != E4_MIGRATION_SWITCH:
        raise E4GuardError("E4 migration switch is invalid")
    expected = _migration_switch_fingerprint()
    if required and recorded_fingerprint is not None and recorded_fingerprint != expected:
        raise E4GuardError("E4 preflight migration switch is missing or invalid")
    if recorded_fingerprint is not None and recorded_fingerprint != expected:
        raise E4GuardError("E4 preflight migration switch fingerprint is invalid")


def _validate_approval_token(purposes: Sequence[str], approval_token: str | None) -> None:
    if _requires_migration_switch(purposes) and (not isinstance(approval_token, str) or not approval_token):
        raise E4GuardError("E4 migration preflight requires an approval token")
    if approval_token is not None:
        approval_token_fingerprint(approval_token)


def _validate_lifetime_seconds(lifetime_seconds: int) -> None:
    if not isinstance(lifetime_seconds, int) or isinstance(lifetime_seconds, bool) or not 0 < lifetime_seconds <= E4_PREFLIGHT_MAX_LIFETIME_SECONDS:
        raise E4GuardError("E4 preflight lifetime must be between 1 and 900 seconds")


def _validated_topology_facts(
    target: E4Target,
    facts: Mapping[str, Any] | None,
    *,
    required: bool,
) -> dict[str, Any] | None:
    """Validate the container/network/image facts bound to a live target."""

    target_fields = (target.container_name, target.container_id, target.image_reference, target.network, target.image_id)
    if not required and facts is None and not any(value is not None for value in target_fields):
        return None
    if any(value is None for value in target_fields):
        raise E4GuardError("E4 allowlist target topology facts are incomplete")
    if not isinstance(facts, Mapping):
        raise E4GuardError("E4 preflight container topology facts are missing")
    if facts.get("container_name") != target.container_name:
        raise E4GuardError("E4 container name does not match the allowlist")
    if facts.get("container_id") != target.container_id:
        raise E4GuardError("E4 container identity does not match the allowlist")
    if facts.get("image_reference") != target.image_reference:
        raise E4GuardError("E4 container image does not match the allowlist")
    if facts.get("image_id") != target.image_id:
        raise E4GuardError("E4 container image identity does not match the allowlist")
    networks = facts.get("networks")
    if networks != [target.network]:
        raise E4GuardError("E4 container network does not match the allowlist")
    host_ports = facts.get("host_ports")
    if host_ports != [target.port]:
        raise E4GuardError("E4 container host port does not match the allowlist")
    if facts.get("running") is not True or facts.get("healthy") is not True:
        raise E4GuardError("E4 container must be running and healthy")
    normalized: dict[str, Any] = {
        "container_name": target.container_name,
        "container_id": target.container_id,
        "image_reference": target.image_reference,
        "image_id": target.image_id,
        "networks": [target.network],
        "host_ports": [target.port],
        "running": True,
        "healthy": True,
    }
    return normalized


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
    if "database" not in database_facts:
        raise E4GuardError("E4 preflight database name is missing")
    database = database_facts.get("database")
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
    migration_switch: str | None = None,
    container_facts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    targets = parse_e4_allowlist(allowlist)
    target = parse_e4_target(database_url, targets, target_id=target_id, credential_ref=credential_ref)
    normalized_purposes = _validated_purposes(purpose=purpose, purposes=purposes)
    _validate_purposes_for_target(target, normalized_purposes)
    _validated_migration_switch(normalized_purposes, migration_switch)
    _validate_approval_token(normalized_purposes, approval_token)
    if not isinstance(issued_at, datetime) or issued_at.tzinfo is None:
        raise E4GuardError("E4 preflight issued_at must include a timezone")
    _validate_lifetime_seconds(lifetime_seconds)
    if not isinstance(credential_ref, str) or not credential_ref.strip():
        raise E4GuardError("E4 credential_ref is required")
    database = _validated_database_facts(database_facts, target)
    topology = _validated_topology_facts(
        target,
        container_facts,
        required=_has_container_topology(target),
    )
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
    if _requires_migration_switch(normalized_purposes):
        record["migration_switch_sha256"] = _migration_switch_fingerprint()
    if topology is not None:
        record["container"] = topology
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
        migration_switch=migration_switch,
        container_facts=container_facts,
    )
    return record


DatabaseInspector: TypeAlias = Callable[[E4Target], Mapping[str, Any] | Awaitable[Mapping[str, Any]]]
ContainerInspector: TypeAlias = Callable[[E4Target], Mapping[str, Any] | Awaitable[Mapping[str, Any]]]
SyncContainerInspector: TypeAlias = Callable[[E4Target], Mapping[str, Any]]


async def issue_e4_preflight_record(
    *,
    database_url: str,
    allowlist: AllowlistSource,
    credential_ref: str,
    issuance_switch: str,
    database_inspector: DatabaseInspector | None = None,
    inspector: DatabaseInspector | None = None,
    container_inspector: ContainerInspector | None = None,
    purpose: str | None = None,
    purposes: Sequence[str] | None = None,
    target_id: str | None = None,
    approval_token: str | None = None,
    lifetime_seconds: int = E4_PREFLIGHT_MAX_LIFETIME_SECONDS,
    migration_switch: str | None = None,
) -> dict[str, Any]:
    """Issue a record after an explicitly injected, read-only identity check.

    No default engine, dotenv lookup, container inspection, or network fallback
    exists here.  Production callers must inject the already-approved resource
    inspector, which keeps accidental live-resource discovery impossible.
    """

    if issuance_switch != E4_PREFLIGHT_ISSUANCE_SWITCH:
        raise E4GuardError("E4 preflight issuance switch is not enabled")
    normalized_purposes = _validated_purposes(purpose=purpose, purposes=purposes)
    _validated_migration_switch(normalized_purposes, migration_switch)
    targets = parse_e4_allowlist(allowlist)
    target = parse_e4_target(database_url, targets, target_id=target_id, credential_ref=credential_ref)
    _validate_purposes_for_target(target, normalized_purposes)
    _validate_approval_token(normalized_purposes, approval_token)
    _validate_lifetime_seconds(lifetime_seconds)
    inspect_target = database_inspector or inspector
    if inspect_target is None:
        raise E4GuardError("E4 preflight requires an explicit database inspector")
    container_facts = None
    if _has_container_topology(target):
        if container_inspector is None:
            raise E4GuardError("E4 container-backed preflight requires an explicit container inspector")
        inspected_container = container_inspector(target)
        if inspect.isawaitable(inspected_container):
            inspected_container = await inspected_container
        container_facts = _validated_topology_facts(target, inspected_container, required=True)
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
        migration_switch=migration_switch,
        container_facts=container_facts,
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
    migration_switch: str | None = None,
    container_facts: Mapping[str, Any] | None = None,
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
    _validate_purposes_for_target(target, normalized_purposes)
    if _requires_migration_switch(normalized_purposes) and "migration_switch_sha256" not in record:
        raise E4GuardError("E4 preflight migration switch is missing or invalid")
    _validated_migration_switch(
        normalized_purposes,
        migration_switch,
        recorded_fingerprint=record.get("migration_switch_sha256"),
    )
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
    if _requires_migration_switch(normalized_purposes) and approval_token is None:
        raise E4GuardError("E4 approval token is required for migration preflight")
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
    topology = _validated_topology_facts(
        target,
        container_facts,
        required=_has_container_topology(target),
    )
    recorded_topology = record.get("container")
    if topology is not None:
        if not isinstance(recorded_topology, Mapping) or dict(recorded_topology) != topology:
            raise E4GuardError("E4 preflight container topology does not match the allowlist")
    elif recorded_topology is not None:
        raise E4GuardError("E4 preflight container topology cannot be verified")
    return target


def _read_preflight(preflight: Mapping[str, Any] | str | Path) -> Mapping[str, Any]:
    document = _json_document(preflight)  # type: ignore[arg-type]
    if not isinstance(document, Mapping):
        raise E4GuardError("E4 preflight record must be a JSON object")
    return document


def inspect_e4_container(target: E4Target) -> dict[str, Any]:
    """Read current Docker facts for an already allowlisted E4 container.

    The container name comes from the parsed allowlist; this function never
    searches by port, image, compose project, or environment variables.
    """

    if not _has_container_topology(target) or not target.container_name:
        raise E4GuardError("E4 target has no container identity to inspect")
    try:
        result = subprocess.run(
            ["docker", "inspect", target.container_name],
            capture_output=True,
            check=False,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise E4GuardError("unable to inspect the allowlisted E4 container") from exc
    if result.returncode != 0:
        raise E4GuardError(f"allowlisted E4 container {target.container_name!r} is unavailable")
    try:
        item = json.loads(result.stdout)[0]
        ports = item["NetworkSettings"]["Ports"].get("3306/tcp") or []
        host_ports = sorted(
            int(entry["HostPort"])
            for entry in ports
            if entry.get("HostIp") in {"127.0.0.1", "::1"}
        )
        networks = sorted(item["NetworkSettings"]["Networks"])
        health = (item.get("State", {}).get("Health") or {}).get("Status")
        return {
            "container_name": str(item["Name"]).lstrip("/"),
            "container_id": str(item["Id"]),
            "image_reference": str(item["Config"]["Image"]),
            "image_id": str(item["Image"]),
            "networks": networks,
            "host_ports": host_ports,
            "running": bool(item["State"]["Running"]),
            "healthy": health == "healthy",
        }
    except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise E4GuardError("docker inspect returned invalid E4 container facts") from exc


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
    migration_switch: str | None = None,
    container_inspector: SyncContainerInspector | None = None,
) -> E4MigrationGuard:
    """Load a guard from explicit config and freshly inspect container targets."""

    targets = parse_e4_allowlist(allowlist)
    record = _read_preflight(preflight)
    target = parse_e4_target(database_url, targets, target_id=target_id, credential_ref=credential_ref)
    if _has_container_topology(target):
        recorded_container = record.get("container")
        validate_preflight_record(
            record,
            database_url=database_url,
            allowlist=targets,
            credential_ref=credential_ref,
            purpose=purpose,
            target_id=target_id,
            approval_token=approval_token,
            now=now,
            migration_switch=migration_switch,
            container_facts=recorded_container if isinstance(recorded_container, Mapping) else None,
        )
        if container_inspector is None:
            raise E4GuardError("E4 container-backed guard requires an explicit container inspector")
        inspected_container = container_inspector(target)
    else:
        inspected_container = None
    target = validate_preflight_record(
        record,
        database_url=database_url,
        allowlist=targets,
        credential_ref=credential_ref,
        purpose=purpose,
        target_id=target_id,
        approval_token=approval_token,
        now=now,
        migration_switch=migration_switch,
        container_facts=inspected_container,
    )
    return E4MigrationGuard(database_url=database_url, target=target, preflight=record, allowlist=targets)


def load_guard_from_environment(
    purpose: str,
    *,
    environ: Mapping[str, str] | None = None,
    container_inspector: SyncContainerInspector | None = None,
) -> E4MigrationGuard:
    """Load an E4 guard only from explicit process-bound configuration.

    Unlike the application's normal settings loader this function does not
    read dotenv files or infer a target.  The allowlist and preflight must be
    separate files, and the credential is represented only by its external
    reference.  A migration-purpose guard is therefore impossible to create
    from the repository's default development DSN.
    """

    values = environ if environ is not None else os.environ
    if values.get("E4_MIGRATION_ENABLED") != E4_MIGRATION_SWITCH:
        raise E4GuardError("E4 migration switch is not enabled")
    database_url = values.get("E4_DATABASE_URL", "")
    allowlist_name = values.get("E4_ALLOWLIST_FILE", "")
    credential_ref = values.get("E4_CREDENTIAL_REF", "")
    preflight_name = values.get("E4_PREFLIGHT_FILE", "")
    target_id = values.get("E4_TARGET_ID") or None
    approval_token = values.get("E4_APPROVAL_TOKEN") or None
    if not database_url or not allowlist_name or not credential_ref or not preflight_name:
        raise E4GuardError(
            "E4_DATABASE_URL, E4_ALLOWLIST_FILE, E4_CREDENTIAL_REF and E4_PREFLIGHT_FILE are required"
        )
    allowlist_path = Path(allowlist_name).resolve()
    preflight_path = Path(preflight_name).resolve()
    if not allowlist_path.is_file() or not preflight_path.is_file():
        raise E4GuardError("E4 allowlist and preflight files must exist")
    try:
        allowlist = json.loads(allowlist_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise E4GuardError("E4 allowlist file is invalid") from exc
    return load_guard_from_config(
        purpose,
        database_url=database_url,
        allowlist=allowlist,
        credential_ref=credential_ref,
        preflight=preflight_path,
        target_id=target_id,
        approval_token=approval_token,
        migration_switch=E4_MIGRATION_SWITCH,
        container_inspector=container_inspector,
    )


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
