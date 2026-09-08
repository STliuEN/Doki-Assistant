"""E4 runtime identity, audit and durable projection outbox."""

from __future__ import annotations

import hashlib
import json
from contextvars import ContextVar
from copy import deepcopy
from datetime import UTC, date, datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, event, inspect, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import TextClause

from app.jobs.config import JobRuntimeConfig
from app.jobs.repository import JobBackpressureError, JobRepository, payload_digest
from app.models.chat_history import ChatMessage, ChatSession
from app.models.embedding_config import UserEmbeddingConfig
from app.models.identity_domain import User
from app.models.job_domain import AuditEvent, Job
from app.models.knowledge_document import KnowledgeSourceDocument
from app.models.memory_item import MemoryItem
from app.models.model_config import UserModelConfig
from app.models.note import Note
from app.models.note_template import NoteTemplate
from app.models.skill_domain import SkillRunBinding

OWNER_MODELS = (ChatSession, Note, NoteTemplate, MemoryItem, KnowledgeSourceDocument, UserModelConfig, UserEmbeddingConfig, SkillRunBinding)
BUSINESS_TABLES = frozenset(model.__tablename__ for model in (*OWNER_MODELS, ChatMessage))
SHADOW_FIELDS = frozenset(
    {"canonical_id", "canonical_user_id", "canonical_session_id", "content_digest", "artifact_digest", "created_at", "updated_at"}
)
BUSINESS_ACTOR = ContextVar("e4_business_actor", default=None)
BUSINESS_CORRELATION = ContextVar("e4_business_correlation", default=None)


class BusinessWriteError(ValueError):
    pass


class BusinessSession(Session):
    """Only the guarded E4 app and worker use this session class."""


def uses_business_authority(session) -> bool:
    return isinstance(getattr(session, "sync_session", session), BusinessSession)


def canonical_uuid(value) -> str:
    try:
        normalized = str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as error:
        raise BusinessWriteError("Business identity must be a canonical UUID") from error
    if normalized != value:
        raise BusinessWriteError("Business identity must be a canonical UUID")
    return normalized


def _encoded(value):
    if isinstance(value, bytes):
        return {"sha256": hashlib.sha256(value).hexdigest(), "bytes": len(value)}
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    raise TypeError("Unsupported business digest value")


def business_digest(row) -> str:
    values = {
        attribute.key: getattr(row, attribute.key)
        for attribute in inspect(type(row)).column_attrs
        if attribute.key not in SHADOW_FIELDS and not (isinstance(row, ChatMessage) and attribute.key == "id")
    }
    return hashlib.sha256(json.dumps(values, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=_encoded).encode()).hexdigest()


def _immutable(row, names):
    state = inspect(row)
    if state.persistent and any(state.attrs[name].history.has_changes() for name in names if name in state.attrs):
        raise BusinessWriteError("Business ownership and identity are immutable")


def _owner(session, row) -> str:
    _immutable(row, ("id", "run_id", "user_id", "canonical_user_id", "canonical_id"))
    owner = canonical_uuid(row.canonical_user_id or row.user_id)
    if row in session.new and row.user_id != owner:
        raise BusinessWriteError("New business writes require canonical ownership")
    if session.get(User, owner) is None and not any(isinstance(item, User) and item.id == owner for item in session.new):
        raise BusinessWriteError("Business owner does not exist")
    actor = session.info.get("e4_actor_id", BUSINESS_ACTOR.get())
    if actor is not None and actor != owner:
        raise BusinessWriteError("Business owner does not match authenticated actor")
    row.canonical_user_id = owner
    return owner


def _parent(session, row):
    _immutable(row, ("id", "session_id", "canonical_id", "canonical_session_id"))
    parent = next((item for item in session.new if isinstance(item, ChatSession) and item.id == row.session_id), None)
    parent = parent or session.get(ChatSession, row.session_id)
    if parent is None or not parent.canonical_id or not parent.canonical_user_id:
        raise BusinessWriteError("Canonical parent session is missing")
    if row.canonical_session_id not in (None, parent.canonical_id):
        raise BusinessWriteError("Canonical parent session mismatch")
    row.canonical_session_id = parent.canonical_id
    actor = session.info.get("e4_actor_id", BUSINESS_ACTOR.get())
    if actor is not None and actor != parent.canonical_user_id:
        raise BusinessWriteError("Business parent does not match authenticated actor")
    return parent.canonical_user_id


