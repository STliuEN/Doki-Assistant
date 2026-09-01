from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job_domain import AuditEvent

_SENSITIVE_KEY = re.compile(r"(?:password|passwd|secret|token|cookie|hash|ip)", re.IGNORECASE)


def _safe(value):
    if isinstance(value, Mapping):
        return {str(key): _safe(item) for key, item in value.items() if not _SENSITIVE_KEY.search(str(key))}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (datetime, UUID)):
        return str(value)
    return str(value)


def safe_audit_value(value):
    return _safe(value)


async def record_audit(
    session: AsyncSession,
    *,
    action: str,
    target_type: str,
    target_id: str | None,
    result: str,
    reason: str,
    correlation_id: str | None = None,
    actor_type: str = "user",
    actor_id: str | None = None,
    actor_role: str | None = None,
    scope_type: str | None = None,
    scope_id: str | None = None,
    policy_revision: int | None = None,
    subject_revision: int | None = None,
    content_digest: str | None = None,
    before: Mapping | None = None,
    after: Mapping | None = None,
    grant_diff: Mapping | None = None,
    effective_at: datetime | None = None,
    expires_at: datetime | None = None,
    error_code: str | None = None,
    import_id: str | None = None,
    migration_id: str | None = None,
) -> AuditEvent:
    correlation = correlation_id or str(uuid4())
    event = AuditEvent(
        actor_type=actor_type,
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        target_type=target_type,
        target_id=target_id,
        scope_type=scope_type,
        scope_id=scope_id,
        policy_revision=policy_revision,
        subject_revision=subject_revision,
        content_digest=content_digest,
        before_json=safe_audit_value(before),
        after_json=safe_audit_value(after),
        grant_diff_json=safe_audit_value(grant_diff),
        reason=reason[:4096],
        effective_at=effective_at,
        expires_at=expires_at,
        result=result,
        error_code=error_code,
        correlation_id=correlation,
        import_id=import_id,
        migration_id=migration_id,
    )
    session.add(event)
    await session.flush()
    return event
