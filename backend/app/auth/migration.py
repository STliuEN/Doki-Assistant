from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.audit import record_audit
from app.auth.authorization import assign_default_user_role
from app.auth.errors import AUTH_CONFLICT, AUTH_VALIDATION, AuthError
from app.auth.passwords import validate_password_hash
from app.auth.repository import normalize_email, normalize_phone, normalize_username
from app.models.identity_domain import MigrationMap, User, UserProfile


@dataclass(frozen=True, slots=True)
class LegacyUser:
    source_id: str
    username: str
    email: str
    password_hash: str
    telephone: str | None = None
    gender: str | None = None
    bio: str | None = None
    avatar: str | None = None
    last_login: datetime | None = None
    status: str = "active"


@dataclass(frozen=True, slots=True)
class MigrationPlan:
    migration_batch_id: str
    source_digest: str
    users: tuple[LegacyUser, ...]
    target_ids: dict[str, str]


class MigrationConflict(AuthError):
    def __init__(self, message: str) -> None:
        super().__init__(AUTH_CONFLICT, message, status_code=409)


_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_BATCH_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _source_datetime(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise MigrationConflict("Source last_login must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MigrationConflict("Source last_login must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise MigrationConflict("Source last_login must include timezone")
    return parsed.astimezone(UTC)


def _source_text(value: object, *, field: str, max_length: int) -> str | None:
    if value is None or value == "":
        return None
    allowed_controls = {"\t", "\n", "\r"}
    if not isinstance(value, str) or len(value) > max_length or any(ord(character) < 32 and character not in allowed_controls for character in value):
        raise MigrationConflict(f"Source {field} is invalid")
    return value


def source_digest(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise AuthError(AUTH_VALIDATION, "Source dump cannot be read", status_code=400) from exc


def _records_from_payload(payload) -> list[dict[str, object]]:
    if isinstance(payload, list):
        if not all(isinstance(item, dict) for item in payload):
            raise AuthError(AUTH_VALIDATION, "Every source user must be an object", status_code=400)
        return payload
    if isinstance(payload, dict):
        for key in ("users", "user_service", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                if not all(isinstance(item, dict) for item in value):
                    raise AuthError(AUTH_VALIDATION, "Every source user must be an object", status_code=400)
                return value
    raise AuthError(AUTH_VALIDATION, "Source dump must contain a users list", status_code=400)


def load_source_dump(path: str | Path) -> list[LegacyUser]:
    source_path = Path(path)
    try:
        if source_path.suffix.lower() in {".json", ".jsonl"}:
            if source_path.suffix.lower() == ".jsonl":
                payload = [json.loads(line) for line in source_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            else:
                payload = json.loads(source_path.read_text(encoding="utf-8"))
            records = _records_from_payload(payload)
        elif source_path.suffix.lower() == ".csv":
            with source_path.open(newline="", encoding="utf-8") as handle:
                records = list(csv.DictReader(handle))
        else:
            raise AuthError(AUTH_VALIDATION, "Only JSON, JSONL, and CSV dumps are supported", status_code=400)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuthError(AUTH_VALIDATION, "Source dump is invalid", status_code=400) from exc
    users: list[LegacyUser] = []
    for raw in records:
        source_id = str(raw.get("id") or raw.get("user_id") or raw.get("pk") or "").strip()
        username = str(raw.get("username") or "").strip()
        email = str(raw.get("email") or raw.get("email_display") or "").strip()
        password_hash = str(raw.get("password") or raw.get("password_hash") or "").strip()
        if not source_id or not username or not email or not password_hash:
            raise MigrationConflict("Every source user must include id, username, email, and password hash")
        users.append(
            LegacyUser(
                source_id=source_id,
                username=username,
                email=email,
                password_hash=password_hash,
                telephone=(str(raw.get("telephone") or raw.get("phone") or "").strip() or None),
                gender=(str(raw.get("gender")).strip() if raw.get("gender") is not None else None),
                bio=(str(raw.get("bio")).strip() if raw.get("bio") is not None else None),
                avatar=(str(raw.get("avatar")).strip() if raw.get("avatar") is not None else None),
                last_login=_source_datetime(raw.get("last_login")),
                status=str(raw.get("status") or "active").strip(),
            )
        )
    return users


def build_migration_plan(users: list[LegacyUser], *, migration_batch_id: str, source_digest_value: str) -> MigrationPlan:
    if not users:
        raise MigrationConflict("Source dump contains no users")
    if not _BATCH_ID_RE.fullmatch(migration_batch_id):
        raise MigrationConflict("Migration batch id is invalid")
    if not _DIGEST_RE.fullmatch(source_digest_value):
        raise MigrationConflict("Source digest is invalid")
    emails: set[str] = set()
    phones: set[str] = set()
    usernames: set[str] = set()
    source_ids: set[str] = set()
    target_ids: dict[str, str] = {}
    normalized_users: list[LegacyUser] = []
    for user in users:
        if not user.source_id or len(user.source_id) > 255 or any(ord(character) < 32 for character in user.source_id):
            raise MigrationConflict("Source user id is invalid")
        if user.source_id in source_ids:
            raise MigrationConflict("Duplicate source user id in source dump")
        source_ids.add(user.source_id)
        try:
            email = normalize_email(user.email)
            username = normalize_username(user.username)
            phone = normalize_phone(user.telephone)
        except AuthError as exc:
            raise MigrationConflict("Source user identity is invalid") from exc
        if email in emails or username in usernames:
            raise MigrationConflict("Duplicate user identity in source dump")
        emails.add(email)
        usernames.add(username)
        if phone:
            if phone in phones:
                raise MigrationConflict("Duplicate phone number in source dump")
            phones.add(phone)
        if user.status not in {"active", "disabled", "locked"}:
            raise MigrationConflict("Unsupported user status in source dump")
        if not validate_password_hash(user.password_hash):
            raise MigrationConflict("Unsupported password hash format in source dump")
        bio = _source_text(user.bio, field="bio", max_length=4096)
        avatar = _source_text(user.avatar, field="avatar", max_length=1024)
        target_ids[user.source_id] = str(uuid5(NAMESPACE_URL, f"django/user/{user.source_id}")).lower()
        normalized_users.append(
            LegacyUser(
                source_id=user.source_id,
                username=username,
                email=user.email.strip(),
                password_hash=user.password_hash,
                telephone=phone,
                gender=user.gender,
                bio=bio,
                avatar=avatar,
                last_login=user.last_login,
                status=user.status,
            )
        )
    return MigrationPlan(
        migration_batch_id=migration_batch_id,
        source_digest=source_digest_value,
        users=tuple(normalized_users),
        target_ids=target_ids,
    )


async def validate_migration_plan(session: AsyncSession, plan: MigrationPlan) -> None:
    """Validate the complete source plan against target identities without writes."""

    source_ids = [user.source_id for user in plan.users]
    maps = (
        await session.scalars(
            select(MigrationMap).where(
                MigrationMap.source_system == "django",
                MigrationMap.entity_type == "user",
                MigrationMap.source_id.in_(source_ids),
            )
        )
    ).all()
    maps_by_source = {row.source_id: row for row in maps}
    mapped_target_ids: set[str] = set()
    for user in plan.users:
        mapping = maps_by_source.get(user.source_id)
        if mapping is None:
            continue
        expected_target = plan.target_ids[user.source_id]
        if mapping.target_uuid != expected_target or mapping.source_digest != plan.source_digest:
            raise MigrationConflict("Existing migration map conflicts with this source digest")
        mapped_target_ids.add(mapping.target_uuid)

    usernames = [user.username.casefold() for user in plan.users]
    emails = [user.email.casefold() for user in plan.users]
    phones = [user.telephone for user in plan.users if user.telephone]
    target_ids = list(plan.target_ids.values())
    conditions = [func.lower(User.username).in_(usernames), User.email_normalized.in_(emails), User.id.in_(target_ids)]
    if phones:
        conditions.append(User.phone_e164.in_(phones))
    existing_users = (await session.scalars(select(User).where(or_(*conditions)))).all()
    existing_by_id = {row.id: row for row in existing_users}
    for row in existing_users:
        if row.id not in mapped_target_ids:
            raise MigrationConflict("Source identities conflict with existing target users")
    if mapped_target_ids - existing_by_id.keys():
        raise MigrationConflict("Existing migration map references a missing target user")


async def import_migration_plan(session: AsyncSession, plan: MigrationPlan, *, correlation_id: str) -> int:
    """Import a complete plan atomically; callers own the outer transaction."""

    await validate_migration_plan(session, plan)
    inserted = 0
    for legacy in plan.users:
        target_id = plan.target_ids[legacy.source_id]
        existing_map = await session.scalar(
            select(MigrationMap).where(
                MigrationMap.source_system == "django",
                MigrationMap.entity_type == "user",
                MigrationMap.source_id == legacy.source_id,
            )
        )
        if existing_map is not None:
            if existing_map.target_uuid != target_id or existing_map.source_digest != plan.source_digest:
                raise MigrationConflict("Existing migration map conflicts with this source digest")
            continue
        user = User(
            id=target_id,
            username=legacy.username,
            email_display=legacy.email,
            email_normalized=legacy.email.casefold(),
            phone_display=legacy.telephone,
            phone_e164=legacy.telephone,
            password_hash=legacy.password_hash,
            status=legacy.status,
            token_version=1,
        )
        profile = UserProfile(user_id=target_id, gender=legacy.gender, bio=legacy.bio, avatar=legacy.avatar, last_login=legacy.last_login)
        mapping = MigrationMap(
            migration_batch_id=plan.migration_batch_id,
            source_system="django",
            entity_type="user",
            source_id=legacy.source_id,
            target_uuid=target_id,
            source_digest=plan.source_digest,
            status="mapped",
        )
        session.add_all([user, profile, mapping])
        try:
            await session.flush()
        except IntegrityError as exc:
            raise MigrationConflict("User migration conflicts with target identities") from exc
        await assign_default_user_role(session, target_id)
        inserted += 1
    try:
        await session.flush()
    except IntegrityError as exc:
        raise MigrationConflict("User migration conflicts with target identities") from exc
    await record_audit(
        session,
        correlation_id=correlation_id,
        action="migration.users.import",
        target_type="migration",
        target_id=plan.migration_batch_id,
        result="success",
        reason="user migration imported",
        migration_id=plan.migration_batch_id,
        after={"count": inserted, "source_digest": plan.source_digest},
    )
    return inserted
