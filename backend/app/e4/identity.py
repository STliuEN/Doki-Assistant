"""Deterministic, read-only E4 identity mapping dry-run.

This module is deliberately independent of SQLAlchemy, application settings,
network clients, and filesystem stores.  Callers provide a complete JSON
snapshot containing source entities and optional read-only target facts.  The
result is a redacted report: source identifiers are represented by SHA-256
tokens, while canonical UUIDs and digest values remain available for review.

The report is a planning artifact only.  ``validated`` and ``mapped`` records
do not write ``migration_maps`` or any target table.  A later importer must
re-validate the same snapshot digest and use an explicit transaction/guard.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

E4_IDENTITY_TOOL_VERSION = "1.0"
IDENTITY_SCHEMA_VERSION = 1
_BATCH_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_ASCII_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SCOPES = frozenset({"user", "global"})
_KNOWN_SOURCE_SYSTEMS = frozenset({"django", "fastapi_legacy", "filesystem", "chroma", "skill_storage", "skill_legacy"})
_SECRET_FIELDS = frozenset(
    {
        "api_key",
        "api_key_encrypted",
        "content_blob",
        "database_url",
        "password",
        "passwd",
        "raw_blob",
        "refresh_token",
        "secret",
        "token",
    }
)
_MAX_UNIQUE_KEY_LENGTH = 512


class IdentityDryRunError(ValueError):
    """Raised when the explicit dry-run document cannot be parsed safely."""


@dataclass(frozen=True, slots=True, order=True)
class SourceKey:
    """Normalized source identity; source IDs remain case-sensitive."""

    source_system: str
    entity_type: str
    source_id: str

    @property
    def token(self) -> str:
        return _sha256_text(_source_key_text(self))


@dataclass(frozen=True, slots=True)
class _ForeignKey:
    key: SourceKey
    required: bool


@dataclass(frozen=True, slots=True)
class _Candidate:
    key: SourceKey
    entity_digest: str
    scope: str
    owner: SourceKey | None
    foreign_keys: tuple[_ForeignKey, ...]
    unique_key: str | None
    artifact_digest: str | None
    target_uuid: str
    explicit_target_uuid: bool


@dataclass(frozen=True, slots=True)
class _ExistingMapping:
    key: SourceKey
    target_uuid: str
    source_digest: str
    status: str


@dataclass(frozen=True, slots=True)
class _ExistingTarget:
    target_uuid: str
    source_key: SourceKey | None
    unique_key: str | None


@dataclass(frozen=True, slots=True)
class IdentityInput:
    """Validated explicit input for one deterministic dry-run batch."""

    migration_batch_id: str
    snapshot_manifest_digest: str
    schema_revision: str
    correlation_id: str
    entities: tuple[Mapping[str, Any], ...]
    existing_mappings: tuple[Mapping[str, Any], ...]
    existing_targets: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True, slots=True)
class IdentityDecision:
    """One internal decision; serialized reports redact the source key."""

    key: SourceKey
    target_uuid: str | None
    entity_digest: str | None
    scope: str | None
    owner: SourceKey | None
    foreign_key_count: int
    status: str
    action: str
    issue_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class IdentityDryRunReport:
    migration_batch_id: str
    snapshot_manifest_digest: str
    schema_revision: str
    correlation_id: str
    decisions: tuple[IdentityDecision, ...]
    counts: Mapping[str, int]
    blocked: bool
    report_sha256: str


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise IdentityDryRunError("E4 identity input contains non-deterministic JSON") from exc


def _source_key_text(key: SourceKey) -> str:
    return f"{key.source_system}\x1f{key.entity_type}\x1f{key.source_id}"


def _reject_secret_fields(value: object, *, path: str = "document") -> None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            if isinstance(raw_key, str) and raw_key.casefold() in _SECRET_FIELDS:
                raise IdentityDryRunError(f"E4 identity {path} contains inline secret material")
            _reject_secret_fields(child, path=f"{path}.{raw_key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_secret_fields(child, path=f"{path}[{index}]")


def _json_document(source: Mapping[str, Any] | str | Path) -> Mapping[str, Any]:
    if isinstance(source, Mapping):
        document = source
    else:
        path_or_json = str(source).strip() if isinstance(source, str) else None
        if path_or_json is not None and path_or_json.startswith(("{", "[")):
            try:
                document = json.loads(path_or_json)
            except json.JSONDecodeError as exc:
                raise IdentityDryRunError("E4 identity JSON document is invalid") from exc
        else:
            path = Path(source)
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise IdentityDryRunError("E4 identity input document is invalid") from exc
    if not isinstance(document, Mapping):
        raise IdentityDryRunError("E4 identity input must be a JSON object")
    _reject_secret_fields(document)
    return document


def _required_string(value: object, field: str, *, maximum: int = 255, strip: bool = True) -> str:
    if not isinstance(value, str):
        raise IdentityDryRunError(f"E4 identity {field} must be a string")
    normalized = value.strip() if strip else value
    if not normalized or len(normalized) > maximum or normalized != value and not strip:
        raise IdentityDryRunError(f"E4 identity {field} is empty or too long")
    if any(ord(character) < 32 for character in normalized):
        raise IdentityDryRunError(f"E4 identity {field} contains a control character")
    return normalized


def _normalized_name(value: object, field: str) -> str:
    normalized = _required_string(value, field, maximum=64).casefold()
    if not _ASCII_NAME.fullmatch(normalized):
        raise IdentityDryRunError(f"E4 identity {field} has an invalid name")
    return normalized


def _normalized_source_id(value: object, *, source_system: str, entity_type: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise IdentityDryRunError("E4 identity source_id must be a string or integer")
    if isinstance(value, int):
        if value < 0:
            raise IdentityDryRunError("E4 identity source_id integer must be non-negative")
        normalized = str(value)
    else:
        normalized = _required_string(value, "source_id", maximum=255)
        # Legacy SQL integer IDs are represented canonically without leading zeros.
        if (
            source_system == "fastapi_legacy"
            and entity_type in {"session", "message", "note", "memory", "knowledge_document"}
            and normalized.isdecimal()
        ):
            normalized = str(int(normalized))
    if any(ord(character) < 32 for character in normalized):
        raise IdentityDryRunError("E4 identity source_id contains a control character")
    return normalized


def _source_key_from_mapping(value: object, field: str) -> SourceKey:
    if not isinstance(value, Mapping):
        raise IdentityDryRunError(f"E4 identity {field} must be an object")
    source_system = _normalized_name(value.get("source_system"), f"{field}.source_system")
    entity_type = _normalized_name(value.get("entity_type"), f"{field}.entity_type")
    source_id = _normalized_source_id(value.get("source_id"), source_system=source_system, entity_type=entity_type)
    if source_system not in _KNOWN_SOURCE_SYSTEMS:
        raise IdentityDryRunError(f"E4 identity {field}.source_system is unsupported")
    return SourceKey(source_system, entity_type, source_id)


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise IdentityDryRunError(f"E4 identity {field} must be a lowercase SHA-256 digest")
    return value


def _canonical_uuid(value: object, field: str) -> str:
    if not isinstance(value, str) or value != value.lower() or not _UUID.fullmatch(value):
        raise IdentityDryRunError(f"E4 identity {field} must be a lowercase UUID")
    try:
        parsed = UUID(value)
    except ValueError as exc:
        raise IdentityDryRunError(f"E4 identity {field} must be a lowercase UUID") from exc
    if str(parsed) != value:
        raise IdentityDryRunError(f"E4 identity {field} must be a lowercase UUID")
    return value


def _unique_key(value: object, field: str) -> str | None:
    if value is None:
        return None
    normalized = _required_string(value, field, maximum=_MAX_UNIQUE_KEY_LENGTH)
    if any(ord(character) < 32 for character in normalized):
        raise IdentityDryRunError(f"E4 identity {field} contains a control character")
    return normalized


def deterministic_target_uuid(key: SourceKey | Mapping[str, Any]) -> str:
    """Return the frozen E3/E4 UUIDv5 target for one source key."""

    normalized = key if isinstance(key, SourceKey) else _source_key_from_mapping(key, "source_key")
    if normalized.source_system == "django" and normalized.entity_type == "user":
        name = f"django/user/{normalized.source_id}"
    else:
        name = f"doki-e4/{normalized.source_system}/{normalized.entity_type}/{normalized.source_id}"
    return str(uuid5(NAMESPACE_URL, name)).lower()


def _foreign_keys(value: object, field: str) -> tuple[_ForeignKey, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise IdentityDryRunError(f"E4 identity {field} must be a list")
    result: list[_ForeignKey] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise IdentityDryRunError(f"E4 identity {field}[{index}] must be an object")
        key = _source_key_from_mapping(item, f"{field}[{index}]")
        required = item.get("required", True)
        if not isinstance(required, bool):
            raise IdentityDryRunError(f"E4 identity {field}[{index}].required must be boolean")
        result.append(_ForeignKey(key=key, required=required))
    unique = {(item.key, item.required) for item in result}
    if len(unique) != len(result):
        raise IdentityDryRunError(f"E4 identity {field} contains duplicate references")
    return tuple(result)


def _candidate_from_mapping(item: object, index: int) -> _Candidate:
    if not isinstance(item, Mapping):
        raise IdentityDryRunError(f"E4 identity entities[{index}] must be an object")
    key = _source_key_from_mapping(item, f"entities[{index}]")
    entity_digest = _digest(item.get("entity_content_digest"), f"entities[{index}].entity_content_digest")
    scope = _required_string(item.get("scope"), f"entities[{index}].scope", maximum=16).casefold()
    if scope not in _SCOPES:
        raise IdentityDryRunError(f"E4 identity entities[{index}].scope is unsupported")
    owner_value = item.get("owner")
    owner = None if owner_value is None else _source_key_from_mapping(owner_value, f"entities[{index}].owner")
    if scope == "user" and owner is None:
        raise IdentityDryRunError(f"E4 identity entities[{index}] user scope requires owner")
    if scope == "global" and owner is not None:
        raise IdentityDryRunError(f"E4 identity entities[{index}] global scope cannot have owner")
    raw_target = item.get("target_uuid")
    explicit_target_uuid = raw_target is not None
    target_uuid = deterministic_target_uuid(key) if raw_target is None else _canonical_uuid(raw_target, f"entities[{index}].target_uuid")
    if key.source_system == "django" and key.entity_type == "user" and target_uuid != deterministic_target_uuid(key):
        raise IdentityDryRunError("E4 identity django user target_uuid violates the E3 UUIDv5 rule")
    return _Candidate(
        key=key,
        entity_digest=entity_digest,
        scope=scope,
        owner=owner,
        foreign_keys=_foreign_keys(item.get("foreign_keys"), f"entities[{index}].foreign_keys"),
        unique_key=_unique_key(item.get("unique_key"), f"entities[{index}].unique_key"),
        artifact_digest=None if item.get("artifact_digest") is None else _digest(item.get("artifact_digest"), f"entities[{index}].artifact_digest"),
        target_uuid=target_uuid,
        explicit_target_uuid=explicit_target_uuid,
    )


def _existing_mapping_from_mapping(item: object, index: int) -> _ExistingMapping:
    if not isinstance(item, Mapping):
        raise IdentityDryRunError(f"E4 identity existing_mappings[{index}] must be an object")
    return _ExistingMapping(
        key=_source_key_from_mapping(item, f"existing_mappings[{index}]"),
        target_uuid=_canonical_uuid(item.get("target_uuid"), f"existing_mappings[{index}].target_uuid"),
        source_digest=_digest(item.get("source_digest"), f"existing_mappings[{index}].source_digest"),
        status=_required_string(item.get("status"), f"existing_mappings[{index}].status", maximum=16).casefold(),
    )


def _existing_target_from_mapping(item: object, index: int) -> _ExistingTarget:
    if isinstance(item, str):
        return _ExistingTarget(target_uuid=_canonical_uuid(item, f"existing_targets[{index}]"), source_key=None, unique_key=None)
    if not isinstance(item, Mapping):
        raise IdentityDryRunError(f"E4 identity existing_targets[{index}] must be a UUID or object")
    source_key = None if item.get("source_key") is None else _source_key_from_mapping(item.get("source_key"), f"existing_targets[{index}].source_key")
    return _ExistingTarget(
        target_uuid=_canonical_uuid(item.get("target_uuid"), f"existing_targets[{index}].target_uuid"),
        source_key=source_key,
        unique_key=_unique_key(item.get("unique_key"), f"existing_targets[{index}].unique_key"),
    )


def load_identity_input(source: Mapping[str, Any] | str | Path | IdentityInput) -> IdentityInput:
    """Parse one explicit JSON snapshot without consulting process state."""

    if isinstance(source, IdentityInput):
        return source
    document = _json_document(source)
    schema_version = document.get("schema_version", IDENTITY_SCHEMA_VERSION)
    if schema_version != IDENTITY_SCHEMA_VERSION:
        raise IdentityDryRunError("unsupported E4 identity schema version")
    batch_id = _required_string(document.get("migration_batch_id"), "migration_batch_id", maximum=64)
    if not _BATCH_ID.fullmatch(batch_id):
        raise IdentityDryRunError("E4 identity migration_batch_id is invalid")
    snapshot_digest = _digest(document.get("snapshot_manifest_digest"), "snapshot_manifest_digest")
    schema_revision = _required_string(document.get("schema_revision"), "schema_revision", maximum=128)
    correlation_id = _canonical_uuid(document.get("correlation_id"), "correlation_id")
    entities = document.get("entities")
    if not isinstance(entities, Sequence) or isinstance(entities, (str, bytes)) or not entities:
        raise IdentityDryRunError("E4 identity entities must be a non-empty list")
    existing_mappings = document.get("existing_mappings", ())
    existing_targets = document.get("existing_targets", ())
    if not isinstance(existing_mappings, Sequence) or isinstance(existing_mappings, (str, bytes)):
        raise IdentityDryRunError("E4 identity existing_mappings must be a list")
    if not isinstance(existing_targets, Sequence) or isinstance(existing_targets, (str, bytes)):
        raise IdentityDryRunError("E4 identity existing_targets must be a list")
    # Parse once here so malformed snapshots fail before a report is emitted.
    for index, item in enumerate(entities):
        _candidate_from_mapping(item, index)
    for index, item in enumerate(existing_mappings):
        _existing_mapping_from_mapping(item, index)
    for index, item in enumerate(existing_targets):
        _existing_target_from_mapping(item, index)
    return IdentityInput(
        migration_batch_id=batch_id,
        snapshot_manifest_digest=snapshot_digest,
        schema_revision=schema_revision,
        correlation_id=correlation_id,
        entities=tuple(item for item in entities if isinstance(item, Mapping)),
        existing_mappings=tuple(item for item in existing_mappings if isinstance(item, Mapping)),
        existing_targets=tuple(item if isinstance(item, Mapping) else {"target_uuid": item} for item in existing_targets),
    )


def _issue_codes_for_references(
    candidate: _Candidate,
    *,
    available: set[SourceKey],
    existing_keys: set[SourceKey],
) -> tuple[str, ...]:
    issues: list[str] = []
    references: list[SourceKey] = []
    if candidate.owner is not None:
        references.append(candidate.owner)
    references.extend(item.key for item in candidate.foreign_keys if item.required)
    for reference in references:
        if reference not in available and reference not in existing_keys:
            issues.append("missing_reference")
    return tuple(sorted(set(issues)))


def _base_decisions(
    candidates: Sequence[_Candidate],
    mappings: Sequence[_ExistingMapping],
    targets: Sequence[_ExistingTarget],
) -> tuple[list[IdentityDecision], set[SourceKey], set[SourceKey]]:
    mapping_by_key: dict[SourceKey, _ExistingMapping] = {}
    for mapping in mappings:
        if mapping.key in mapping_by_key:
            raise IdentityDryRunError("E4 identity existing_mappings contains duplicate source keys")
        if mapping.status not in {"mapped", "conflict", "error"}:
            raise IdentityDryRunError("E4 identity existing_mappings contains an unsupported status")
        mapping_by_key[mapping.key] = mapping
    target_by_uuid: dict[str, _ExistingTarget] = {}
    for target in targets:
        if target.target_uuid in target_by_uuid:
            raise IdentityDryRunError("E4 identity existing_targets contains duplicate target UUIDs")
        target_by_uuid[target.target_uuid] = target

    target_by_source: dict[SourceKey, _ExistingTarget] = {}
    for target in targets:
        if target.source_key is None:
            continue
        if target.source_key in target_by_source:
            raise IdentityDryRunError("E4 identity existing_targets contains duplicate source keys")
        target_by_source[target.source_key] = target

    existing_unique_keys: dict[str, _ExistingTarget] = {}
    for target in targets:
        if target.unique_key is None:
            continue
        if target.unique_key in existing_unique_keys:
            raise IdentityDryRunError("E4 identity existing_targets contains duplicate unique keys")
        existing_unique_keys[target.unique_key] = target

    occurrences: Counter[SourceKey] = Counter(item.key for item in candidates)
    target_occurrences: defaultdict[str, list[SourceKey]] = defaultdict(list)
    unique_occurrences: defaultdict[str, list[SourceKey]] = defaultdict(list)
    for candidate in candidates:
        target_occurrences[candidate.target_uuid].append(candidate.key)
        if candidate.unique_key is not None:
            unique_occurrences[candidate.unique_key].append(candidate.key)

    decisions: list[IdentityDecision] = []
    duplicate_keys = {key for key, count in occurrences.items() if count > 1}
    collided_targets = {target for target, keys in target_occurrences.items() if len(set(keys)) > 1}
    collided_uniques = {unique for unique, keys in unique_occurrences.items() if len(set(keys)) > 1}
    for candidate in candidates:
        issues: set[str] = set()
        existing = mapping_by_key.get(candidate.key)
        existing_target = target_by_uuid.get(candidate.target_uuid)
        if candidate.key in duplicate_keys:
            issues.add("duplicate_source_key")
        if candidate.target_uuid in collided_targets:
            issues.add("target_uuid_collision")
        if candidate.unique_key is not None and candidate.unique_key in collided_uniques:
            issues.add("unique_key_conflict")
        existing_source_target = target_by_source.get(candidate.key)
        if existing_source_target is not None and existing_source_target.target_uuid != candidate.target_uuid:
            issues.add("target_uuid_conflict")
        if existing is not None:
            if existing.status != "mapped":
                issues.add("existing_mapping_not_mapped")
            if existing.target_uuid != candidate.target_uuid:
                issues.add("target_uuid_conflict")
            if existing.source_digest != candidate.entity_digest:
                issues.add("source_digest_conflict")
        if existing_target is not None:
            same_source = existing_target.source_key == candidate.key or (
                existing is not None and existing.status == "mapped" and existing.target_uuid == candidate.target_uuid
            )
            if existing_target.source_key is None and existing is None:
                issues.add("target_exists_without_mapping")
            elif not same_source:
                issues.add("target_exists_for_other_source")
            elif existing is None:
                issues.add("target_exists_without_mapping")
            if candidate.unique_key is not None and existing_target.unique_key not in {None, candidate.unique_key}:
                issues.add("unique_key_conflict")
        if candidate.unique_key is not None:
            existing_unique = existing_unique_keys.get(candidate.unique_key)
            if existing_unique is not None and existing_unique.source_key != candidate.key:
                issues.add("unique_key_conflict")
        status = "conflict" if issues else ("mapped" if existing is not None else "candidate")
        action = "reject" if issues else ("already_mapped" if existing is not None else "pending")
        decisions.append(IdentityDecision(
            key=candidate.key,
            target_uuid=candidate.target_uuid,
            entity_digest=candidate.entity_digest,
            scope=candidate.scope,
            owner=candidate.owner,
            foreign_key_count=len(candidate.foreign_keys),
            status=status,
            action=action,
            issue_codes=tuple(sorted(issues)),
        ))
    available = {
        candidate.key
        for candidate, decision in zip(candidates, decisions)
        if occurrences[candidate.key] == 1 and decision.status in {"candidate", "mapped"}
    }
    existing_keys = {mapping.key for mapping in mappings if mapping.status == "mapped"}
    return decisions, available, existing_keys


def _reconcile_references(
    candidates: Sequence[_Candidate],
    decisions: list[IdentityDecision],
    available: set[SourceKey],
    existing_keys: set[SourceKey],
) -> None:
    while True:
        changed = False
        for index, candidate in enumerate(candidates):
            key = candidate.key
            if key not in available:
                continue
            missing = _issue_codes_for_references(candidate, available=available, existing_keys=existing_keys)
            if not missing:
                continue
            decision = decisions[index]
            decisions[index] = IdentityDecision(
                key=decision.key,
                target_uuid=decision.target_uuid,
                entity_digest=decision.entity_digest,
                scope=decision.scope,
                owner=decision.owner,
                foreign_key_count=decision.foreign_key_count,
                status="orphan",
                action="reject",
                issue_codes=tuple(sorted(set(decision.issue_codes) | set(missing))),
            )
            available.remove(key)
            changed = True
        if not changed:
            break
    for index, candidate in enumerate(candidates):
        if candidate.key not in available:
            continue
        decision = decisions[index]
        decisions[index] = IdentityDecision(
            key=decision.key,
            target_uuid=decision.target_uuid,
            entity_digest=decision.entity_digest,
            scope=decision.scope,
            owner=decision.owner,
            foreign_key_count=decision.foreign_key_count,
            status="mapped" if decision.status == "mapped" else "validated",
            action="already_mapped" if decision.status == "mapped" else "insert",
            issue_codes=decision.issue_codes,
        )


def _counts(decisions: Sequence[IdentityDecision]) -> dict[str, int]:
    statuses = Counter(decision.status for decision in decisions)
    issues = Counter(code for decision in decisions for code in decision.issue_codes)
    return {
        "source_key_total": len(decisions),
        "normalized_count": sum(statuses.values()),
        "invalid_count": 0,
        "duplicate_count": issues["duplicate_source_key"],
        "validated_count": statuses["validated"],
        "already_mapped_count": statuses["mapped"],
        "conflict_count": statuses["conflict"],
        "orphan_count": statuses["orphan"],
        "target_uuid_collision_count": issues["target_uuid_collision"],
        "unique_conflict_count": issues["unique_key_conflict"],
        "expected_inserts": statuses["validated"],
        "expected_noops": statuses["mapped"],
    }


def _redacted_decision(decision: IdentityDecision) -> dict[str, Any]:
    return {
        "source_key_token": decision.key.token,
        "target_uuid": decision.target_uuid,
        "entity_content_digest": decision.entity_digest,
        "scope": decision.scope,
        "owner_key_token": None if decision.owner is None else decision.owner.token,
        "foreign_key_count": decision.foreign_key_count,
        "status": decision.status,
        "action": decision.action,
        "issue_codes": list(decision.issue_codes),
    }


def identity_report_to_dict(report: IdentityDryRunReport, *, include_digest: bool = True) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": IDENTITY_SCHEMA_VERSION,
        "tool": "e4_identity_dry_run",
        "tool_version": E4_IDENTITY_TOOL_VERSION,
        "migration_batch_id": report.migration_batch_id,
        "snapshot_manifest_digest": report.snapshot_manifest_digest,
        "schema_revision": report.schema_revision,
        "correlation_id": report.correlation_id,
        "blocked": report.blocked,
        "counts": dict(report.counts),
        "decisions": [_redacted_decision(decision) for decision in report.decisions],
    }
    if include_digest:
        result["report_sha256"] = report.report_sha256
    return result


def _report_digest(payload: Mapping[str, Any]) -> str:
    return _sha256_text(_canonical_json(payload))


def build_identity_dry_run(source: Mapping[str, Any] | str | Path | IdentityInput) -> IdentityDryRunReport:
    """Build a deterministic report from explicit snapshots; never writes state."""

    data = load_identity_input(source)
    candidates = tuple(_candidate_from_mapping(item, index) for index, item in enumerate(data.entities))
    mappings = tuple(_existing_mapping_from_mapping(item, index) for index, item in enumerate(data.existing_mappings))
    targets = tuple(_existing_target_from_mapping(item, index) for index, item in enumerate(data.existing_targets))
    decisions, available, existing_keys = _base_decisions(candidates, mappings, targets)
    _reconcile_references(candidates, decisions, available, existing_keys)
    ordered = tuple(sorted(decisions, key=lambda decision: decision.key))
    counts = _counts(ordered)
    blocked = any(decision.status in {"conflict", "orphan"} for decision in ordered)
    unsigned: dict[str, Any] = {
        "schema_version": IDENTITY_SCHEMA_VERSION,
        "tool": "e4_identity_dry_run",
        "tool_version": E4_IDENTITY_TOOL_VERSION,
        "migration_batch_id": data.migration_batch_id,
        "snapshot_manifest_digest": data.snapshot_manifest_digest,
        "schema_revision": data.schema_revision,
        "correlation_id": data.correlation_id,
        "blocked": blocked,
        "counts": counts,
        "decisions": [_redacted_decision(decision) for decision in ordered],
    }
    digest = _report_digest(unsigned)
    return IdentityDryRunReport(
        migration_batch_id=data.migration_batch_id,
        snapshot_manifest_digest=data.snapshot_manifest_digest,
        schema_revision=data.schema_revision,
        correlation_id=data.correlation_id,
        decisions=ordered,
        counts=counts,
        blocked=blocked,
        report_sha256=digest,
    )


def write_identity_report(report: IdentityDryRunReport, output: str | os.PathLike[str] | Path) -> Path:
    """Write one new report atomically; never overwrite an existing artifact."""

    destination = Path(output).absolute()
    if destination.exists() or destination.is_symlink():
        raise IdentityDryRunError(f"E4 identity report output already exists: {destination.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging_fd, staging_name = tempfile.mkstemp(prefix=f".{destination.name}-", suffix=".tmp", dir=destination.parent)
    os.close(staging_fd)
    staging = Path(staging_name)
    try:
        rendered = json.dumps(identity_report_to_dict(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        staging.write_text(rendered, encoding="utf-8", newline="\n")
        staging.replace(destination)
    except BaseException:
        staging.unlink(missing_ok=True)
        raise
    return destination