def _projection(row, operation, changed):
    if isinstance(row, Note) and (operation != "updated" or {"title", "content"} & changed):
        return "e4.note.project"
    if isinstance(row, KnowledgeSourceDocument) and (operation != "updated" or {"content_blob", "filename", "original_filename"} & changed):
        return "e4.knowledge.project"
    if isinstance(row, UserEmbeddingConfig) and operation != "deleted":
        return "e4.embedding.rebuild"
    return None


def enqueue_business_job(session, row, owner, job_type, correlation, event_id):
    payload = {"schema_version": 1, "entity_type": row.__tablename__, "entity_id": str(row.id), "owner_id": owner, "event_id": event_id}
    if isinstance(row, KnowledgeSourceDocument):
        payload["md5"] = row.md5
    job = Job(
        id=str(uuid4()),
        job_type=job_type,
        owner_scope_type="user",
        owner_scope_id=owner,
        correlation_id=correlation,
        idempotency_key=event_id + ":" + job_type,
        payload_digest=payload_digest(payload),
        payload_json=payload,
        payload_schema_version=1,
    )
    config = JobRuntimeConfig()
    from sqlalchemy import func
    active = ("queued", "leased", "running", "retry_wait", "cancel_requested")
    pending = [item for item in session.new if isinstance(item, Job)]
    global_count = session.scalar(select(func.count()).select_from(Job).where(Job.status.in_(active))) + len(pending)
    owner_count = session.scalar(
        select(func.count()).select_from(Job).where(Job.status.in_(active), Job.owner_scope_id == owner, Job.job_type == job_type)
    )
    owner_count += sum(item.owner_scope_id == owner and item.job_type == job_type for item in pending)
    if global_count >= config.global_backpressure or owner_count >= config.owner_type_backpressure:
        raise JobBackpressureError("Business projection queue capacity exceeded")
    session.add(job)
    audit = JobRepository(session).append_audit(
        action="job.enqueued",
        target_type="job",
        target_id=job.id,
        job_id=job.id,
        correlation_id=correlation,
        scope_type="user",
        scope_id=owner,
        reason="Business projection accepted in the same transaction",
        result="accepted",
        after={"status": "queued", "payload_digest": job.payload_digest},
    )
    audit.job = job
    session.info.setdefault("e4_enqueued_jobs", []).append(job.id)
    return job


def _normalise_datetime(value, column_type, dialect):
    if dialect.name != "mysql":
        return value
    if value.tzinfo is not None:
        value = value.astimezone(UTC).replace(tzinfo=None)
    precision = getattr(column_type.dialect_impl(dialect), "fsp", None) or 0
    microseconds = value.microsecond // (10 ** (6 - precision)) * (10 ** (6 - precision))
    return value.replace(microsecond=microseconds)


def _apply_defaults(row):
    for attribute in inspect(type(row)).column_attrs:
        column = attribute.columns[0]
        if getattr(row, attribute.key) is not None or column.default is None:
            continue
        if column.default.is_scalar:
            setattr(row, attribute.key, deepcopy(column.default.arg))
        elif column.default.is_callable and attribute.key not in SHADOW_FIELDS:
            setattr(row, attribute.key, column.default.arg(None))


