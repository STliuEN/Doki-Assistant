from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.e2.errors import E2PrimitiveValidationError

_UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def new_uuid() -> str:
    return str(uuid4())


def canonical_uuid(value: str | None, field: str, *, required: bool = True) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not _UUID_PATTERN.fullmatch(value):
        raise E2PrimitiveValidationError(f"{field} must be a lowercase UUIDv4")
    try:
        parsed = UUID(value)
    except ValueError as exc:
        raise E2PrimitiveValidationError(f"{field} must be a lowercase UUIDv4") from exc
    if parsed.version != 4 or str(parsed) != value:
        raise E2PrimitiveValidationError(f"{field} must be a lowercase UUIDv4")
    return value


def generated_or_canonical_uuid(value: str | None, field: str) -> str:
    return new_uuid() if value is None else canonical_uuid(value, field)  # type: ignore[return-value]


def required_text(value: str, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise E2PrimitiveValidationError(f"{field} must be a non-empty string of at most {maximum} characters")
    return value


def ascii_text(value: str, field: str, maximum: int) -> str:
    normalized = required_text(value, field, maximum)
    try:
        normalized.encode("ascii")
    except UnicodeEncodeError as exc:
        raise E2PrimitiveValidationError(f"{field} must contain ASCII characters only") from exc
    return normalized


def digest(value: str, field: str) -> str:
    if not isinstance(value, str) or not _DIGEST_PATTERN.fullmatch(value):
        raise E2PrimitiveValidationError(f"{field} must be a lowercase SHA-256 hex digest")
    return value


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json_bytes(value: Mapping[str, object], field: str = "JSON") -> bytes:
    if not isinstance(value, Mapping):
        raise E2PrimitiveValidationError(f"{field} must be a JSON object")
    try:
        rendered = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise E2PrimitiveValidationError(f"{field} must be deterministic and JSON-serializable") from exc
    return rendered.encode("utf-8")


def versioned_json(value: Mapping[str, object], schema_version: int, field: str, maximum: int) -> dict[str, object]:
    if not isinstance(schema_version, int) or schema_version <= 0:
        raise E2PrimitiveValidationError(f"{field} schema version must be positive")
    normalized = dict(value) if isinstance(value, Mapping) else None
    if normalized is None:
        raise E2PrimitiveValidationError(f"{field} must be a JSON object")
    if normalized.get("schema_version") != schema_version:
        raise E2PrimitiveValidationError(f"{field}.schema_version must match the declared version")
    if len(canonical_json_bytes(normalized, field)) > maximum:
        raise E2PrimitiveValidationError(f"{field} exceeds the {maximum}-byte UTF-8 limit")
    return normalized


def utc_datetime(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise E2PrimitiveValidationError(f"{field} must include a timezone")
    return value.astimezone(UTC)


async def database_now(session: AsyncSession) -> datetime:
    value = await session.scalar(select(func.current_timestamp()))
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, bytes):
        parsed = _parse_timestamp(value.decode("utf-8", errors="strict"))
    elif isinstance(value, str):
        parsed = _parse_timestamp(value)
    else:
        raise RuntimeError("database did not return a timestamp")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.strip().replace(" ", "T", 1))
    except ValueError as exc:
        raise RuntimeError("database returned an invalid timestamp") from exc
