"""Transactional E4 migration facts and idempotent import primitives.

The repository is deliberately SQL-only.  It does not discover a database,
read settings, touch files/Chroma/Redis, or commit a transaction on behalf of
its caller.  A caller must use :class:`~app.db.uow.SqlUnitOfWork` (or an
equivalent transaction) and commit only after the batch gate has passed.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.e4_migration import E4MigrationBatch, E4MigrationEntity, MediaAsset
from app.models.identity_domain import MigrationMap
from app.models.job_domain import AuditEvent

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_MD5_RE = re.compile(r"^[0-9a-f]{32}$")
_ASCII_RE = re.compile(r"^[\x20-\x7e]+$")
_MAX_MEDIA_BYTES = 256 * 1024 * 1024

E4_ENTITY_TRANSITIONS: dict[str, frozenset[str]] = {
    "candidate": frozenset({"candidate", "validated", "conflict", "orphan", "excluded"}),
    "validated": frozenset({"validated", "mapped", "conflict", "orphan", "excluded"}),
    "mapped": frozenset({"mapped", "imported", "conflict"}),
    "imported": frozenset({"imported", "reconciled", "conflict"}),
    "reconciled": frozenset({"reconciled"}),
    "conflict": frozenset({"conflict"}),
    "orphan": frozenset({"orphan"}),
    "excluded": frozenset({"excluded"}),
}

E4_BATCH_TRANSITIONS: dict[str, frozenset[str]] = {
    "planned": frozenset({"planned", "validated", "importing", "blocked", "rolled_back"}),
    "validated": frozenset({"validated", "importing", "blocked", "rolled_back"}),
    "importing": frozenset({"importing", "imported", "blocked", "rolled_back"}),
    "imported": frozenset({"imported", "reconciled", "blocked", "rolled_back"}),
    "reconciled": frozenset({"reconciled", "rolled_back"}),
    "blocked": frozenset({"blocked", "rolled_back"}),
    "rolled_back": frozenset({"rolled_back"}),
}


class E4RepositoryError(RuntimeError):
    """Base error for a rejected E4 repository operation."""


class E4ValidationError(ValueError, E4RepositoryError):
    """An input violates the frozen E4 SQL contract."""


class E4ConflictError(E4RepositoryError):
    """An immutable E4 fact conflicts with an existing fact."""


class E4StateError(E4RepositoryError):
    """A state transition is not allowed by the E4 state machine."""


@dataclass(frozen=True, slots=True)
class MappingResult:
    mapping: MigrationMap
    created: bool


def _uuid(value: str, field: str) -> str:
    if not isinstance(value, str) or not _UUID_RE.fullmatch(value):
        raise E4ValidationError(f"{field} must be a lowercase canonical UUID")
    try:
        UUID(value)
    except ValueError as exc:
        raise E4ValidationError(f"{field} must be a lowercase canonical UUID") from exc
    return value


def _optional_uuid(value: str | None, field: str) -> str | None:
    return None if value is None else _uuid(value, field)


def _digest(value: str, field: str) -> str:
    if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
        raise E4ValidationError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _optional_digest(value: str | None, field: str) -> str | None:
    return None if value is None else _digest(value, field)


def _md5(value: str | None, field: str = "legacy_md5") -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _MD5_RE.fullmatch(value.casefold()):
        raise E4ValidationError(f"{field} must be a 32-character hexadecimal MD5 value")
    return value.casefold()


def _text(value: str, field: str, maximum: int, *, ascii_only: bool = False) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > maximum:
        raise E4ValidationError(f"{field} must be a non-empty string of at most {maximum} characters")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise E4ValidationError(f"{field} contains a control character")
    if ascii_only and not _ASCII_RE.fullmatch(value):
        raise E4ValidationError(f"{field} must contain printable ASCII characters only")
    return value


def _scope(value: str) -> str:
    value = _text(value, "scope_type", 32, ascii_only=True).casefold()
    if value not in {"user", "global"}:
        raise E4ValidationError("scope_type must be user or global")
    return value


def _timestamp(value: datetime | None, field: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise E4ValidationError(f"{field} must include a timezone")
    return value.astimezone(UTC)


def _json_object(value: Mapping[str, Any] | None, field: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise E4ValidationError(f"{field} must be a JSON object")
    try:
        rendered = json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"))
        normalized = json.loads(rendered)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise E4ValidationError(f"{field} must be deterministic JSON") from exc
    return normalized


def _safe_audit_json(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Keep audit payloads bounded and reject obvious secret-bearing keys."""

    if value is None:
        return None
    forbidden = {"password", "passwd", "token", "secret", "api_key", "api_key_encrypted", "database_url", "dsn"}

    def scrub(item: Any) -> Any:
        if isinstance(item, Mapping):
            result: dict[str, Any] = {}
            for key, child in item.items():
                key_text = str(key)
                if key_text.casefold() in forbidden:
                    raise E4ValidationError("audit payload cannot contain secret material")
                result[key_text] = scrub(child)
            return result
        if isinstance(item, (list, tuple)):
            return [scrub(child) for child in item]
        if isinstance(item, (str, int, float, bool)) or item is None:
            return item
        raise E4ValidationError("audit payload must be JSON serializable")

    normalized = scrub(value)
    encoded = json.dumps(normalized, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > 256 * 1024:
        raise E4ValidationError("audit payload exceeds 256 KiB")
    return normalized


class E4MigrationRepository:
    """Unit-of-work repository for E4 batch and migration facts."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _batch(self, value: str, *, for_update: bool = False) -> E4MigrationBatch:
        if not isinstance(value, str):
            raise E4ValidationError("batch_id must be a string")
        normalized = value
        statement = select(E4MigrationBatch).where((E4MigrationBatch.id == normalized) | (E4MigrationBatch.migration_batch_id == normalized))
        if for_update:
            statement = statement.with_for_update()
        batch = await self.session.scalar(statement)
        if batch is None:
            raise E4ValidationError("E4 migration batch does not exist")
        return batch

    async def create_batch(
        self,
        *,
        migration_batch_id: str,
        snapshot_manifest_digest: str,
        schema_revision: str,
        correlation_id: str,
        source_locator_digest: str | None = None,
        target_id: str | None = None,
        restore_target_id: str | None = None,
        actor_id: str | None = None,
        batch_row_id: str | None = None,
    ) -> E4MigrationBatch:
        migration_batch_id = _text(migration_batch_id, "migration_batch_id", 64, ascii_only=True)
        snapshot_manifest_digest = _digest(snapshot_manifest_digest, "snapshot_manifest_digest")
        schema_revision = _text(schema_revision, "schema_revision", 128, ascii_only=True)
        correlation_id = _uuid(correlation_id, "correlation_id")
        source_locator_digest = _optional_digest(source_locator_digest, "source_locator_digest")
        target_id = None if target_id is None else _text(target_id, "target_id", 64, ascii_only=True)
        restore_target_id = None if restore_target_id is None else _text(restore_target_id, "restore_target_id", 64, ascii_only=True)
        actor_id = None if actor_id is None else _text(actor_id, "actor_id", 64)
        batch_row_id = _optional_uuid(batch_row_id, "batch_row_id")

        existing = await self.session.scalar(
            select(E4MigrationBatch).where(E4MigrationBatch.migration_batch_id == migration_batch_id).with_for_update()
        )
        immutable = {
            "snapshot_manifest_digest": snapshot_manifest_digest,
            "schema_revision": schema_revision,
            "correlation_id": correlation_id,
            "source_locator_digest": source_locator_digest,
            "target_id": target_id,
            "restore_target_id": restore_target_id,
        }
        if existing is not None:
            if any(getattr(existing, key) != value for key, value in immutable.items()):
                raise E4ConflictError("migration_batch_id already exists with different immutable facts")
            return existing

        batch = E4MigrationBatch(
            id=batch_row_id or str(uuid4()),
            migration_batch_id=migration_batch_id,
            snapshot_manifest_digest=snapshot_manifest_digest,
            schema_revision=schema_revision,
            correlation_id=correlation_id,
            source_locator_digest=source_locator_digest,
            target_id=target_id,
            restore_target_id=restore_target_id,
            actor_id=actor_id,
            started_at=datetime.now(UTC),
        )
        self.session.add(batch)
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except IntegrityError as exc:
            raced = await self.session.scalar(select(E4MigrationBatch).where(E4MigrationBatch.migration_batch_id == migration_batch_id))
            if raced is None:
                raise E4ConflictError("E4 migration batch uniqueness constraint rejected the insert") from exc
            if any(getattr(raced, key) != value for key, value in immutable.items()):
                raise E4ConflictError("migration_batch_id raced with different immutable facts") from None
            return raced
        self.append_audit(
            action="migration.started",
            target_type="migration_batch",
            target_id=migration_batch_id,
            migration_id=migration_batch_id,
            correlation_id=correlation_id,
            actor_id=actor_id,
            reason="E4 migration batch created",
            result="planned",
            after={"status": "planned", "snapshot_manifest_digest": snapshot_manifest_digest},
        )
        return batch

    async def get_batch(self, batch_id: str, *, for_update: bool = False) -> E4MigrationBatch:
        return await self._batch(batch_id, for_update=for_update)

    async def record_entity(
        self,
        *,
        batch_id: str,
        source_system: str,
        entity_type: str,
        source_id: str,
        entity_content_digest: str,
        scope_type: str,
        target_uuid: str | None = None,
        canonical_user_id: str | None = None,
        owner_source_key: Mapping[str, Any] | None = None,
        artifact_digest: str | None = None,
        legacy_md5: str | None = None,
        status: str = "candidate",
        issue_code: str | None = None,
        error_detail: str | None = None,
        correlation_id: str | None = None,
        entity_id: str | None = None,
    ) -> E4MigrationEntity:
        batch = await self._batch(batch_id)
        source_system = _text(source_system, "source_system", 64, ascii_only=True)
        entity_type = _text(entity_type, "entity_type", 64, ascii_only=True)
        source_id = _text(source_id, "source_id", 255)
        entity_content_digest = _digest(entity_content_digest, "entity_content_digest")
        scope_type = _scope(scope_type)
        target_uuid = _optional_uuid(target_uuid, "target_uuid")
        canonical_user_id = _optional_uuid(canonical_user_id, "canonical_user_id")
        if scope_type == "global" and canonical_user_id is not None:
            raise E4ValidationError("global entity must not have canonical_user_id")
        if scope_type == "user" and canonical_user_id is None:
            raise E4ValidationError("user-scoped entity requires canonical_user_id")
        owner_source_key = _json_object(owner_source_key, "owner_source_key")
        artifact_digest = _optional_digest(artifact_digest, "artifact_digest")
        legacy_md5 = _md5(legacy_md5)
        status = _text(status, "status", 32, ascii_only=True).casefold()
        if status not in E4_ENTITY_TRANSITIONS:
            raise E4ValidationError("unsupported E4 entity status")
        issue_code = None if issue_code is None else _text(issue_code, "issue_code", 64, ascii_only=True)
        error_detail = None if error_detail is None else _text(error_detail, "error_detail", 4096)
        if status in {"conflict", "orphan", "excluded"} and (not issue_code or not error_detail):
            raise E4ValidationError(f"{status} entities require issue_code and error_detail")
        correlation_id = _uuid(correlation_id or batch.correlation_id, "correlation_id")
        entity_id = _optional_uuid(entity_id, "entity_id")

        existing = await self.session.scalar(
            select(E4MigrationEntity)
            .where(
                E4MigrationEntity.batch_id == batch.id,
                E4MigrationEntity.source_system == source_system,
                E4MigrationEntity.entity_type == entity_type,
                E4MigrationEntity.source_id == source_id,
            )
            .with_for_update()
        )
        immutable = {
            "entity_content_digest": entity_content_digest,
            "artifact_digest": artifact_digest,
            "legacy_md5": legacy_md5,
            "target_uuid": target_uuid,
            "scope_type": scope_type,
            "canonical_user_id": canonical_user_id,
            "owner_source_key": owner_source_key,
        }
        if existing is not None:
            if any(getattr(existing, key) != value for key, value in immutable.items()):
                await self._mark_conflict(
                    existing,
                    "entity_fact_conflict",
                    "source key was replayed with different immutable facts",
                    batch=batch,
                    correlation_id=correlation_id,
                )
                raise E4ConflictError("source entity conflicts with an existing immutable fact")
            if status != existing.status and status != "candidate":
                await self.transition_entity(
                    entity_id=existing.id,
                    to_status=status,
                    issue_code=issue_code,
                    error_detail=error_detail,
                )
            return existing

        entity = E4MigrationEntity(
            id=entity_id or str(uuid4()),
            batch_id=batch.id,
            source_system=source_system,
            entity_type=entity_type,
            source_id=source_id,
            target_uuid=target_uuid,
            canonical_user_id=canonical_user_id,
            scope_type=scope_type,
            owner_source_key=owner_source_key,
            entity_content_digest=entity_content_digest,
            artifact_digest=artifact_digest,
            legacy_md5=legacy_md5,
            status=status,
            issue_code=issue_code,
            error_detail=error_detail,
            correlation_id=correlation_id,
        )
        self.session.add(entity)
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except IntegrityError as exc:
            raced = await self.session.scalar(
                select(E4MigrationEntity).where(
                    E4MigrationEntity.batch_id == batch.id,
                    E4MigrationEntity.source_system == source_system,
                    E4MigrationEntity.entity_type == entity_type,
                    E4MigrationEntity.source_id == source_id,
                )
            )
            if raced is None:
                raise E4ConflictError("E4 entity uniqueness constraint rejected the insert") from exc
            if any(getattr(raced, key) != value for key, value in immutable.items()):
                raise E4ConflictError("E4 entity raced with different immutable facts") from None
            return raced
        return entity

    async def get_entity(self, entity_id: str, *, for_update: bool = False) -> E4MigrationEntity:
        entity_id = _uuid(entity_id, "entity_id")
        statement = select(E4MigrationEntity).where(E4MigrationEntity.id == entity_id)
        if for_update:
            statement = statement.with_for_update()
        entity = await self.session.scalar(statement)
        if entity is None:
            raise E4ValidationError("E4 migration entity does not exist")
        return entity

    async def transition_entity(
        self,
        *,
        entity_id: str,
        to_status: str,
        expected_status: str | None = None,
        issue_code: str | None = None,
        error_detail: str | None = None,
        target_uuid: str | None = None,
    ) -> E4MigrationEntity:
        entity = await self.get_entity(entity_id, for_update=True)
        to_status = _text(to_status, "to_status", 32, ascii_only=True).casefold()
        if to_status not in E4_ENTITY_TRANSITIONS:
            raise E4ValidationError("unsupported E4 entity status")
        if expected_status is not None and entity.status != expected_status:
            raise E4StateError(f"entity is {entity.status!r}, expected {expected_status!r}")
        allowed = E4_ENTITY_TRANSITIONS.get(entity.status, frozenset())
        if to_status not in allowed:
            raise E4StateError(f"entity transition {entity.status!r} -> {to_status!r} is not allowed")
        batch = await self._batch(entity.batch_id)
        previous_status = entity.status
        if target_uuid is not None:
            target_uuid = _uuid(target_uuid, "target_uuid")
            if entity.target_uuid is not None and entity.target_uuid != target_uuid:
                raise E4ConflictError("entity target_uuid is immutable")
            entity.target_uuid = target_uuid
        issue_code = None if issue_code is None else _text(issue_code, "issue_code", 64, ascii_only=True)
        error_detail = None if error_detail is None else _text(error_detail, "error_detail", 4096)
        if to_status in {"conflict", "orphan", "excluded"} and (not issue_code or not error_detail):
            raise E4ValidationError(f"{to_status} entities require issue_code and error_detail")
        entity.status = to_status
        entity.issue_code = issue_code
        entity.error_detail = error_detail
        now = datetime.now(UTC)
        if to_status == "imported":
            entity.imported_at = now
        elif to_status == "reconciled":
            entity.reconciled_at = now
        await self.session.flush()
        self.append_audit(
            action=(
                "migration.blocked"
                if to_status in {"conflict", "orphan", "excluded"}
                else "migration.imported"
                if to_status == "imported"
                else "migration.reconciled"
                if to_status == "reconciled"
                else "migration.entity_state_changed"
            ),
            target_type="migration_entity",
            target_id=entity.id,
            migration_id=batch.migration_batch_id,
            correlation_id=entity.correlation_id,
            actor_id=batch.actor_id,
            reason="E4 entity state transition",
            result=to_status,
            error_code=issue_code,
            before={"status": previous_status},
            after={"status": to_status, "target_uuid": entity.target_uuid},
        )
        return entity

    async def map_entity(
        self,
        *,
        entity_id: str,
        target_uuid: str | None = None,
        mapping_id: str | None = None,
    ) -> MappingResult:
        entity = await self.get_entity(entity_id, for_update=True)
        if entity.status not in {"validated", "mapped"}:
            raise E4StateError(f"entity status {entity.status!r} cannot be mapped")
        target_uuid = _uuid(target_uuid or entity.target_uuid or "", "target_uuid")
        if entity.target_uuid is not None and entity.target_uuid != target_uuid:
            raise E4ConflictError("entity target_uuid conflicts with the requested mapping")
        if entity.scope_type == "user" and entity.canonical_user_id is None:
            raise E4ValidationError("user-scoped entity requires canonical_user_id before mapping")
        batch = await self._batch(entity.batch_id)
        existing = await self.session.scalar(
            select(MigrationMap)
            .where(
                MigrationMap.source_system == entity.source_system,
                MigrationMap.entity_type == entity.entity_type,
                MigrationMap.source_id == entity.source_id,
            )
            .with_for_update()
        )
        if existing is not None:
            if existing.target_uuid != target_uuid or existing.source_digest != entity.entity_content_digest:
                await self._mark_conflict(
                    entity,
                    "mapping_fact_conflict",
                    "existing migration map has a different target or digest",
                    batch=batch,
                )
                raise E4ConflictError("migration map conflicts with an existing target or digest")
            if existing.status != "mapped":
                await self._mark_conflict(
                    entity,
                    "mapping_not_mapped",
                    "existing migration map is not in mapped state",
                    batch=batch,
                )
                raise E4ConflictError("existing migration map is not in mapped state")
            entity.target_uuid = target_uuid
            if entity.status != "mapped":
                entity.status = "mapped"
            await self.session.flush()
            self.append_audit(
                action="migration.mapped",
                target_type="migration_entity",
                target_id=entity.id,
                migration_id=batch.migration_batch_id,
                correlation_id=entity.correlation_id,
                actor_id=batch.actor_id,
                reason="immutable source mapping replayed",
                result="mapped",
                after={"target_uuid": target_uuid, "source_digest": entity.entity_content_digest, "created": False},
            )
            return MappingResult(existing, False)

        target_owner = await self.session.scalar(select(MigrationMap).where(MigrationMap.target_uuid == target_uuid).limit(1).with_for_update())
        if target_owner is not None and (
            target_owner.source_system != entity.source_system
            or target_owner.entity_type != entity.entity_type
            or target_owner.source_id != entity.source_id
        ):
            await self._mark_conflict(
                entity,
                "target_uuid_collision",
                "target UUID is already mapped to another source key",
                batch=batch,
            )
            raise E4ConflictError("target UUID is already mapped to another source key")

        mapping = MigrationMap(
            id=_uuid(mapping_id, "mapping_id") if mapping_id is not None else str(uuid4()),
            migration_batch_id=batch.migration_batch_id,
            source_system=entity.source_system,
            entity_type=entity.entity_type,
            source_id=entity.source_id,
            target_uuid=target_uuid,
            source_digest=entity.entity_content_digest,
            status="mapped",
        )
        self.session.add(mapping)
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except IntegrityError as exc:
            raced = await self.session.scalar(
                select(MigrationMap).where(
                    MigrationMap.source_system == entity.source_system,
                    MigrationMap.entity_type == entity.entity_type,
                    MigrationMap.source_id == entity.source_id,
                )
            )
            if raced is None:
                raise E4ConflictError("migration map uniqueness constraint rejected the insert") from exc
            if raced.target_uuid != target_uuid or raced.source_digest != entity.entity_content_digest or raced.status != "mapped":
                await self._mark_conflict(
                    entity,
                    "mapping_race_conflict",
                    "mapping raced with different immutable facts",
                    batch=batch,
                )
                raise E4ConflictError("migration map raced with different immutable facts") from None
            mapping = raced
            created = False
        else:
            created = True
        entity.target_uuid = target_uuid
        entity.status = "mapped"
        entity.issue_code = None
        entity.error_detail = None
        await self.session.flush()
        self.append_audit(
            action="migration.mapped",
            target_type="migration_entity",
            target_id=entity.id,
            migration_id=batch.migration_batch_id,
            correlation_id=entity.correlation_id,
            reason="immutable source mapping accepted",
            result="mapped",
            after={"target_uuid": target_uuid, "source_digest": entity.entity_content_digest, "created": created},
        )
        return MappingResult(mapping, created)

    async def _mark_conflict(
        self,
        entity: E4MigrationEntity,
        issue_code: str,
        detail: str,
        *,
        batch: E4MigrationBatch | None = None,
        correlation_id: str | None = None,
    ) -> None:
        previous_status = entity.status
        entity.status = "conflict"
        entity.issue_code = _text(issue_code, "issue_code", 64, ascii_only=True)
        entity.error_detail = _text(detail, "error_detail", 4096)
        await self.session.flush()
        batch = batch or await self._batch(entity.batch_id)
        self.append_audit(
            action="migration.blocked",
            target_type="migration_entity",
            target_id=entity.id,
            migration_id=batch.migration_batch_id,
            correlation_id=correlation_id or entity.correlation_id,
            actor_id=batch.actor_id,
            reason=detail,
            result="conflict",
            error_code=issue_code,
            before={"status": previous_status},
            after={"status": "conflict", "issue_code": issue_code},
        )

    async def mark_imported(self, *, entity_id: str, target_uuid: str | None = None) -> E4MigrationEntity:
        entity = await self.get_entity(entity_id, for_update=True)
        if entity.status != "mapped":
            raise E4StateError("only mapped entities can be marked imported")
        if target_uuid is not None and entity.target_uuid != _uuid(target_uuid, "target_uuid"):
            raise E4ConflictError("import target UUID differs from mapped UUID")
        return await self.transition_entity(entity_id=entity.id, to_status="imported", expected_status="mapped")

    async def mark_reconciled(self, *, entity_id: str) -> E4MigrationEntity:
        entity = await self.get_entity(entity_id, for_update=True)
        if entity.status != "imported":
            raise E4StateError("only imported entities can be reconciled")
        return await self.transition_entity(entity_id=entity.id, to_status="reconciled", expected_status="imported")

    async def set_batch_status(
        self,
        *,
        batch_id: str,
        to_status: str,
        expected_status: str | None = None,
        reason: str = "E4 batch state transition",
    ) -> E4MigrationBatch:
        batch = await self._batch(batch_id, for_update=True)
        to_status = _text(to_status, "to_status", 32, ascii_only=True).casefold()
        if to_status not in E4_BATCH_TRANSITIONS:
            raise E4ValidationError("unsupported E4 batch status")
        if expected_status is not None and batch.status != expected_status:
            raise E4StateError(f"batch is {batch.status!r}, expected {expected_status!r}")
        if to_status not in E4_BATCH_TRANSITIONS.get(batch.status, frozenset()):
            raise E4StateError(f"batch transition {batch.status!r} -> {to_status!r} is not allowed")
        reason = _text(reason, "reason", 4096)
        if to_status in {"imported", "reconciled"}:
            entities = tuple((await self.session.execute(select(E4MigrationEntity).where(E4MigrationEntity.batch_id == batch.id))).scalars())
            required = "imported" if to_status == "imported" else "reconciled"
            if any(entity.status not in {required, "reconciled"} for entity in entities):
                raise E4StateError(f"all entities must be at least {required} before batch can be {to_status}")
        batch.status = to_status
        if to_status == "importing" and batch.started_at is None:
            batch.started_at = datetime.now(UTC)
        if to_status in {"imported", "reconciled", "blocked", "rolled_back"}:
            batch.finished_at = datetime.now(UTC)
        await self.session.flush()
        self.append_audit(
            action=(
                "migration.reconciled"
                if to_status == "reconciled"
                else "migration.blocked"
                if to_status == "blocked"
                else "migration.imported"
                if to_status == "imported"
                else "migration.state_changed"
            ),
            target_type="migration_batch",
            target_id=batch.migration_batch_id,
            migration_id=batch.migration_batch_id,
            correlation_id=batch.correlation_id,
            actor_id=batch.actor_id,
            reason=reason,
            result=to_status,
            after={"status": to_status},
        )
        return batch

    async def record_media_asset(
        self,
        *,
        batch_id: str,
        source_system: str,
        source_id: str,
        content_blob: bytes,
        content_digest: str,
        artifact_digest: str | None = None,
        legacy_md5: str | None = None,
        filename: str,
        mime_type: str,
        scope_type: str,
        canonical_user_id: str | None = None,
        status: str = "active",
        asset_id: str | None = None,
    ) -> MediaAsset:
        batch = await self._batch(batch_id)
        source_system = _text(source_system, "source_system", 64, ascii_only=True)
        source_id = _text(source_id, "source_id", 255)
        if not isinstance(content_blob, bytes) or not content_blob or len(content_blob) > _MAX_MEDIA_BYTES:
            raise E4ValidationError("content_blob must be non-empty and at most 256 MiB")
        content_digest = _digest(content_digest, "content_digest")
        expected_artifact = hashlib.sha256(content_blob).hexdigest()
        artifact_digest = _digest(artifact_digest or expected_artifact, "artifact_digest")
        if artifact_digest != expected_artifact:
            raise E4ValidationError("artifact_digest does not match content_blob bytes")
        legacy_md5 = _md5(legacy_md5, "legacy_md5")
        expected_md5 = hashlib.md5(content_blob).hexdigest()
        if legacy_md5 is None:
            legacy_md5 = expected_md5
        if legacy_md5 != expected_md5:
            raise E4ValidationError("legacy_md5 does not match content_blob bytes")
        filename = _text(filename, "filename", 255)
        mime_type = _text(mime_type, "mime_type", 255)
        scope_type = _scope(scope_type)
        canonical_user_id = _optional_uuid(canonical_user_id, "canonical_user_id")
        if scope_type == "global":
            if canonical_user_id is not None:
                raise E4ValidationError("global media must not have canonical_user_id")
            scope_id = "global"
        else:
            if canonical_user_id is None:
                raise E4ValidationError("user media requires canonical_user_id")
            scope_id = canonical_user_id
        status = _text(status, "status", 32, ascii_only=True).casefold()
        if status not in {"active", "quarantined"}:
            raise E4ValidationError("media status must be active or quarantined")

        existing = await self.session.scalar(
            select(MediaAsset).where(MediaAsset.source_system == source_system, MediaAsset.source_id == source_id).with_for_update()
        )
        immutable = {
            "content_digest": content_digest,
            "artifact_digest": artifact_digest,
            "legacy_md5": legacy_md5,
            "canonical_user_id": canonical_user_id,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "byte_size": len(content_blob),
            "filename": filename,
            "mime_type": mime_type,
            "status": status,
        }
        if existing is not None:
            if any(getattr(existing, key) != value for key, value in immutable.items()) or existing.content_blob != content_blob:
                self.append_audit(
                    action="migration.blocked",
                    target_type="media_asset",
                    target_id=existing.id,
                    migration_id=batch.migration_batch_id,
                    correlation_id=batch.correlation_id,
                    actor_id=batch.actor_id,
                    reason="media source key was replayed with different immutable facts",
                    result="conflict",
                    error_code="media_fact_conflict",
                    after={
                        "source_key_sha256": hashlib.sha256(f"{source_system}\x1f{source_id}".encode("utf-8")).hexdigest(),
                    },
                )
                raise E4ConflictError("media source key conflicts with an existing immutable asset")
            self.append_audit(
                action="migration.media_replayed",
                target_type="media_asset",
                target_id=existing.id,
                migration_id=batch.migration_batch_id,
                correlation_id=batch.correlation_id,
                actor_id=batch.actor_id,
                reason="identical media source facts were replayed",
                result="replayed",
                after={"content_digest": content_digest, "artifact_digest": artifact_digest, "byte_size": len(content_blob)},
            )
            return existing
        duplicate = await self.session.scalar(
            select(MediaAsset)
            .where(
                MediaAsset.content_digest == content_digest,
                MediaAsset.scope_type == scope_type,
                MediaAsset.scope_id == scope_id,
            )
            .with_for_update()
        )
        if duplicate is not None:
            if duplicate.content_blob != content_blob or duplicate.artifact_digest != artifact_digest:
                self.append_audit(
                    action="migration.blocked",
                    target_type="media_asset",
                    target_id=duplicate.id,
                    migration_id=batch.migration_batch_id,
                    correlation_id=batch.correlation_id,
                    actor_id=batch.actor_id,
                    reason="media content digest conflicts with different bytes",
                    result="conflict",
                    error_code="media_content_conflict",
                    after={"content_digest": content_digest},
                )
                raise E4ConflictError("media content digest conflicts with different bytes")
            self.append_audit(
                action="migration.media_replayed",
                target_type="media_asset",
                target_id=duplicate.id,
                migration_id=batch.migration_batch_id,
                correlation_id=batch.correlation_id,
                actor_id=batch.actor_id,
                reason="identical media content was replayed under another source key",
                result="replayed",
                after={"content_digest": content_digest, "artifact_digest": artifact_digest, "byte_size": len(content_blob)},
            )
            return duplicate
        asset = MediaAsset(
            id=_uuid(asset_id, "asset_id") if asset_id is not None else str(uuid4()),
            canonical_user_id=canonical_user_id,
            scope_type=scope_type,
            scope_id=scope_id,
            source_system=source_system,
            source_id=source_id,
            migration_batch_id=batch.migration_batch_id,
            content_digest=content_digest,
            artifact_digest=artifact_digest,
            legacy_md5=legacy_md5,
            filename=filename,
            mime_type=mime_type,
            byte_size=len(content_blob),
            content_blob=content_blob,
            status=status,
        )
        self.session.add(asset)
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except IntegrityError as exc:
            self.append_audit(
                action="migration.blocked",
                target_type="media_asset",
                target_id=None,
                migration_id=batch.migration_batch_id,
                correlation_id=batch.correlation_id,
                actor_id=batch.actor_id,
                reason="media asset uniqueness constraint rejected the insert",
                result="conflict",
                error_code="media_uniqueness_conflict",
                after={
                    "source_key_sha256": hashlib.sha256(f"{source_system}\x1f{source_id}".encode("utf-8")).hexdigest(),
                    "content_digest": content_digest,
                },
            )
            raise E4ConflictError("media asset uniqueness constraint rejected the insert") from exc
        self.append_audit(
            action="migration.media_imported",
            target_type="media_asset",
            target_id=asset.id,
            migration_id=batch.migration_batch_id,
            correlation_id=batch.correlation_id,
            actor_id=batch.actor_id,
            reason="media bytes stored as SQL business authority",
            result=status,
            after={"content_digest": content_digest, "artifact_digest": artifact_digest, "byte_size": len(content_blob)},
        )
        return asset

    def append_audit(
        self,
        *,
        action: str,
        target_type: str,
        target_id: str | None,
        correlation_id: str,
        reason: str,
        result: str,
        migration_id: str | None = None,
        actor_id: str | None = None,
        error_code: str | None = None,
        content_digest: str | None = None,
        before: Mapping[str, Any] | None = None,
        after: Mapping[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            id=str(uuid4()),
            actor_type="system",
            actor_id=None if actor_id is None else _text(actor_id, "actor_id", 64),
            actor_role="e4_migration",
            action=_text(action, "action", 128, ascii_only=True),
            target_type=_text(target_type, "target_type", 64, ascii_only=True),
            target_id=None if target_id is None else _text(target_id, "target_id", 64),
            reason=_text(reason, "reason", 4096),
            result=_text(result, "result", 32, ascii_only=True),
            error_code=None if error_code is None else _text(error_code, "error_code", 64, ascii_only=True),
            correlation_id=_uuid(correlation_id, "correlation_id"),
            migration_id=None if migration_id is None else _text(migration_id, "migration_id", 64, ascii_only=True),
            content_digest=None if content_digest is None else _digest(content_digest, "content_digest"),
            before_json=_safe_audit_json(before),
            after_json=_safe_audit_json(after),
        )
        self.session.add(event)
        return event


# Compatibility alias used by operational scripts and review notes.
E4Repository = E4MigrationRepository

__all__ = [
    "E4_BATCH_TRANSITIONS",
    "E4_ENTITY_TRANSITIONS",
    "E4ConflictError",
    "E4MigrationRepository",
    "E4Repository",
    "E4RepositoryError",
    "E4StateError",
    "E4ValidationError",
    "MappingResult",
]