@event.listens_for(BusinessSession, "before_flush")
def record_business_writes(session, _context, _instances):
    rows = [
        row
        for row in (*session.new, *session.dirty, *session.deleted)
        if row.__tablename__ in BUSINESS_TABLES or row.__tablename__.startswith("skill_") or row.__tablename__ == "skills"
    ]
    rows.sort(key=lambda row: 0 if isinstance(row, ChatSession) else 1)
    for row in rows:
        operation = "created" if row in session.new else "deleted" if row in session.deleted else "updated"
        if operation == "updated" and not session.is_modified(row, include_collections=False):
            continue
        if operation == "created":
            _apply_defaults(row)
        state = inspect(row)
        changed = {attribute.key for attribute in state.mapper.column_attrs if state.attrs[attribute.key].history.has_changes()}
        if session.get_bind().dialect.name == "mysql":
            for attribute in state.mapper.column_attrs:
                column_type = attribute.columns[0].type
                value = getattr(row, attribute.key)
                if isinstance(column_type, DateTime) and isinstance(value, datetime) and attribute.key in changed:
                    setattr(row, attribute.key, _normalise_datetime(value, column_type, session.get_bind().dialect))
        owner = _owner(session, row) if isinstance(row, OWNER_MODELS) else None
        if hasattr(row, "canonical_id"):
            _immutable(row, ("id", "canonical_id"))
            if not row.canonical_id:
                try:
                    row.canonical_id = canonical_uuid(row.id)
                except BusinessWriteError:
                    row.canonical_id = str(uuid4())
            canonical_uuid(row.canonical_id)
        if isinstance(row, ChatMessage) and not row.session_id:
            raise BusinessWriteError("Chat messages require a parent session")
        if isinstance(row, (ChatMessage, SkillRunBinding)) and row.session_id:
            parent_owner = _parent(session, row)
            if owner is not None and owner != parent_owner:
                raise BusinessWriteError("Business parent belongs to another user")
            owner = parent_owner
        if isinstance(row, UserModelConfig) and operation != "deleted":
            if row.api_key_encrypted:
                from app.utils.crypto_utils import _resolve_secret, decrypt_text
                secret = _resolve_secret()
                decrypt_text(row.api_key_encrypted, secret=secret, strict=True)
                row.api_key_key_version = "e4-sha256-" + hashlib.sha256(secret.encode()).hexdigest()[:48]
            else:
                row.api_key_key_version = None
        if isinstance(row, MemoryItem) and row.source_type == "note" and row.source_id and operation != "deleted":
            source = next((item for item in session.new if isinstance(item, Note) and item.id == row.source_id), None)
            source = source or session.get(Note, row.source_id)
            if source is None or (source.canonical_user_id or source.user_id) != owner:
                raise BusinessWriteError("Memory source note must belong to its owner")
        digest = business_digest(row)
        if hasattr(row, "content_digest"):
            row.content_digest = digest
        if isinstance(row, KnowledgeSourceDocument):
            row.artifact_digest = hashlib.sha256(row.content_blob).hexdigest()
        event_id = str(uuid4())
        correlation = session.info.setdefault("e4_correlation_id", BUSINESS_CORRELATION.get() or str(uuid4()))
        actor = session.info.get("e4_actor_id", BUSINESS_ACTOR.get())
        target_id = str(getattr(row, "canonical_id", None) or getattr(row, "id", None) or getattr(row, "run_id", ""))
        session.add(
            AuditEvent(
                id=event_id,
                actor_type="user" if actor else "system",
                actor_id=actor,
                actor_role="e4_business",
                action="business." + operation,
                target_type=row.__tablename__,
                target_id=target_id,
                scope_type="user" if owner else "global",
                scope_id=owner,
                correlation_id=correlation,
                content_digest=digest,
                reason="E4 SQL business mutation",
                result="accepted",
                after_json={"operation": operation, "fields": sorted(changed - SHADOW_FIELDS)},
            )
        )
        if owner:
            job_type = _projection(row, operation, changed)
            if job_type:
                enqueue_business_job(session, row, owner, job_type, correlation, event_id)
            if isinstance(row, Note) and operation == "created" and row.tags is None and row.category is None:
                enqueue_business_job(session, row, owner, "e4.note.enrich", correlation, event_id)


@event.listens_for(BusinessSession, "do_orm_execute")
def reject_bulk_business_writes(state):
    if isinstance(state.statement, TextClause):
        statement = str(state.statement).strip().upper()
        if statement != "BEGIN" and not statement.startswith(("SELECT ", "SHOW ", "SET TRANSACTION ")):
            raise BusinessWriteError("Untracked SQL is forbidden in business sessions")
    if not (state.is_update or state.is_delete or state.is_insert):
        return
    name = getattr(getattr(state.statement, "table", None), "name", "")
    if name in BUSINESS_TABLES or name.startswith("skill_") or name == "skills":
        raise BusinessWriteError("Bulk business DML is forbidden; use tracked ORM rows")


async def mutate_rows(session, model, *criteria, values=None, remove=False) -> int:
    rows = list((await session.scalars(select(model).where(*criteria).with_for_update())).all())
    for row in rows:
        if remove:
            await session.delete(row)
        else:
            for name, value in (values or {}).items():
                setattr(row, name, value)
    return len(rows)
