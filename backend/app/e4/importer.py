"""Transactional E4 business-bundle importer.

The importer is the first write-capable E4 adapter.  It accepts an explicit
JSON bundle, validates the same identity contract used by the offline dry-run,
and writes canonical shadow values plus the original business row in one SQL
unit of work.  It deliberately never discovers credentials, opens a source
store, commits a transaction, or performs a projection side effect.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.e4.identity import (
    IdentityDryRunReport,
    SourceKey,
    build_identity_dry_run,
    deterministic_target_uuid,
    load_identity_input,
)
from app.e4.repository import E4MigrationRepository, E4StateError
from app.models.chat_history import ChatMessage, ChatSession
from app.models.e4_migration import E4MigrationEntity
from app.models.embedding_config import UserEmbeddingConfig
from app.models.identity_domain import MigrationMap, User
from app.models.knowledge_document import KnowledgeSourceDocument
from app.models.memory_item import MemoryItem
from app.models.model_config import UserModelConfig
from app.models.note import Note
from app.models.note_template import NoteTemplate
from app.models.skill_domain import (
    Skill,
    SkillAlias,
    SkillAuditEvent,
    SkillCapabilityGrant,
    SkillImport,
    SkillInstallation,
    SkillRegistryEvent,
    SkillRegistryState,
    SkillRunBinding,
    SkillVersion,
)

E4_BUSINESS_BUNDLE_SCHEMA_VERSION = 1
E4_BUSINESS_SCHEMA_REVISION = "20260905_0008_e4_business_shadow"
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_MD5_RE = re.compile(r"^[0-9a-fA-F]{32}$")
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_BATCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_MAX_ENTITY_COUNT = 1_000_000
_MAX_MEDIA_COUNT = 100_000
_MAX_MEDIA_BYTES = 256 * 1024 * 1024
_SECRET_KEYS = frozenset(
    {
        "api_key",
        "database_url",
        "dsn",
        "password",
        "passwd",
        "raw_blob",
        "refresh_token",
        "secret",
        "token",
    }
)
_ENCRYPTED_KEY = "api_key_encrypted"
_KEY_VERSION_KEY = "api_key_key_version"


class E4ImportError(ValueError):
    """Base error for malformed or rejected E4 business input."""


class E4BundleValidationError(E4ImportError):
    """The explicit bundle does not satisfy the frozen E4 contract."""


class E4ImportBlocked(E4ImportError):
    """Identity, FK, uniqueness, or key-version gates blocked the batch."""

    def __init__(self, message: str, *, report: IdentityDryRunReport | None = None) -> None:
        self.report = report
        super().__init__(message)


class E4ImportConflict(E4ImportError):
    """A target row conflicts with an immutable source fact."""


@dataclass(frozen=True, slots=True)
class E4BusinessBundle:
    migration_batch_id: str
    snapshot_manifest_digest: str
    schema_revision: str
    correlation_id: str
    entities: tuple[Mapping[str, Any], ...]
    media: tuple[Mapping[str, Any], ...]
    existing_mappings: tuple[Mapping[str, Any], ...]
    existing_targets: tuple[Mapping[str, Any], ...]
    actor_id: str | None = None
    manifest: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class E4ImportResult:
    migration_batch_id: str
    correlation_id: str
    dry_run: bool
    total_entities: int
    imported_entities: int
    skipped_entities: int
    quarantined_entities: int
    media_imported: int
    blocked_entities: int
    report_sha256: str
    processed_source_keys: tuple[str, ...] = ()

    @property
    def imported_count(self) -> int:
        return self.imported_entities

    @property
    def blocked(self) -> bool:
        """Whether this result must stop a batch runner with a failure code."""

        return bool(self.blocked_entities or self.quarantined_entities)

    def as_dict(self) -> dict[str, Any]:
        return {
            "migration_batch_id": self.migration_batch_id,
            "correlation_id": self.correlation_id,
            "dry_run": self.dry_run,
            "total_entities": self.total_entities,
            "imported_entities": self.imported_entities,
            "skipped_entities": self.skipped_entities,
            "quarantined_entities": self.quarantined_entities,
            "media_imported": self.media_imported,
            "blocked_entities": self.blocked_entities,
            "blocked": self.blocked,
            "report_sha256": self.report_sha256,
            "processed_source_keys": list(self.processed_source_keys),
        }


# The aliases keep the public adapter name flexible for operational scripts.
ImportResult = E4ImportResult
BusinessBundle = E4BusinessBundle


_MODEL_BY_ENTITY_TYPE: dict[str, type] = {
    "session": ChatSession,
    "chat_session": ChatSession,
    "message": ChatMessage,
    "chat_message": ChatMessage,
    "note": Note,
    "memory": MemoryItem,
    "knowledge_document": KnowledgeSourceDocument,
    "knowledge_source_document": KnowledgeSourceDocument,
    "note_template": NoteTemplate,
    "template": NoteTemplate,
    "model_config": UserModelConfig,
    "user_model_config": UserModelConfig,
    "embedding_config": UserEmbeddingConfig,
    "user_embedding_config": UserEmbeddingConfig,
    "skill_run_binding": SkillRunBinding,
    "skill": Skill,
    "skill_alias": SkillAlias,
    "skill_version": SkillVersion,
    "skill_installation": SkillInstallation,
    "skill_capability_grant": SkillCapabilityGrant,
    "skill_import": SkillImport,
    "skill_audit_event": SkillAuditEvent,
    "skill_registry_event": SkillRegistryEvent,
    "skill_registry_state": SkillRegistryState,
}


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise E4BundleValidationError("E4 bundle contains non-deterministic JSON") from exc


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _required_text(value: object, field: str, maximum: int = 255) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > maximum:
        raise E4BundleValidationError(f"{field} must be a non-empty string of at most {maximum} characters")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise E4BundleValidationError(f"{field} contains a control character")
    return value


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
        raise E4BundleValidationError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _uuid(value: object, field: str) -> str:
    if not isinstance(value, str) or not _UUID_RE.fullmatch(value) or value != value.lower():
        raise E4BundleValidationError(f"{field} must be a lowercase canonical UUID")
    try:
        UUID(value)
    except ValueError as exc:
        raise E4BundleValidationError(f"{field} must be a lowercase canonical UUID") from exc
    return value


def _normalise_source_id(value: object, *, source_system: str, entity_type: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise E4BundleValidationError("source_id must be a string or non-negative integer")
    if isinstance(value, int):
        if value < 0:
            raise E4BundleValidationError("source_id integer must be non-negative")
        return str(value)
    source_id = _required_text(value, "source_id", 255)
    if source_system != "django" and _UUID_RE.fullmatch(source_id.casefold()):
        source_id = source_id.casefold()
    if (
        source_system == "fastapi_legacy"
        and entity_type in {"session", "message", "note", "memory", "knowledge_document"}
        and source_id.isdecimal()
    ):
        source_id = str(int(source_id))
    return source_id


def _source_key(value: Mapping[str, Any], *, field: str = "entity") -> SourceKey:
    source_system = _required_text(value.get("source_system"), f"{field}.source_system", 64).casefold()
    entity_type = _required_text(value.get("entity_type"), f"{field}.entity_type", 64).casefold()
    source_id = _normalise_source_id(value.get("source_id"), source_system=source_system, entity_type=entity_type)
    return SourceKey(source_system, entity_type, source_id)


def _reject_plain_secrets(value: object, *, path: str = "bundle", allow_encrypted: bool = True) -> None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key).casefold()
            if key in _SECRET_KEYS or (key == _ENCRYPTED_KEY and not allow_encrypted):
                raise E4BundleValidationError(f"E4 bundle {path} contains prohibited secret material")
            _reject_plain_secrets(child, path=f"{path}.{raw_key}", allow_encrypted=allow_encrypted)
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_plain_secrets(child, path=f"{path}[{index}]", allow_encrypted=allow_encrypted)


def _read_document(source: Mapping[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(source, Mapping):
        document = dict(source)
    else:
        path = Path(source)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise E4BundleValidationError("E4 business bundle is not valid JSON") from exc
    if not isinstance(document, dict):
        raise E4BundleValidationError("E4 business bundle must be a JSON object")
    _reject_plain_secrets(document)
    return document


def _verify_manifest(document: Mapping[str, Any], snapshot_digest: str) -> Mapping[str, Any] | None:
    manifest = document.get("manifest", document.get("snapshot_manifest"))
    if manifest is None:
        declared = document.get("manifest_sha256")
        if declared is not None and _digest(declared, "manifest_sha256") != snapshot_digest:
            raise E4BundleValidationError("manifest_sha256 does not match snapshot_manifest_digest")
        return None
    if not isinstance(manifest, Mapping):
        raise E4BundleValidationError("manifest must be a JSON object")
    declared = manifest.get("manifest_sha256")
    if declared is None:
        raise E4BundleValidationError("manifest must contain manifest_sha256")
    declared = _digest(declared, "manifest.manifest_sha256")
    unsigned = {key: value for key, value in manifest.items() if key not in {"manifest_sha256", "captured_at"}}
    if _sha256_json(unsigned) != declared:
        raise E4BundleValidationError("snapshot manifest digest is not reproducible")
    if declared != snapshot_digest:
        raise E4BundleValidationError("manifest_sha256 does not match snapshot_manifest_digest")
    return dict(manifest)


def _identity_projection(entities: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    projection: list[dict[str, Any]] = []
    for index, entity in enumerate(entities):
        if not isinstance(entity, Mapping):
            raise E4BundleValidationError(f"entities[{index}] must be an object")
        item = {
            key: value
            for key, value in entity.items()
            if key not in {"data", "row", "record", "payload", _ENCRYPTED_KEY, _KEY_VERSION_KEY}
        }
        if "scope" not in item and "scope_type" in item:
            item["scope"] = item["scope_type"]
        projection.append(item)
    return projection


def _validate_media_only_identity_facts(
    existing_mappings: Sequence[Mapping[str, Any]],
    existing_targets: Sequence[Mapping[str, Any]],
) -> None:
    """Validate optional owner facts without weakening the identity contract.

    The standalone identity dry-run intentionally requires at least one entity.
    A media-only business bundle still needs to validate any explicitly supplied
    mapping/target facts, so it uses the same field-level rules here without
    manufacturing a synthetic entity.
    """

    seen_mapping_keys: set[SourceKey] = set()
    seen_mapping_targets: set[str] = set()
    for index, item in enumerate(existing_mappings):
        if not isinstance(item, Mapping):
            raise E4BundleValidationError(f"existing_mappings[{index}] must be an object")
        key = _source_key(item, field=f"existing_mappings[{index}]")
        if key in seen_mapping_keys:
            raise E4BundleValidationError("existing_mappings contains duplicate source keys")
        target = _uuid(item.get("target_uuid"), f"existing_mappings[{index}].target_uuid")
        if target != deterministic_target_uuid(key):
            raise E4BundleValidationError("existing mapping violates the deterministic target UUID rule")
        _digest(item.get("source_digest"), f"existing_mappings[{index}].source_digest")
        status = _required_text(item.get("status"), f"existing_mappings[{index}].status", 16).casefold()
        if status not in {"mapped", "conflict", "error"}:
            raise E4BundleValidationError("existing_mappings contains an unsupported status")
        if target in seen_mapping_targets:
            raise E4BundleValidationError("existing_mappings reuses one target UUID for different source keys")
        seen_mapping_keys.add(key)
        seen_mapping_targets.add(target)

    seen_targets: set[str] = set()
    for index, raw_item in enumerate(existing_targets):
        item = raw_item if isinstance(raw_item, Mapping) else {"target_uuid": raw_item}
        target = _uuid(item.get("target_uuid"), f"existing_targets[{index}].target_uuid")
        if target in seen_targets:
            raise E4BundleValidationError("existing_targets contains duplicate target UUIDs")
        source_key = item.get("source_key")
        if source_key is not None:
            key = _source_key(source_key, field=f"existing_targets[{index}].source_key")
            if target != deterministic_target_uuid(key):
                raise E4BundleValidationError("existing target violates the deterministic target UUID rule")
        seen_targets.add(target)


def _empty_identity_report(
    bundle: E4BusinessBundle,
    *,
    blocked: bool = False,
    mapping_count: int = 0,
    conflict_count: int = 0,
) -> IdentityDryRunReport:
    mapping_count = max(0, int(mapping_count))
    conflict_count = max(0, min(mapping_count, int(conflict_count)))
    counts = {
        "source_key_total": mapping_count,
        "normalized_count": mapping_count,
        "invalid_count": 0,
        "duplicate_count": 0,
        "validated_count": mapping_count - conflict_count,
        "already_mapped_count": mapping_count - conflict_count,
        "conflict_count": conflict_count,
        "orphan_count": 0,
        "target_uuid_collision_count": 0,
        "unique_conflict_count": 0,
        "expected_inserts": 0,
        "expected_noops": mapping_count - conflict_count,
    }
    unsigned = {
        "schema_version": 1,
        "tool": "e4_identity_dry_run",
        "tool_version": "1.1",
        "migration_batch_id": bundle.migration_batch_id,
        "snapshot_manifest_digest": bundle.snapshot_manifest_digest,
        "schema_revision": bundle.schema_revision,
        "correlation_id": bundle.correlation_id,
        "blocked": blocked,
        "counts": counts,
        "decisions": [],
    }
    return IdentityDryRunReport(
        migration_batch_id=bundle.migration_batch_id,
        snapshot_manifest_digest=bundle.snapshot_manifest_digest,
        schema_revision=bundle.schema_revision,
        correlation_id=bundle.correlation_id,
        decisions=(),
        counts=counts,
        blocked=blocked,
        report_sha256=hashlib.sha256(_canonical_json(unsigned).encode("utf-8")).hexdigest(),
    )


def load_business_bundle(source: Mapping[str, Any] | str | Path | E4BusinessBundle) -> E4BusinessBundle:
    """Parse and validate an explicit E4 business bundle without DB access."""

    if isinstance(source, E4BusinessBundle):
        # Dataclass callers must pass through the same contract as JSON
        # callers.  Type annotations and frozen fields are not a validation
        # boundary, and a hand-built instance may contain invalid IDs,
        # digests, aliases, or secret-bearing row data.
        source = {
            "artifact_kind": "e4-business-bundle",
            "schema_version": E4_BUSINESS_BUNDLE_SCHEMA_VERSION,
            "migration_batch_id": source.migration_batch_id,
            "snapshot_manifest_digest": source.snapshot_manifest_digest,
            "schema_revision": source.schema_revision,
            "correlation_id": source.correlation_id,
            "entities": source.entities,
            "media": source.media,
            "existing_mappings": source.existing_mappings,
            "existing_targets": source.existing_targets,
            "actor_id": source.actor_id,
            "manifest": source.manifest,
        }
    document = _read_document(source)
    if document.get("artifact_kind", "e4-business-bundle") != "e4-business-bundle":
        raise E4BundleValidationError("unsupported E4 business bundle artifact_kind")
    if document.get("schema_version", E4_BUSINESS_BUNDLE_SCHEMA_VERSION) != E4_BUSINESS_BUNDLE_SCHEMA_VERSION:
        raise E4BundleValidationError("unsupported E4 business bundle schema version")
    batch_id = _required_text(document.get("migration_batch_id"), "migration_batch_id", 64)
    if not _BATCH_RE.fullmatch(batch_id):
        raise E4BundleValidationError("migration_batch_id has an invalid format")
    snapshot_digest = _digest(document.get("snapshot_manifest_digest"), "snapshot_manifest_digest")
    schema_revision = _required_text(document.get("schema_revision"), "schema_revision", 128)
    if schema_revision != E4_BUSINESS_SCHEMA_REVISION:
        raise E4BundleValidationError("E4 business bundle schema_revision is not the reviewed revision")
    correlation_id = _uuid(document.get("correlation_id"), "correlation_id")
    raw_entities = document.get("entities", ())
    raw_media = document.get("media", document.get("media_assets", ()))
    if not isinstance(raw_entities, Sequence) or isinstance(raw_entities, (str, bytes)):
        raise E4BundleValidationError("entities must be a list")
    if not isinstance(raw_media, Sequence) or isinstance(raw_media, (str, bytes)):
        raise E4BundleValidationError("media must be a list")
    if not raw_entities and not raw_media:
        raise E4BundleValidationError("E4 business bundle must contain entities or media")
    if len(raw_entities) > _MAX_ENTITY_COUNT or len(raw_media) > _MAX_MEDIA_COUNT:
        raise E4BundleValidationError("E4 business bundle exceeds the supported item count")
    entities = tuple(item for item in raw_entities if isinstance(item, Mapping))
    media = tuple(item for item in raw_media if isinstance(item, Mapping))
    if len(entities) != len(raw_entities) or len(media) != len(raw_media):
        raise E4BundleValidationError("entities and media entries must be objects")
    for index, entity in enumerate(entities):
        _source_key(entity, field=f"entities[{index}]")
        _digest(entity.get("entity_content_digest"), f"entities[{index}].entity_content_digest")
        scope = entity.get("scope", entity.get("scope_type"))
        if not isinstance(scope, str) or scope.casefold() not in {"user", "global"}:
            raise E4BundleValidationError(f"entities[{index}].scope must be user or global")
        if entity.get("data", entity.get("row", entity.get("record", {}))) is not None and not isinstance(
            entity.get("data", entity.get("row", entity.get("record", {}))), Mapping
        ):
            raise E4BundleValidationError(f"entities[{index}] row data must be an object")
    for index, item in enumerate(media):
        _source_key({**item, "entity_type": item.get("entity_type", "media")}, field=f"media[{index}]")
        _digest(item.get("content_digest"), f"media[{index}].content_digest")
        scope = item.get("scope", item.get("scope_type"))
        if not isinstance(scope, str) or scope.casefold() not in {"user", "global"}:
            raise E4BundleValidationError(f"media[{index}].scope must be user or global")
    existing_mappings = document.get("existing_mappings", ())
    existing_targets = document.get("existing_targets", ())
    if not isinstance(existing_mappings, Sequence) or isinstance(existing_mappings, (str, bytes)):
        raise E4BundleValidationError("existing_mappings must be a list")
    if not isinstance(existing_targets, Sequence) or isinstance(existing_targets, (str, bytes)):
        raise E4BundleValidationError("existing_targets must be a list")
    manifest = _verify_manifest(document, snapshot_digest)
    projection = _identity_projection(entities)
    identity_document = {
        "schema_version": 1,
        "migration_batch_id": batch_id,
        "snapshot_manifest_digest": snapshot_digest,
        "schema_revision": schema_revision,
        "correlation_id": correlation_id,
        "entities": projection,
        "existing_mappings": list(existing_mappings),
        "existing_targets": list(existing_targets),
    }
    if entities:
        load_identity_input(identity_document)
    else:
        _validate_media_only_identity_facts(existing_mappings, existing_targets)
    actor_id = document.get("actor_id")
    if actor_id is not None:
        actor_id = _required_text(actor_id, "actor_id", 64)
    return E4BusinessBundle(
        migration_batch_id=batch_id,
        snapshot_manifest_digest=snapshot_digest,
        schema_revision=schema_revision,
        correlation_id=correlation_id,
        entities=entities,
        media=media,
        existing_mappings=tuple(item for item in existing_mappings if isinstance(item, Mapping)),
        existing_targets=tuple(item if isinstance(item, Mapping) else {"target_uuid": item} for item in existing_targets),
        actor_id=actor_id,
        manifest=manifest,
    )


def build_business_dry_run(bundle: E4BusinessBundle | Mapping[str, Any] | str | Path) -> IdentityDryRunReport:
    """Build the redacted identity report without opening a database."""

    parsed = load_business_bundle(bundle)
    if not parsed.entities:
        non_mapped = sum(
            str(item.get("status", "")).casefold() != "mapped"
            for item in parsed.existing_mappings
        )
        return _empty_identity_report(
            parsed,
            blocked=non_mapped > 0,
            mapping_count=len(parsed.existing_mappings),
            conflict_count=non_mapped,
        )
    identity_input = _entity_identity_input(
        parsed,
        existing_mappings=parsed.existing_mappings,
        existing_targets=parsed.existing_targets,
    )
    return build_identity_dry_run(identity_input)


def bundle_file_sha256(source: str | Path) -> str:
    """Return the exact JSON bundle file digest for CLI evidence."""

    path = Path(source)
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise E4BundleValidationError("E4 business bundle cannot be read") from exc


def _entity_identity_input(bundle: E4BusinessBundle, *, existing_mappings, existing_targets) -> Any:
    return load_identity_input(
        {
            "schema_version": 1,
            "migration_batch_id": bundle.migration_batch_id,
            "snapshot_manifest_digest": bundle.snapshot_manifest_digest,
            "schema_revision": bundle.schema_revision,
            "correlation_id": bundle.correlation_id,
            "entities": _identity_projection(bundle.entities),
            "existing_mappings": list(existing_mappings),
            "existing_targets": list(existing_targets),
        }
    )


def _source_key_token(key: SourceKey) -> str:
    return hashlib.sha256(f"{key.source_system}\x1f{key.entity_type}\x1f{key.source_id}".encode("utf-8")).hexdigest()


def _identity_key_map(bundle: E4BusinessBundle) -> dict[SourceKey, Mapping[str, Any]]:
    return {_source_key(entity, field="entity"): entity for entity in bundle.entities}


def _ordered_entity_keys(bundle: E4BusinessBundle) -> tuple[SourceKey, ...]:
    """Return a deterministic dependency-first order for a partial import."""

    entity_by_key = _identity_key_map(bundle)
    dependencies: dict[SourceKey, set[SourceKey]] = {key: set() for key in entity_by_key}
    for key, entity in entity_by_key.items():
        references: list[Mapping[str, Any]] = []
        owner = entity.get("owner")
        if isinstance(owner, Mapping):
            references.append(owner)
        foreign_keys = entity.get("foreign_keys", ())
        if isinstance(foreign_keys, Sequence) and not isinstance(foreign_keys, (str, bytes)):
            references.extend(reference for reference in foreign_keys if isinstance(reference, Mapping))
        for reference in references:
            reference_key = _source_key(reference, field="entity.reference")
            if reference_key in entity_by_key and reference_key != key:
                dependencies[key].add(reference_key)

        # Legacy chat messages may carry only a row-level session_id rather
        # than an explicit foreign_keys entry.  Infer a dependency only when
        # the matching session is present in this bundle; otherwise the
        # existing target row remains the authoritative FK check.
        if key.entity_type in {"message", "chat_message"}:
            legacy_session_id = _row_data(entity).get("session_id")
            if legacy_session_id is not None:
                for session_type in ("session", "chat_session"):
                    try:
                        session_key = _source_key(
                            {
                                "source_system": key.source_system,
                                "entity_type": session_type,
                                "source_id": legacy_session_id,
                            },
                            field="entity.row.session_id",
                        )
                    except E4BundleValidationError:
                        continue
                    if session_key in entity_by_key and session_key != key:
                        dependencies[key].add(session_key)

    priority = {
        "user": 0,
        "session": 1,
        "chat_session": 1,
        "message": 2,
        "chat_message": 2,
    }

    def sort_key(key: SourceKey) -> tuple[int, str, str, str]:
        return (priority.get(key.entity_type, 10), key.source_system, key.entity_type, key.source_id)

    ordered: list[SourceKey] = []
    remaining = {key: set(value) for key, value in dependencies.items()}
    while remaining:
        ready = sorted((key for key, refs in remaining.items() if not refs), key=sort_key)
        if not ready:
            # Cycles cannot be made safe by guessing; retain a stable order so
            # the first FK failure identifies the blocking cycle deterministically.
            ordered.extend(sorted(remaining, key=sort_key))
            break
        ordered.extend(ready)
        for key in ready:
            remaining.pop(key, None)
        for refs in remaining.values():
            refs.difference_update(ready)
    return tuple(ordered)


def _row_data(entity: Mapping[str, Any]) -> dict[str, Any]:
    value = entity.get("data", entity.get("row", entity.get("record", {})))
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise E4BundleValidationError("entity row data must be an object")
    return dict(value)


def _normalise_row_columns(model: type, value: Mapping[str, Any]) -> dict[str, Any]:
    """Translate SQL column names to SQLAlchemy constructor attribute names."""

    column_attributes = {
        column.key: column.key
        for column in model.__table__.columns
    }
    column_attributes.update(
        {
            column.name: property_.key
            for property_ in model.__mapper__.column_attrs
            for column in property_.columns
        }
    )
    result: dict[str, Any] = {}
    for raw_key, raw_value in value.items():
        if not isinstance(raw_key, str):
            raise E4BundleValidationError("entity row column names must be strings")
        key = column_attributes.get(raw_key)
        if key is None:
            raise E4BundleValidationError(f"entity row contains unknown columns: {raw_key}")
        if key in result and result[key] != raw_value:
            raise E4ImportConflict(f"entity row specifies conflicting aliases for {key}")
        result[key] = raw_value
    for attribute in model.__mapper__.column_attrs:
        value = result.get(attribute.key)
        if isinstance(attribute.columns[0].type, DateTime) and isinstance(value, str):
            try:
                result[attribute.key] = datetime.fromisoformat(value)
            except ValueError as exc:
                raise E4BundleValidationError("entity row datetime must be ISO formatted") from exc
    return result


def _decode_base64_bytes(value: object, field: str) -> bytes:
    if isinstance(value, bytes):
        return value
    if not isinstance(value, str):
        raise E4BundleValidationError(f"{field} must be strict base64")
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error) as exc:
        raise E4BundleValidationError(f"{field} must be strict base64") from exc


def _reference_target(reference: Mapping[str, Any], decisions: Mapping[SourceKey, Any], field: str) -> str:
    key = _source_key(reference, field=field)
    decision = decisions.get(key)
    if decision is not None:
        if decision.target_uuid is None or decision.status in {"conflict", "orphan"}:
            raise E4ImportBlocked(f"{field} mapping is unavailable")
        return decision.target_uuid
    return deterministic_target_uuid(key)


def _session_reference(
    entity: Mapping[str, Any],
    row: Mapping[str, Any],
    decisions: Mapping[SourceKey, Any],
) -> tuple[str | None, str | None]:
    """Resolve a legacy/canonical session reference for message-like rows."""

    references = entity.get("foreign_keys", ())
    session_ref: Mapping[str, Any] | None = None
    if isinstance(references, Sequence) and not isinstance(references, (str, bytes)):
        for reference in references:
            if isinstance(reference, Mapping) and str(reference.get("entity_type", "")).casefold() in {
                "session",
                "chat_session",
            }:
                session_ref = reference
                break
    legacy_id = None
    if session_ref is not None:
        session_ref_key = _source_key(session_ref, field="entity.foreign_keys.session")
        legacy_id = session_ref_key.source_id
        target = _reference_target(session_ref, decisions, "entity.foreign_keys.session")
    else:
        target = row.get("canonical_session_id")
        if target is not None:
            target = _uuid(target, "canonical_session_id")
        legacy_value = row.get("session_id")
        legacy_id = None if legacy_value is None else str(legacy_value)
    if session_ref is not None and row.get("session_id") is not None and legacy_id != str(row["session_id"]):
        raise E4ImportConflict("business row session_id conflicts with foreign_keys")
    if session_ref is not None and row.get("canonical_session_id") is not None:
        declared = _uuid(row["canonical_session_id"], "canonical_session_id")
        if declared != target:
            raise E4ImportConflict("business row canonical_session_id conflicts with foreign_keys")
    return target, legacy_id


def _model_for_entity(entity_type: str) -> type:
    try:
        return _MODEL_BY_ENTITY_TYPE[entity_type.casefold()]
    except KeyError as exc:
        raise E4ImportBlocked(f"unsupported E4 business entity_type: {entity_type}") from exc


def _media_owner_keys(bundle: E4BusinessBundle) -> list[SourceKey]:
    keys: list[SourceKey] = []
    for item in bundle.media:
        owner = item.get("owner")
        if isinstance(owner, Mapping):
            keys.append(_source_key(owner, field="media.owner"))
    return keys


async def _load_authoritative_facts(session: AsyncSession, bundle: E4BusinessBundle) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    keys = [_source_key(entity) for entity in bundle.entities]
    for key in _media_owner_keys(bundle):
        if key not in keys:
            keys.append(key)
    existing_mappings: list[dict[str, Any]] = []
    if keys:
        rows = (
            await session.scalars(
                select(MigrationMap).where(
                    MigrationMap.source_system.in_([key.source_system for key in keys]),
                    MigrationMap.entity_type.in_([key.entity_type for key in keys]),
                    MigrationMap.source_id.in_([key.source_id for key in keys]),
                )
            )
        ).all()
        wanted = {(key.source_system, key.entity_type, key.source_id) for key in keys}
        for row in rows:
            if (row.source_system, row.entity_type, row.source_id) in wanted:
                existing_mappings.append(
                    {
                        "source_system": row.source_system,
                        "entity_type": row.entity_type,
                        "source_id": row.source_id,
                        "target_uuid": row.target_uuid,
                        "source_digest": row.source_digest,
                        "status": row.status,
                    }
                )

    # Target collision checks apply to the entities being imported.  Owner
    # keys are included above for mapping lookup, but their canonical user
    # rows are references, not candidate targets for this bundle.
    candidate_keys = [_source_key(entity) for entity in bundle.entities]
    target_uuids = [deterministic_target_uuid(key) for key in candidate_keys]
    existing_targets: list[dict[str, Any]] = []
    # Every E4 shadow-enabled table is queried independently so a canonical
    # UUID present without migration_maps is still a fail-closed collision.
    # Include both canonical users and prior E4 migration rows in the target
    # scan.  A UUID already owned by either table is not safe to reuse merely
    # because an older batch has not yet materialized a MigrationMap row.
    target_columns = (
        (User, User.id),
        (E4MigrationEntity, E4MigrationEntity.target_uuid),
        (ChatSession, getattr(ChatSession, "canonical_id", None)),
        (ChatMessage, getattr(ChatMessage, "canonical_id", None)),
        (KnowledgeSourceDocument, getattr(KnowledgeSourceDocument, "canonical_id", None)),
        (MemoryItem, getattr(MemoryItem, "canonical_id", None)),
        (NoteTemplate, getattr(NoteTemplate, "canonical_id", None)),
        (Note, getattr(Note, "canonical_id", None)),
        (UserEmbeddingConfig, getattr(UserEmbeddingConfig, "canonical_id", None)),
        (UserModelConfig, getattr(UserModelConfig, "canonical_id", None)),
    )
    for model, canonical_column in target_columns:
        if canonical_column is None:
            continue
        try:
            values = (await session.scalars(select(canonical_column).where(canonical_column.in_(target_uuids)))).all()
        except SQLAlchemyError as exc:
            raise E4ImportError(f"unable to inspect canonical targets for {model.__tablename__}") from exc
        existing_targets.extend({"target_uuid": value} for value in values if value is not None)
    deduplicated_targets = {item["target_uuid"]: item for item in existing_targets}
    return existing_mappings, list(deduplicated_targets.values())


def _merge_facts(
    bundle: E4BusinessBundle,
    actual_mappings: Sequence[Mapping[str, Any]],
    actual_targets: Sequence[Mapping[str, Any]],
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    supplied_mappings = {
        (_source_key(item).source_system, _source_key(item).entity_type, _source_key(item).source_id): item
        for item in bundle.existing_mappings
    }
    actual_map = {
        (_source_key(item).source_system, _source_key(item).entity_type, _source_key(item).source_id): item
        for item in actual_mappings
    }
    for key, supplied in supplied_mappings.items():
        actual = actual_map.get(key)
        if actual is not None and dict(supplied) != dict(actual):
            raise E4ImportBlocked("bundle existing_mappings disagree with authoritative SQL facts")
        if actual is None:
            # Owner/FK mappings may intentionally refer to a user or another
            # E3 entity that is outside this bundle's business-row set.  Keep
            # the explicit immutable fact after confirming no SQL fact
            # contradicts it.
            actual_map[key] = supplied
    supplied_targets = {str(item.get("target_uuid")) for item in bundle.existing_targets}
    actual_target_values = {str(item.get("target_uuid")) for item in actual_targets}
    if supplied_targets and supplied_targets != actual_target_values:
        raise E4ImportBlocked("bundle existing_targets disagree with authoritative SQL facts")
    return list(actual_map.values()), list(actual_targets)


async def _resolve_owner(
    session: AsyncSession,
    entity: Mapping[str, Any],
    decisions: Mapping[SourceKey, Any],
) -> str | None:
    scope = str(entity.get("scope", entity.get("scope_type", ""))).casefold()
    owner = entity.get("owner")
    explicit = entity.get("canonical_user_id")
    row = _row_data(entity)
    if explicit is None:
        explicit = row.get("canonical_user_id")
    if scope == "global":
        if owner is not None or explicit is not None:
            raise E4ImportBlocked("global entity cannot have an owner")
        return None
    if scope != "user":
        raise E4ImportBlocked("entity scope must be user or global")
    owner_target = None
    if owner is not None:
        owner_key = _source_key(owner, field="owner")
        decision = decisions.get(owner_key)
        if decision is not None:
            if decision.target_uuid is None or decision.status in {"conflict", "orphan"}:
                raise E4ImportBlocked("user entity owner mapping is unavailable")
            owner_target = decision.target_uuid
        else:
            persisted = await session.scalar(
                select(MigrationMap).where(
                    MigrationMap.source_system == owner_key.source_system,
                    MigrationMap.entity_type == owner_key.entity_type,
                    MigrationMap.source_id == owner_key.source_id,
                )
            )
            if persisted is not None:
                if persisted.status != "mapped":
                    raise E4ImportBlocked("user entity owner mapping is unavailable")
                owner_target = persisted.target_uuid
            else:
                owner_target = deterministic_target_uuid(owner_key)
    if explicit is not None:
        explicit = _uuid(explicit, "canonical_user_id")
    if owner_target is not None and explicit is not None and owner_target != explicit:
        raise E4ImportBlocked("owner source mapping conflicts with canonical_user_id")
    canonical_user_id = explicit or owner_target
    if canonical_user_id is None:
        raise E4ImportBlocked("user entity requires canonical_user_id or owner")
    if await session.get(User, canonical_user_id) is None:
        raise E4ImportBlocked("canonical_user_id does not reference an existing user")
    return canonical_user_id


def _has_column(model: type, name: str) -> bool:
    return name in model.__table__.columns


def _primary_key_name(model: type) -> str:
    keys = tuple(column.name for column in model.__table__.primary_key.columns)
    if len(keys) != 1:
        raise E4ImportBlocked(f"E4 importer requires a single-column primary key for {model.__tablename__}")
    return keys[0]


def _prepare_row(
    model: type,
    entity: Mapping[str, Any],
    target_uuid: str,
    canonical_user_id: str | None,
    decisions: Mapping[SourceKey, Any],
) -> dict[str, Any]:
    raw_row = _row_data(entity)
    encoded_blob = entity.get("content_blob_base64", raw_row.pop("content_blob_base64", None))
    row = _normalise_row_columns(model, raw_row)
    key = _source_key(entity)
    primary_key = _primary_key_name(model)
    source_id = key.source_id
    if primary_key == "id":
        if model is ChatMessage:
            if not source_id.isdecimal():
                raise E4ImportBlocked("chat message source_id must be a decimal legacy integer")
            source_value: Any = int(source_id)
        else:
            source_value = source_id
        if "id" in row and str(row["id"]) != str(source_value):
            raise E4ImportConflict("business row id conflicts with source_id")
        row["id"] = source_value
    if _has_column(model, "canonical_id"):
        if "canonical_id" in row and row["canonical_id"] not in {None, target_uuid}:
            raise E4ImportConflict("business row canonical_id conflicts with identity mapping")
        row["canonical_id"] = target_uuid
    if _has_column(model, "canonical_user_id"):
        if canonical_user_id is not None:
            if row.get("canonical_user_id") not in {None, canonical_user_id}:
                raise E4ImportConflict("business row canonical_user_id conflicts with owner mapping")
            row["canonical_user_id"] = canonical_user_id
        elif row.get("canonical_user_id") is not None:
            raise E4ImportConflict("global business row cannot contain canonical_user_id")
    if model is ChatMessage:
        canonical_session_id, legacy_session_id = _session_reference(entity, row, decisions)
        if canonical_session_id is not None:
            row["canonical_session_id"] = canonical_session_id
        if legacy_session_id is not None:
            row["session_id"] = legacy_session_id
    if _has_column(model, "content_digest"):
        row["content_digest"] = _digest(entity.get("entity_content_digest"), "entity_content_digest")
    if _has_column(model, "artifact_digest") and entity.get("artifact_digest") is not None:
        row["artifact_digest"] = _digest(entity.get("artifact_digest"), "artifact_digest")
    if _has_column(model, _KEY_VERSION_KEY):
        version = entity.get(_KEY_VERSION_KEY, row.get(_KEY_VERSION_KEY))
        if version is not None:
            row[_KEY_VERSION_KEY] = _required_text(version, _KEY_VERSION_KEY, 64)
    if _has_column(model, "content_blob"):
        if encoded_blob is not None:
            row["content_blob"] = _decode_base64_bytes(encoded_blob, "content_blob_base64")
        blob = row.get("content_blob")
        if not isinstance(blob, bytes) or not blob:
            raise E4BundleValidationError("knowledge document content_blob_base64 is required")
        if entity.get("artifact_digest") is not None and hashlib.sha256(blob).hexdigest() != entity["artifact_digest"]:
            raise E4ImportConflict("content_blob bytes conflict with artifact_digest")
        if row.get("md5") is None and entity.get("legacy_md5") is not None:
            row["md5"] = entity["legacy_md5"].casefold()
        if row.get("file_size") is None:
            row["file_size"] = len(blob)
    if _has_column(model, "user_id") and row.get("user_id") is None:
        owner = entity.get("owner")
        if isinstance(owner, Mapping) and owner.get("source_id") is not None:
            row["user_id"] = str(owner["source_id"])
    return row


def _encrypted_key_requires_quarantine(model: type, entity: Mapping[str, Any], row: Mapping[str, Any]) -> bool:
    if not _has_column(model, _ENCRYPTED_KEY):
        return False
    ciphertext = row.get(_ENCRYPTED_KEY)
    if ciphertext in {None, ""}:
        return False
    version = entity.get(_KEY_VERSION_KEY, row.get(_KEY_VERSION_KEY))
    return not isinstance(version, str) or not version.strip()


async def _find_existing_row(session: AsyncSession, model: type, row: Mapping[str, Any], target_uuid: str):
    canonical_column = getattr(model, "canonical_id", None)
    if canonical_column is not None:
        existing = await session.scalar(select(model).where(canonical_column == target_uuid).with_for_update())
        if existing is not None:
            return existing
    primary_key = _primary_key_name(model)
    if primary_key in row:
        return await session.get(model, row[primary_key], with_for_update=True)
    return None


def _row_matches(existing: Any, row: Mapping[str, Any]) -> bool:
    # Compare only explicit source values; server timestamps and defaults are
    # intentionally excluded from replay equality.
    for key, value in row.items():
        if key in {"created_at", "updated_at"}:
            continue
        current = getattr(existing, key, None)
        if current != value:
            return False
    return True


async def _write_business_row(session: AsyncSession, model: type, row: Mapping[str, Any], target_uuid: str):
    existing = await _find_existing_row(session, model, row, target_uuid)
    if existing is not None:
        if not _row_matches(existing, row):
            raise E4ImportConflict("existing business row conflicts with immutable source facts")
        return existing, False
    instance = model(**row)
    try:
        # Keep constraint failures inside a savepoint.  Without this nested
        # transaction, SQLAlchemy marks the caller's session as failed and the
        # importer cannot persist the corresponding conflict state/audit event
        # or safely continue a caller-owned transaction.
        async with session.begin_nested():
            session.add(instance)
            await session.flush()
    except IntegrityError as exc:
        raise E4ImportConflict(f"business row uniqueness or foreign-key constraint rejected {model.__tablename__}") from exc
    return instance, True


def _decode_media(item: Mapping[str, Any]) -> bytes:
    value = item.get("content_blob_base64", item.get("content_blob"))
    if isinstance(value, bytes):
        blob = value
    elif isinstance(value, str):
        try:
            blob = base64.b64decode(value.encode("ascii"), validate=True)
        except (UnicodeEncodeError, binascii.Error) as exc:
            raise E4BundleValidationError("media content_blob must be strict base64") from exc
    else:
        raise E4BundleValidationError("media content_blob_base64 is required")
    if not blob or len(blob) > _MAX_MEDIA_BYTES:
        raise E4BundleValidationError("media bytes must be non-empty and at most 256 MiB")
    return blob


async def _media_owner(session: AsyncSession, item: Mapping[str, Any], decisions: Mapping[SourceKey, Any]) -> str | None:
    scope = str(item.get("scope", item.get("scope_type", ""))).casefold()
    owner = item.get("owner")
    explicit = item.get("canonical_user_id")
    if scope == "global":
        if owner is not None or explicit is not None:
            raise E4ImportBlocked("global media cannot have an owner")
        return None
    if scope != "user":
        raise E4ImportBlocked("media scope must be user or global")
    owner_target = None
    if owner is not None:
        owner_key = _source_key(owner, field="media.owner")
        decision = decisions.get(owner_key)
        if decision is not None:
            if decision.target_uuid is None or decision.status in {"conflict", "orphan"}:
                raise E4ImportBlocked("media owner mapping is unavailable")
            owner_target = decision.target_uuid
        else:
            persisted = await session.scalar(
                select(MigrationMap).where(
                    MigrationMap.source_system == owner_key.source_system,
                    MigrationMap.entity_type == owner_key.entity_type,
                    MigrationMap.source_id == owner_key.source_id,
                )
            )
            if persisted is not None:
                if persisted.status != "mapped":
                    raise E4ImportBlocked("media owner mapping is unavailable")
                owner_target = persisted.target_uuid
            else:
                raise E4ImportBlocked("media owner mapping does not exist")
    explicit_target = _uuid(explicit, "canonical_user_id") if explicit is not None else None
    if owner_target and explicit_target and owner_target != explicit_target:
        raise E4ImportBlocked("media owner conflicts with canonical_user_id")
    result = explicit_target or owner_target
    if result is None or await session.get(User, result) is None:
        raise E4ImportBlocked("media requires an existing canonical user")
    return result


async def _assert_batch_complete(
    session: AsyncSession,
    *,
    batch_id: str,
    expected_keys: Sequence[SourceKey],
) -> None:
    """Refuse to finalize a partial batch with missing or unexpected rows.

    ``set_batch_status`` can only validate rows that have already been
    recorded.  A caller that skips an earlier chunk would otherwise be able to
    finalize a batch containing only its last chunk, so the importer checks the
    complete bundle identity before requesting the terminal transition.
    """

    expected = set(expected_keys)
    persisted = (
        await session.scalars(
            select(E4MigrationEntity).where(E4MigrationEntity.batch_id == batch_id)
        )
    ).all()
    actual = {
        SourceKey(row.source_system, row.entity_type, row.source_id): row
        for row in persisted
    }
    missing = expected.difference(actual)
    unexpected = set(actual).difference(expected)
    incomplete = sum(row.status not in {"imported", "reconciled"} for row in persisted if row.source_system)
    if missing or unexpected or incomplete:
        raise E4ImportBlocked(
            "E4 batch cannot be finalized until every bundle entity is imported "
            f"(missing={len(missing)}, unexpected={len(unexpected)}, incomplete={incomplete})"
        )


class E4BusinessImporter:
    """Write-capable E4 adapter whose caller owns commit/rollback."""

    def __init__(self, session: AsyncSession, *, actor_id: str | None = None) -> None:
        self.session = session
        self.actor_id = actor_id

    async def validate(self, bundle: E4BusinessBundle | Mapping[str, Any] | str | Path) -> tuple[E4BusinessBundle, IdentityDryRunReport]:
        parsed = load_business_bundle(bundle)
        actual_mappings, actual_targets = await _load_authoritative_facts(self.session, parsed)
        mappings, targets = _merge_facts(parsed, actual_mappings, actual_targets)
        if not parsed.entities:
            invalid_mappings = sum(
                str(item.get("status", "")).casefold() != "mapped"
                for item in mappings
            )
            report = _empty_identity_report(
                parsed,
                blocked=invalid_mappings > 0,
                mapping_count=len(mappings),
                conflict_count=invalid_mappings,
            )
            if report.blocked:
                raise E4ImportBlocked("E4 media owner identity validation is blocked", report=report)
            return parsed, report
        identity_input = _entity_identity_input(parsed, existing_mappings=mappings, existing_targets=targets)
        report = build_identity_dry_run(identity_input)
        if report.blocked:
            raise E4ImportBlocked("E4 identity validation is blocked", report=report)
        return parsed, report

    async def import_bundle(
        self,
        bundle: E4BusinessBundle | Mapping[str, Any] | str | Path,
        *,
        batch_size: int = 100,
        dry_run: bool = False,
        resume: bool = True,
        entity_offset: int = 0,
        entity_limit: int | None = None,
        finalize: bool = True,
        include_media: bool = True,
    ) -> E4ImportResult:
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or not 0 < batch_size <= 100_000:
            raise E4BundleValidationError("batch_size must be between 1 and 100000")
        if isinstance(entity_offset, bool) or not isinstance(entity_offset, int) or entity_offset < 0:
            raise E4BundleValidationError("entity_offset must be a non-negative integer")
        if entity_limit is not None and (
            isinstance(entity_limit, bool) or not isinstance(entity_limit, int) or entity_limit <= 0
        ):
            raise E4BundleValidationError("entity_limit must be a positive integer")
        if not isinstance(finalize, bool) or not isinstance(include_media, bool):
            raise E4BundleValidationError("finalize and include_media must be boolean")
        parsed, report = await self.validate(bundle)
        if dry_run:
            counts = report.counts
            return E4ImportResult(
                migration_batch_id=parsed.migration_batch_id,
                correlation_id=parsed.correlation_id,
                dry_run=True,
                total_entities=len(parsed.entities),
                imported_entities=0,
                skipped_entities=int(counts.get("already_mapped_count", 0)),
                quarantined_entities=0,
                media_imported=0,
                blocked_entities=0,
                report_sha256=report.report_sha256,
            )

        repository = E4MigrationRepository(self.session)
        batch = await repository.create_batch(
            migration_batch_id=parsed.migration_batch_id,
            snapshot_manifest_digest=parsed.snapshot_manifest_digest,
            schema_revision=parsed.schema_revision,
            correlation_id=parsed.correlation_id,
            actor_id=self.actor_id or parsed.actor_id,
        )
        if batch.status in {"blocked", "rolled_back"}:
            raise E4ImportBlocked(f"E4 migration batch is already {batch.status}")
        batch_terminal = batch.status in {"imported", "reconciled"}
        if batch.status == "planned":
            await repository.set_batch_status(batch_id=batch.id, to_status="validated", expected_status="planned")
            await repository.set_batch_status(batch_id=batch.id, to_status="importing", expected_status="validated")
        elif batch.status == "validated":
            await repository.set_batch_status(batch_id=batch.id, to_status="importing", expected_status="validated")

        decisions = {decision.key: decision for decision in report.decisions}
        entity_by_key = _identity_key_map(parsed)
        ordered_keys = _ordered_entity_keys(parsed)
        imported = 0
        skipped = 0
        quarantined = 0
        processed: list[str] = []
        end = len(ordered_keys) if entity_limit is None else min(len(ordered_keys), entity_offset + entity_limit)
        selected_keys = ordered_keys[entity_offset:end]
        for offset in range(0, len(selected_keys), batch_size):
            for key in selected_keys[offset : offset + batch_size]:
                entity = entity_by_key[key]
                decision = decisions[key]
                target_uuid = decision.target_uuid
                if target_uuid is None:
                    raise E4ImportBlocked("validated identity has no target UUID", report=report)
                canonical_user_id = await _resolve_owner(self.session, entity, decisions)
                model = _model_for_entity(key.entity_type)
                row = _prepare_row(model, entity, target_uuid, canonical_user_id, decisions)
                migration_entity = await repository.record_entity(
                    batch_id=batch.id,
                    source_system=key.source_system,
                    entity_type=key.entity_type,
                    source_id=key.source_id,
                    entity_content_digest=entity["entity_content_digest"],
                    scope_type=str(entity.get("scope", entity.get("scope_type"))).casefold(),
                    target_uuid=target_uuid,
                    canonical_user_id=canonical_user_id,
                    owner_source_key=entity.get("owner"),
                    artifact_digest=entity.get("artifact_digest"),
                    legacy_md5=entity.get("legacy_md5"),
                    correlation_id=parsed.correlation_id,
                )
                if migration_entity.status in {"imported", "reconciled"} and resume:
                    skipped += 1
                    processed.append(_source_key_token(key))
                    continue
                if _encrypted_key_requires_quarantine(model, entity, row):
                    if migration_entity.status == "candidate":
                        await repository.transition_entity(
                            entity_id=migration_entity.id,
                            to_status="excluded",
                            expected_status="candidate",
                            issue_code="key_version_unconfirmed",
                            error_detail="api_key_key_version is required before encrypted key migration",
                        )
                    quarantined += 1
                    processed.append(_source_key_token(key))
                    continue
                if migration_entity.status == "candidate":
                    await repository.transition_entity(
                        entity_id=migration_entity.id,
                        to_status="validated",
                        expected_status="candidate",
                    )
                elif migration_entity.status == "excluded":
                    raise E4ImportBlocked("excluded entity cannot be resumed in the same batch")
                if migration_entity.status == "validated":
                    await repository.map_entity(entity_id=migration_entity.id, target_uuid=target_uuid)
                elif migration_entity.status != "mapped":
                    raise E4StateError(f"entity status {migration_entity.status!r} cannot be imported")
                try:
                    _existing_row, created = await _write_business_row(self.session, model, row, target_uuid)
                except (E4ImportConflict, E4BundleValidationError):
                    await repository.transition_entity(
                        entity_id=migration_entity.id,
                        to_status="conflict",
                        issue_code="business_row_conflict",
                        error_detail="existing business row conflicts with immutable source facts",
                    )
                    await repository.set_batch_status(
                        batch_id=batch.id,
                        to_status="blocked",
                        expected_status="importing",
                        reason="business row constraint or immutable fact conflict blocked the E4 batch",
                    )
                    raise
                await repository.mark_imported(entity_id=migration_entity.id, target_uuid=target_uuid)
                repository.append_audit(
                    action="migration.business_imported",
                    target_type=model.__tablename__,
                    target_id=target_uuid,
                    migration_id=parsed.migration_batch_id,
                    correlation_id=parsed.correlation_id,
                    actor_id=self.actor_id or parsed.actor_id,
                    reason="E4 canonical business row imported",
                    result="created" if created else "replayed",
                    content_digest=entity["entity_content_digest"],
                    after={"source_key_sha256": _source_key_token(key), "canonical_id": target_uuid},
                )
                imported += 1
                processed.append(_source_key_token(key))

        media_imported = 0
        media_items = parsed.media if include_media else ()
        for item in sorted(media_items, key=lambda value: (str(value.get("source_system", "")), str(value.get("source_id", "")))):
            source_key = _source_key({**item, "entity_type": item.get("entity_type", "media")}, field="media")
            blob = _decode_media(item)
            owner_id = await _media_owner(self.session, item, decisions)
            await repository.record_media_asset(
                batch_id=batch.id,
                source_system=source_key.source_system,
                source_id=source_key.source_id,
                content_blob=blob,
                content_digest=item["content_digest"],
                artifact_digest=item.get("artifact_digest") or hashlib.sha256(blob).hexdigest(),
                legacy_md5=item.get("legacy_md5") or hashlib.md5(blob).hexdigest(),
                filename=_required_text(item.get("filename"), "media.filename", 255),
                mime_type=_required_text(item.get("mime_type"), "media.mime_type", 255),
                scope_type=str(item.get("scope", item.get("scope_type"))).casefold(),
                canonical_user_id=owner_id,
                status=str(item.get("status", "active")).casefold(),
            )
            # Count processed media entries; identical replays are successful
            # no-ops and remain visible through the replay audit event.
            media_imported += 1

        persisted_quarantined = quarantined
        if finalize and not batch_terminal:
            persisted_quarantined = len(
                (
                    await self.session.scalars(
                        select(E4MigrationEntity).where(
                            E4MigrationEntity.batch_id == batch.id,
                            E4MigrationEntity.status == "excluded",
                        )
                    )
                ).all()
            )
        if not batch_terminal and persisted_quarantined:
            await repository.set_batch_status(
                batch_id=batch.id,
                to_status="blocked",
                expected_status="importing",
                reason="one or more encrypted configuration rows are quarantined pending key-version confirmation",
            )
        elif finalize and not batch_terminal:
            await _assert_batch_complete(
                self.session,
                batch_id=batch.id,
                expected_keys=tuple(_identity_key_map(parsed)),
            )
            await repository.set_batch_status(batch_id=batch.id, to_status="imported", expected_status="importing")
        return E4ImportResult(
            migration_batch_id=parsed.migration_batch_id,
            correlation_id=parsed.correlation_id,
            dry_run=False,
            total_entities=len(parsed.entities),
            imported_entities=imported,
            skipped_entities=skipped,
            quarantined_entities=persisted_quarantined,
            media_imported=media_imported,
            blocked_entities=persisted_quarantined,
            report_sha256=report.report_sha256,
            processed_source_keys=tuple(processed),
        )


# Short operational name used by the CLI and external callers.
E4Importer = E4BusinessImporter


__all__ = [
    "BusinessBundle",
    "E4BusinessBundle",
    "E4BusinessImporter",
    "E4BundleValidationError",
    "E4ImportBlocked",
    "E4ImportConflict",
    "E4ImportError",
    "E4ImportResult",
    "E4Importer",
    "ImportResult",
    "build_business_dry_run",
    "bundle_file_sha256",
    "load_business_bundle",
]
