"""Application service for the single standard Skill package lifecycle."""

from __future__ import annotations

import base64
import binascii
import hashlib
import logging
import uuid
import zipfile
from dataclasses import asdict
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Mapping, Sequence

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.skill_domain import (
    Skill,
    SkillAlias,
    SkillAuditEvent,
    SkillCapabilityGrant,
    SkillImport,
    SkillImportStatus,
    SkillInstallation,
    SkillInstallationStatus,
    SkillLifecycleStatus,
    SkillPackageFormat,
    SkillRegistryEvent,
    SkillRegistryState,
    SkillVersion,
    SkillVersionStatus,
)
from app.skills.package import SkillPackage, SkillPackageError
from app.skills.registry import (
    RuntimeSkill,
    RuntimeSkillResource,
    SkillRegistrySnapshot,
    standard_skill_registry,
)
from app.skills.schema import (
    SkillDraftCreate,
    SkillDraftUpdate,
    normalize_routing_examples,
    validate_skill_resource_budget,
)
from app.skills.storage import StoredSkillPackage, render_skill_markdown, skill_package_storage

SYSTEM_SCOPE_TYPE = "system"
SYSTEM_SCOPE_KEY = "global"
SYSTEM_ACTOR = "system"
MAX_RESOURCE_READ_BYTES = 2 * 1024 * 1024
logger = logging.getLogger(__name__)
SKILL_REGISTRY_STALE_MESSAGE = "Skill registry is updating; retry after instances converge"


class SkillNotFoundError(LookupError):
    pass


class SkillConflictError(RuntimeError):
    pass


class SkillRegistryStaleError(RuntimeError):
    pass


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    return value


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _sorted_skill_aliases(skill: Skill) -> tuple[SkillAlias, ...]:
    """Return aliases in a DB-instance-independent order."""

    return tuple(
        sorted(
            skill.aliases,
            key=lambda alias: (str(alias.alias_type or ""), str(alias.alias_name)),
        )
    )


def _public_skill_id(skill: Skill) -> str:
    """Choose the stable legacy/public ID independent of relationship order."""

    aliases = tuple(alias for alias in _sorted_skill_aliases(skill) if "_" in alias.alias_name)
    return aliases[0].alias_name if aliases else skill.canonical_name


def _routing_examples(settings: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    raw = settings.get("routing_examples", {})
    if not isinstance(raw, Mapping):
        return {}
    return {
        key: tuple(str(item) for item in values if isinstance(item, str) and item.strip())
        for key in ("positive", "negative")
        if isinstance((values := raw.get(key)), list)
    }


def _manifest(package: SkillPackage) -> dict[str, Any]:
    has_scripts = any(resource.kind == "script" for resource in package.resource_manifest)
    level = "C" if has_scripts else ("B" if len(package.resource_manifest) > 1 else "A")
    reasons = (
        ["Package scripts are preserved but disabled until an isolated Skill runner is available."]
        if has_scripts
        else []
    )
    return {
        "frontmatter": _json_value(package.metadata.frontmatter),
        "instructions": package.instructions,
        "resources": [asdict(resource) for resource in package.resource_manifest],
        "total_uncompressed_bytes": package.total_uncompressed_bytes,
        "compatibility": {
            "level": level,
            "format_compatible": True,
            "runtime_ready": not has_scripts,
            "reasons": reasons,
        },
    }


def _requested_capabilities(package: SkillPackage) -> dict[str, Any]:
    scripts = [resource.path for resource in package.resource_manifest if resource.kind == "script"]
    return {"scripts": scripts, "tools": [], "network": [], "secrets": []}


def _effective_grants(version: SkillVersion, tools: Sequence[str]) -> dict[str, Any]:
    """Return the fail-closed capability set approved for a package version."""

    resources = [
        item["path"]
        for item in (version.manifest or {}).get("resources", [])
        if item.get("path") != "SKILL.md" and item.get("kind") != "script"
    ]
    return {
        "tools": list(dict.fromkeys(tools)),
        "resources": {"read": resources},
        # Executable, network, and secret grants remain empty until the
        # isolated runner and security-admin approval flow exist.
        "scripts": [],
        "network": [],
        "secrets": [],
    }


def _installation_settings(
    *,
    default: bool,
    visibility: str,
    order: int,
    tools: Sequence[str],
    always_on: bool,
    routable: bool,
    routing_examples: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    return {
        "default": bool(default),
        "visibility": visibility,
        "order": int(order),
        "tools": list(dict.fromkeys(tools)),
        "always_on": bool(always_on),
        "routable": bool(routable),
        "routing_examples": {
            key: list(dict.fromkeys(values))
            for key, values in normalize_routing_examples(
                {key: list(values) for key, values in routing_examples.items()}
            ).items()
        },
    }


class SkillService:
    def __init__(self) -> None:
        self.storage = skill_package_storage
        self.registry = standard_skill_registry

    @staticmethod
    async def _next_version_number(db: AsyncSession, skill_id: str) -> int:
        result = await db.execute(select(func.coalesce(func.max(SkillVersion.version_number), 0)).where(SkillVersion.skill_id == skill_id))
        return int(result.scalar_one()) + 1

    @staticmethod
    async def _find_skill(db: AsyncSession, identifier: str, *, include_archived: bool = False) -> Skill | None:
        statement = (
            select(Skill)
            .outerjoin(SkillAlias, SkillAlias.skill_id == Skill.id)
            .where(
                or_(
                    Skill.id == identifier,
                    Skill.canonical_name == identifier,
                    SkillAlias.alias_name == identifier,
                )
            )
            .options(selectinload(Skill.aliases), selectinload(Skill.installations))
        )
        if not include_archived:
            statement = statement.where(Skill.status == SkillLifecycleStatus.ACTIVE)
        result = await db.execute(statement.execution_options(populate_existing=True))
        return result.unique().scalar_one_or_none()

    @staticmethod
    async def _installation(
        db: AsyncSession,
        skill_id: str,
        *,
        for_update: bool = False,
    ) -> SkillInstallation | None:
        statement = (
            select(SkillInstallation)
            .where(
                SkillInstallation.skill_id == skill_id,
                SkillInstallation.scope_type == SYSTEM_SCOPE_TYPE,
                SkillInstallation.scope_key == SYSTEM_SCOPE_KEY,
            )
            .options(
                selectinload(SkillInstallation.active_version),
                selectinload(SkillInstallation.draft_version),
                selectinload(SkillInstallation.capability_grants),
            )
            .execution_options(populate_existing=True)
        )
        if for_update:
            statement = statement.with_for_update()
        result = await db.execute(statement)
        return result.scalar_one_or_none()

    @staticmethod
    async def _upsert_capability_grant(
        db: AsyncSession,
        *,
        installation: SkillInstallation,
        version: SkillVersion,
        tools: Sequence[str],
        actor_id: str,
    ) -> SkillCapabilityGrant:
        result = await db.execute(
            select(SkillCapabilityGrant).where(
                SkillCapabilityGrant.installation_id == installation.id,
                SkillCapabilityGrant.skill_version_id == version.id,
            )
        )
        grant = result.scalar_one_or_none()
        grants = _effective_grants(version, tools)
        if grant is None:
            grant = SkillCapabilityGrant(
                installation_id=installation.id,
                skill_version_id=version.id,
                grants=grants,
                revision=1,
                granted_by=actor_id,
            )
            db.add(grant)
        else:
            grant.grants = grants
            grant.revision = int(grant.revision) + 1
            grant.granted_by = actor_id
            grant.revoked_at = None
        await db.flush()
        return grant

    @staticmethod
    def _assert_revision(installation: SkillInstallation, expected_revision: int) -> None:
        if int(installation.revision) != expected_revision:
            raise SkillConflictError(
                f"Skill revision changed from {expected_revision} to {installation.revision}; reload before saving"
            )

    @staticmethod
    def _audit(
        db: AsyncSession,
        *,
        action: str,
        actor_id: str,
        skill_id: str | None,
        version_id: str | None = None,
        installation_id: str | None = None,
        import_id: str | None = None,
        before: Mapping[str, Any] | None = None,
        after: Mapping[str, Any] | None = None,
        details: Mapping[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        db.add(
            SkillAuditEvent(
                skill_id=skill_id,
                skill_version_id=version_id,
                installation_id=installation_id,
                import_id=import_id,
                actor_type="system" if actor_id == SYSTEM_ACTOR else "user",
                actor_id=actor_id,
                action=action,
                target_type="skill",
                target_id=skill_id,
                correlation_id=correlation_id or str(uuid.uuid4()),
                before_state=dict(before) if before else None,
                after_state=dict(after) if after else None,
                details=dict(details or {}),
            )
        )

    @staticmethod
    async def _bump_registry(
        db: AsyncSession,
        *,
        skill_id: str | None,
        event_type: str,
        payload: Mapping[str, Any] | None = None,
    ) -> int:
        result = await db.execute(
            select(SkillRegistryState).where(SkillRegistryState.id == "global").with_for_update()
        )
        state = result.scalar_one_or_none()
        if state is None:
            state = SkillRegistryState(id="global", revision=0)
            db.add(state)
            await db.flush()
        state.revision = int(state.revision) + 1
        db.add(
            SkillRegistryEvent(
                revision=state.revision,
                event_type=event_type,
                skill_id=skill_id,
                payload=dict(payload or {}),
            )
        )
        return int(state.revision)

    async def _refresh_registry_after_commit(self, db: AsyncSession, *, operation: str) -> None:
        """Best-effort in-process publication after the durable transaction commits.

        The outbox reconciler remains authoritative for convergence. A failed
        in-memory refresh must never turn an already committed write into an
        apparent API failure that callers may retry as though it rolled back.
        """

        try:
            await self.refresh_registry(db)
        except Exception:
            logger.exception(
                "Skill %s committed, but the local registry refresh failed; outbox reconciliation will retry",
                operation,
            )

    @staticmethod
    def _archive_from_draft(
        payload: SkillDraftCreate | SkillDraftUpdate,
        *,
        existing_resources: Mapping[str, bytes] | None = None,
    ) -> bytes:
        submitted_resources = payload.resources
        resource_changes = getattr(payload, "resource_changes", None)
        if submitted_resources is None and resource_changes is not None:
            submitted_resources = resource_changes.upsert
        try:
            validate_skill_resource_budget(list(submitted_resources or []))
        except ValueError as exc:
            raise SkillPackageError("resource_budget", str(exc)) from exc

        files = dict(existing_resources or {})
        if payload.resources is not None:
            files = {}
            for resource in payload.resources:
                if resource.path == "SKILL.md":
                    raise SkillPackageError("resource_reserved", "SKILL.md is managed by the structured editor")
                try:
                    files[resource.path] = base64.b64decode(resource.content_base64, validate=True)
                except (binascii.Error, ValueError) as exc:
                    raise SkillPackageError("resource_encoding", "resource content must be valid base64", path=resource.path) from exc
        if resource_changes is not None:
            for path in resource_changes.delete:
                if path == "SKILL.md":
                    raise SkillPackageError("resource_reserved", "SKILL.md is managed by the structured editor")
                files.pop(path, None)
            for resource in resource_changes.upsert:
                if resource.path == "SKILL.md":
                    raise SkillPackageError("resource_reserved", "SKILL.md is managed by the structured editor")
                try:
                    files[resource.path] = base64.b64decode(resource.content_base64, validate=True)
                except (binascii.Error, ValueError) as exc:
                    raise SkillPackageError(
                        "resource_encoding",
                        "resource content must be valid base64",
                        path=resource.path,
                    ) from exc
        files["SKILL.md"] = render_skill_markdown(
            name=payload.name,
            description=payload.description,
            instructions=payload.instructions,
            frontmatter=payload.frontmatter,
        )
        from app.skills.storage import build_skill_archive

        return build_skill_archive(files)

    def _read_version_resources(self, version: SkillVersion) -> dict[str, bytes]:
        archive_bytes = self.storage.read_archive(
            version.storage_key,
            expected_digest=version.package_digest,
        )
        with zipfile.ZipFile(BytesIO(archive_bytes), "r") as archive:
            return {
                info.filename: archive.read(info)
                for info in archive.infolist()
                if not info.is_dir() and info.filename != "SKILL.md"
            }

    async def _create_version(
        self,
        db: AsyncSession,
        *,
        skill: Skill,
        stored: StoredSkillPackage,
        actor_id: str,
        source: str,
        display_name: str | None,
        parent_version_id: str | None,
        status: SkillVersionStatus,
        version_note: str = "",
    ) -> SkillVersion:
        existing_result = await db.execute(select(SkillVersion).where(SkillVersion.package_digest == stored.digest))
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            if existing.skill_id != skill.id:
                raise SkillConflictError("An identical package is already owned by another Skill")
            requested_display_name = display_name or stored.package.metadata.name
            existing_version_note = str((existing.manifest or {}).get("version_note", ""))
            if existing.display_name != requested_display_name or existing_version_note != version_note:
                raise SkillConflictError(
                    "An identical package already exists with different display metadata; "
                    "change the package content or restore the reviewed display name and version note"
                )
            if status == SkillVersionStatus.READY and existing.status == SkillVersionStatus.DRAFT:
                existing.status = SkillVersionStatus.READY
                existing.published_at = existing.published_at or _now()
                await db.flush()
            elif status == SkillVersionStatus.READY and existing.status != SkillVersionStatus.READY:
                raise SkillConflictError(
                    f"Existing package version cannot transition from {existing.status.value} to ready"
                )
            return existing

        manifest = _manifest(stored.package)
        manifest["version_note"] = version_note
        version = SkillVersion(
            skill_id=skill.id,
            parent_version_id=parent_version_id,
            version_number=await self._next_version_number(db, skill.id),
            package_format=SkillPackageFormat.AGENT_SKILLS_V1,
            source=source,
            package_digest=stored.digest,
            storage_key=stored.storage_key,
            package_size_bytes=stored.archive_size,
            name=stored.package.metadata.name,
            display_name=display_name or stored.package.metadata.name,
            description=stored.package.metadata.description,
            manifest=manifest,
            requested_capabilities=_requested_capabilities(stored.package),
            status=status,
            created_by=actor_id,
            published_at=_now() if status == SkillVersionStatus.READY else None,
        )
        db.add(version)
        await db.flush()
        return version

    async def create_draft(self, db: AsyncSession, payload: SkillDraftCreate, actor_id: str) -> dict[str, Any]:
        if await self._find_skill(db, payload.name, include_archived=True) is not None:
            raise SkillConflictError("Skill name or alias already exists")
        stored = self.storage.store_archive(self._archive_from_draft(payload))
        skill = Skill(canonical_name=stored.package.metadata.name, created_by=actor_id)
        db.add(skill)
        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            raise SkillConflictError("Skill name or alias was claimed concurrently; reload and try again") from exc
        version = await self._create_version(
            db,
            skill=skill,
            stored=stored,
            actor_id=actor_id,
            source="visual_editor",
            display_name=payload.display_name,
            parent_version_id=None,
            status=SkillVersionStatus.DRAFT,
            version_note=payload.version_note,
        )
        installation = SkillInstallation(
            skill_id=skill.id,
            active_version_id=None,
            draft_version_id=version.id,
            status=SkillInstallationStatus.DISABLED,
            settings=_installation_settings(
                default=False,
                visibility="public",
                order=100,
                tools=(),
                always_on=False,
                routable=True,
                routing_examples={},
            ),
            revision=1,
            created_by=actor_id,
            updated_by=actor_id,
        )
        db.add(installation)
        await db.flush()
        self._audit(
            db,
            action="draft_created",
            actor_id=actor_id,
            skill_id=skill.id,
            version_id=version.id,
            installation_id=installation.id,
            after={"revision": 1, "digest": version.package_digest},
        )
        await db.commit()
        return await self.get_detail(db, skill.id, can_manage=True)

    async def save_draft(
        self,
        db: AsyncSession,
        identifier: str,
        payload: SkillDraftUpdate,
        actor_id: str,
    ) -> dict[str, Any]:
        skill = await self._find_skill(db, identifier)
        if skill is None:
            raise SkillNotFoundError(identifier)
        installation = await self._installation(db, skill.id, for_update=True)
        if installation is None:
            raise SkillNotFoundError(identifier)
        self._assert_revision(installation, payload.expected_revision)
        base_version = installation.draft_version or installation.active_version
        existing_resources = self._read_version_resources(base_version) if base_version and payload.resources is None else None
        stored = self.storage.store_archive(self._archive_from_draft(payload, existing_resources=existing_resources))
        if stored.package.metadata.name != skill.canonical_name:
            raise SkillConflictError("Renaming a Skill is not supported; create a new Skill instead")
        version = await self._create_version(
            db,
            skill=skill,
            stored=stored,
            actor_id=actor_id,
            source="visual_editor",
            display_name=payload.display_name,
            parent_version_id=base_version.id if base_version else None,
            status=SkillVersionStatus.DRAFT,
            version_note=payload.version_note,
        )
        before = int(installation.revision)
        installation.draft_version_id = version.id
        installation.revision = before + 1
        installation.updated_by = actor_id
        self._audit(
            db,
            action="draft_saved",
            actor_id=actor_id,
            skill_id=skill.id,
            version_id=version.id,
            installation_id=installation.id,
            before={"revision": before},
            after={"revision": installation.revision, "digest": version.package_digest},
        )
        await db.commit()
        return await self.get_detail(db, skill.id, can_manage=True)

    async def import_archive(
        self,
        db: AsyncSession,
        archive_bytes: bytes,
        *,
        actor_id: str,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        request_digest = hashlib.sha256(archive_bytes).hexdigest()
        request_key = idempotency_key or hashlib.sha256(
            actor_id.encode() + b"\0" + request_digest.encode("ascii")
        ).hexdigest()
        existing_result = await db.execute(select(SkillImport).where(SkillImport.idempotency_key == request_key))
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            if existing.requested_by != actor_id or existing.request_archive_digest != request_digest:
                raise SkillConflictError("Idempotency-Key is already bound to a different actor or archive")
            return self._import_response(existing)

        import_record = SkillImport(
            requested_by=actor_id,
            idempotency_key=request_key,
            request_archive_digest=request_digest,
            source_kind="upload",
            status=SkillImportStatus.RECEIVED,
            diagnostics=[],
            requested_capabilities={},
            attempt_count=1,
            started_at=_now(),
        )
        db.add(import_record)
        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            raced_result = await db.execute(
                select(SkillImport).where(SkillImport.idempotency_key == request_key)
            )
            raced = raced_result.scalar_one_or_none()
            if (
                raced is not None
                and raced.requested_by == actor_id
                and raced.request_archive_digest == request_digest
            ):
                return self._import_response(raced)
            raise SkillConflictError(
                "Idempotency-Key is already bound to a different actor or archive"
            ) from exc
        try:
            stored = self.storage.store_archive(archive_bytes)
        except SkillPackageError as exc:
            import_record.status = SkillImportStatus.QUARANTINED
            import_record.error_code = exc.code
            import_record.error_message = exc.detail
            import_record.diagnostics = [{"code": exc.code, "detail": exc.detail, "path": exc.path}]
            import_record.completed_at = _now()
            self._audit(
                db,
                action="import_quarantined",
                actor_id=actor_id,
                skill_id=None,
                import_id=import_record.id,
                details={"error_code": exc.code},
            )
            await db.commit()
            await db.refresh(import_record)
            return self._import_response(import_record)

        import_record.staged_storage_key = stored.storage_key
        import_record.package_digest = stored.digest
        import_record.package_size_bytes = stored.archive_size
        import_record.discovered_canonical_name = stored.package.metadata.name
        import_record.requested_capabilities = _requested_capabilities(stored.package)
        existing_skill = await self._find_skill(
            db,
            stored.package.metadata.name,
            include_archived=True,
        )
        if existing_skill is not None:
            existing_installation = await self._installation(db, existing_skill.id)
            if existing_installation is not None:
                import_record.target_revision = int(existing_installation.revision)
        import_record.diagnostics = []
        import_record.status = SkillImportStatus.AWAITING_APPROVAL
        await db.commit()
        await db.refresh(import_record)
        return self._import_response(import_record)

    async def get_import(self, db: AsyncSession, import_id: str, actor_id: str) -> dict[str, Any]:
        result = await db.execute(select(SkillImport).where(SkillImport.id == import_id))
        record = result.scalar_one_or_none()
        if record is None or record.requested_by != actor_id:
            raise SkillNotFoundError(import_id)
        return self._import_response(record)

    @staticmethod
    def _import_response(record: SkillImport) -> dict[str, Any]:
        has_scripts = bool((record.requested_capabilities or {}).get("scripts"))
        compatibility = None
        if record.package_digest:
            compatibility = {
                "level": "C" if has_scripts else "A/B",
                "format_compatible": True,
                "runtime_ready": not has_scripts,
                "reasons": ["Executable packages require the isolated runner."] if has_scripts else [],
            }
        return {
            "id": record.id,
            "status": record.status.value if hasattr(record.status, "value") else str(record.status),
            "digest": record.package_digest,
            "name": record.discovered_canonical_name,
            "revision": int(record.target_revision) if record.target_revision is not None else None,
            "compatibility": compatibility,
            "diagnostics": list(record.diagnostics or []),
            "created_at": _timestamp(record.created_at),
            "updated_at": _timestamp(record.updated_at),
        }

    async def approve_import(
        self,
        db: AsyncSession,
        import_id: str,
        *,
        actor_id: str,
        expected_digest: str,
        expected_revision: int,
        enabled: bool,
        default: bool,
        visibility: str,
        order: int,
        tools: Sequence[str],
        always_on: bool,
        routable: bool,
        routing_examples: Mapping[str, Sequence[str]],
    ) -> dict[str, Any]:
        result = await db.execute(select(SkillImport).where(SkillImport.id == import_id).with_for_update())
        record = result.scalar_one_or_none()
        if record is None:
            raise SkillNotFoundError(import_id)
        if record.package_digest != expected_digest:
            raise SkillConflictError("Imported package digest changed; review it again")
        if record.status == SkillImportStatus.PUBLISHED and record.skill_id:
            return await self.get_detail(db, record.skill_id, can_manage=True)
        if record.status != SkillImportStatus.AWAITING_APPROVAL or not record.staged_storage_key:
            raise SkillConflictError(f"Import is not awaiting approval: {record.status}")
        stored = self.storage.load_archive(
            record.staged_storage_key,
            expected_digest=record.package_digest,
        )
        skill = await self._find_skill(db, stored.package.metadata.name, include_archived=True)
        reviewed_revision = int(record.target_revision) if record.target_revision is not None else 0
        if expected_revision != reviewed_revision:
            raise SkillConflictError(
                f"Import was reviewed at revision {reviewed_revision}; reload and review it again"
            )

        if record.target_revision is not None and skill is None:
            raise SkillConflictError(
                "The reviewed Skill no longer exists; reload and review the import again"
            )
        if skill is None:
            skill = Skill(canonical_name=stored.package.metadata.name, created_by=actor_id)
            db.add(skill)
            try:
                await db.flush()
            except IntegrityError as exc:
                await db.rollback()
                raise SkillConflictError(
                    "Skill canonical name was claimed concurrently; reload and review the import again"
                ) from exc
        elif skill.status == SkillLifecycleStatus.ARCHIVED:
            raise SkillConflictError("An archived Skill already owns this canonical name")
        elif record.target_revision is None:
            raise SkillConflictError(
                "Skill canonical name was created after import review; reload and review the import again"
            )
        installation = await self._installation(db, skill.id, for_update=True)
        if record.target_revision is None:
            if installation is not None:
                raise SkillConflictError(
                    "A Skill installation was created after import review; reload and review the import again"
                )
        else:
            if installation is None:
                raise SkillConflictError(
                    "The reviewed Skill installation no longer exists; reload and review the import again"
                )
            self._assert_revision(installation, reviewed_revision)
        parent = installation.active_version if installation else None
        version = await self._create_version(
            db,
            skill=skill,
            stored=stored,
            actor_id=actor_id,
            source="import",
            display_name=None,
            parent_version_id=parent.id if parent else None,
            status=SkillVersionStatus.READY,
        )
        has_scripts = bool((version.requested_capabilities or {}).get("scripts"))
        effective_enabled = enabled and not has_scripts
        settings = _installation_settings(
            default=default and effective_enabled,
            visibility=visibility,
            order=order,
            tools=tools,
            always_on=always_on,
            routable=routable,
            routing_examples=routing_examples,
        )
        if installation is None:
            installation = SkillInstallation(
                skill_id=skill.id,
                active_version_id=version.id,
                draft_version_id=None,
                status=SkillInstallationStatus.ENABLED if effective_enabled else SkillInstallationStatus.DISABLED,
                settings=settings,
                revision=1,
                created_by=actor_id,
                updated_by=actor_id,
            )
            db.add(installation)
            await db.flush()
        else:
            installation.active_version_id = version.id
            installation.draft_version_id = None
            installation.status = SkillInstallationStatus.ENABLED if effective_enabled else SkillInstallationStatus.DISABLED
            installation.settings = settings
            installation.revision = int(installation.revision) + 1
            installation.updated_by = actor_id
        await self._upsert_capability_grant(
            db,
            installation=installation,
            version=version,
            tools=tools,
            actor_id=actor_id,
        )
        record.status = SkillImportStatus.PUBLISHED
        record.skill_id = skill.id
        record.skill_version_id = version.id
        record.completed_at = _now()
        await self._bump_registry(db, skill_id=skill.id, event_type="skill_import_published")
        self._audit(
            db,
            action="import_published",
            actor_id=actor_id,
            skill_id=skill.id,
            version_id=version.id,
            installation_id=installation.id,
            import_id=record.id,
            after={"revision": installation.revision, "digest": version.package_digest, "enabled": effective_enabled},
            details={"script_execution_blocked": has_scripts},
        )
        await db.commit()
        await db.refresh(record)
        await self._refresh_registry_after_commit(db, operation="import approval")
        return await self.get_detail(db, skill.id, can_manage=True)

    async def publish_draft(
        self,
        db: AsyncSession,
        identifier: str,
        *,
        actor_id: str,
        expected_revision: int,
        enabled: bool,
        default: bool,
        visibility: str,
        order: int,
        tools: Sequence[str],
        always_on: bool,
        routable: bool,
        routing_examples: Mapping[str, Sequence[str]],
    ) -> dict[str, Any]:
        skill = await self._find_skill(db, identifier)
        if skill is None:
            raise SkillNotFoundError(identifier)
        installation = await self._installation(db, skill.id, for_update=True)
        if installation is None or installation.draft_version is None:
            raise SkillConflictError("Skill has no draft to publish")
        self._assert_revision(installation, expected_revision)
        version = installation.draft_version
        compatibility = (version.manifest or {}).get("compatibility", {})
        runtime_ready = bool(compatibility.get("runtime_ready", False))
        effective_enabled = enabled and runtime_ready
        before = {"revision": int(installation.revision), "active_version_id": installation.active_version_id}
        version.status = SkillVersionStatus.READY
        version.published_at = _now()
        installation.active_version_id = version.id
        installation.draft_version_id = None
        installation.status = SkillInstallationStatus.ENABLED if effective_enabled else SkillInstallationStatus.DISABLED
        installation.settings = _installation_settings(
            default=default and effective_enabled,
            visibility=visibility,
            order=order,
            tools=tools,
            always_on=always_on,
            routable=routable,
            routing_examples=routing_examples,
        )
        installation.revision = int(installation.revision) + 1
        installation.updated_by = actor_id
        await self._upsert_capability_grant(
            db,
            installation=installation,
            version=version,
            tools=tools,
            actor_id=actor_id,
        )
        await self._bump_registry(db, skill_id=skill.id, event_type="skill_published")
        self._audit(
            db,
            action="published",
            actor_id=actor_id,
            skill_id=skill.id,
            version_id=version.id,
            installation_id=installation.id,
            before=before,
            after={"revision": installation.revision, "active_version_id": version.id, "enabled": effective_enabled},
            details={"requested_enabled": enabled, "runtime_ready": runtime_ready},
        )
        await db.commit()
        await self._refresh_registry_after_commit(db, operation="draft publication")
        return await self.get_detail(db, skill.id, can_manage=True)

    async def update_settings(
        self,
        db: AsyncSession,
        identifier: str,
        *,
        actor_id: str,
        expected_revision: int,
        patch: Mapping[str, Any],
    ) -> dict[str, Any]:
        skill = await self._find_skill(db, identifier)
        if skill is None:
            raise SkillNotFoundError(identifier)
        installation = await self._installation(db, skill.id, for_update=True)
        if installation is None:
            raise SkillNotFoundError(identifier)
        self._assert_revision(installation, expected_revision)
        before = {"revision": int(installation.revision), "status": installation.status.value, "settings": dict(installation.settings or {})}
        settings = dict(installation.settings or {})
        for key in ("default", "visibility", "order", "tools", "always_on", "routable", "routing_examples"):
            if key in patch and patch[key] is not None:
                settings[key] = patch[key]
        if "enabled" in patch and patch["enabled"] is not None:
            if patch["enabled"] and installation.active_version is None:
                raise SkillConflictError("A Skill without a published version cannot be enabled")
            compatibility = ((installation.active_version.manifest or {}).get("compatibility", {}) if installation.active_version else {})
            if patch["enabled"] and not compatibility.get("runtime_ready", False):
                raise SkillConflictError("This Skill is not runtime ready and cannot be enabled")
            installation.status = SkillInstallationStatus.ENABLED if patch["enabled"] else SkillInstallationStatus.DISABLED
            if not patch["enabled"]:
                settings["default"] = False
        if installation.status != SkillInstallationStatus.ENABLED:
            settings["default"] = False
        installation.settings = settings
        installation.revision = int(installation.revision) + 1
        installation.updated_by = actor_id
        if installation.active_version is not None:
            await self._upsert_capability_grant(
                db,
                installation=installation,
                version=installation.active_version,
                tools=settings.get("tools", []),
                actor_id=actor_id,
            )
        await self._bump_registry(db, skill_id=skill.id, event_type="skill_settings_changed")
        self._audit(
            db,
            action="settings_updated",
            actor_id=actor_id,
            skill_id=skill.id,
            installation_id=installation.id,
            before=before,
            after={"revision": installation.revision, "status": installation.status.value, "settings": settings},
        )
        await db.commit()
        await self._refresh_registry_after_commit(db, operation="settings update")
        return await self.get_detail(db, skill.id, can_manage=True)

    async def activate_version(
        self,
        db: AsyncSession,
        identifier: str,
        version_id: str,
        *,
        actor_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        skill = await self._find_skill(db, identifier)
        if skill is None:
            raise SkillNotFoundError(identifier)
        installation = await self._installation(db, skill.id, for_update=True)
        if installation is None:
            raise SkillNotFoundError(identifier)
        self._assert_revision(installation, expected_revision)
        result = await db.execute(
            select(SkillVersion).where(
                SkillVersion.id == version_id,
                SkillVersion.skill_id == skill.id,
                SkillVersion.status == SkillVersionStatus.READY,
            )
        )
        version = result.scalar_one_or_none()
        if version is None:
            raise SkillNotFoundError(version_id)
        before_id = installation.active_version_id
        installation.active_version_id = version.id
        installation.draft_version_id = None
        runtime_ready = bool((version.manifest or {}).get("compatibility", {}).get("runtime_ready", False))
        if not runtime_ready:
            installation.status = SkillInstallationStatus.DISABLED
            installation.settings = {**dict(installation.settings or {}), "default": False}
        installation.revision = int(installation.revision) + 1
        installation.updated_by = actor_id
        await self._upsert_capability_grant(
            db,
            installation=installation,
            version=version,
            tools=(installation.settings or {}).get("tools", []),
            actor_id=actor_id,
        )
        await self._bump_registry(db, skill_id=skill.id, event_type="skill_version_activated")
        self._audit(
            db,
            action="version_activated",
            actor_id=actor_id,
            skill_id=skill.id,
            version_id=version.id,
            installation_id=installation.id,
            before={"active_version_id": before_id},
            after={"active_version_id": version.id, "revision": installation.revision},
        )
        await db.commit()
        await self._refresh_registry_after_commit(db, operation="version activation")
        return await self.get_detail(db, skill.id, can_manage=True)

    async def rollback(
        self,
        db: AsyncSession,
        identifier: str,
        *,
        actor_id: str,
        expected_revision: int,
        version_id: str | None,
    ) -> dict[str, Any]:
        skill = await self._find_skill(db, identifier)
        if skill is None:
            raise SkillNotFoundError(identifier)
        installation = await self._installation(db, skill.id, for_update=True)
        if installation is None:
            raise SkillNotFoundError(identifier)
        self._assert_revision(installation, expected_revision)
        statement = select(SkillVersion).where(
            SkillVersion.skill_id == skill.id,
            SkillVersion.status == SkillVersionStatus.READY,
            SkillVersion.id != installation.active_version_id,
        )
        if version_id:
            statement = statement.where(SkillVersion.id == version_id)
        else:
            statement = statement.order_by(SkillVersion.version_number.desc()).limit(1)
        result = await db.execute(statement)
        version = result.scalar_one_or_none()
        if version is None:
            raise SkillNotFoundError(version_id or "previous version")
        return await self.activate_version(
            db,
            identifier,
            version.id,
            actor_id=actor_id,
            expected_revision=expected_revision,
        )

    async def archive(
        self,
        db: AsyncSession,
        identifier: str,
        actor_id: str,
        *,
        expected_revision: int,
    ) -> None:
        skill = await self._find_skill(db, identifier)
        if skill is None:
            raise SkillNotFoundError(identifier)
        installation = await self._installation(db, skill.id, for_update=True)
        if installation is None:
            raise SkillNotFoundError(identifier)
        self._assert_revision(installation, expected_revision)
        installation.status = SkillInstallationStatus.DISABLED
        installation.settings = {**dict(installation.settings or {}), "default": False}
        installation.revision = int(installation.revision) + 1
        installation.updated_by = actor_id
        skill.status = SkillLifecycleStatus.ARCHIVED
        skill.archived_at = _now()
        await self._bump_registry(db, skill_id=skill.id, event_type="skill_archived")
        self._audit(
            db,
            action="archived",
            actor_id=actor_id,
            skill_id=skill.id,
            installation_id=installation.id,
            before={"revision": expected_revision},
            after={"revision": installation.revision},
        )
        await db.commit()
        await self._refresh_registry_after_commit(db, operation="archive")

    async def list_versions(self, db: AsyncSession, identifier: str) -> dict[str, Any]:
        skill = await self._find_skill(db, identifier)
        if skill is None:
            raise SkillNotFoundError(identifier)
        installation = await self._installation(db, skill.id)
        result = await db.execute(
            select(SkillVersion)
            .where(SkillVersion.skill_id == skill.id)
            .order_by(SkillVersion.version_number.desc())
        )
        versions = result.scalars().all()
        return {
            "versions": [
                {
                    "id": version.id,
                    "version": version.version_number,
                    "digest": version.package_digest,
                    "status": version.status.value,
                    "origin": {"type": version.source},
                    "version_note": (version.manifest or {}).get("version_note", ""),
                    "active": installation is not None and version.id == installation.active_version_id,
                    "created_at": _timestamp(version.created_at),
                }
                for version in versions
            ]
        }

    async def export_version(self, db: AsyncSession, identifier: str, version_id: str) -> tuple[bytes, str]:
        skill = await self._find_skill(db, identifier)
        if skill is None:
            raise SkillNotFoundError(identifier)
        result = await db.execute(
            select(SkillVersion).where(SkillVersion.skill_id == skill.id, SkillVersion.id == version_id)
        )
        version = result.scalar_one_or_none()
        if version is None:
            raise SkillNotFoundError(version_id)
        return (
            self.storage.read_archive(
                version.storage_key,
                expected_digest=version.package_digest,
            ),
            f"{skill.canonical_name}-v{version.version_number}.zip",
        )

    async def list_resources(self, db: AsyncSession, identifier: str) -> list[dict[str, Any]]:
        skill = await self._find_skill(db, identifier)
        if skill is None:
            raise SkillNotFoundError(identifier)
        installation = await self._installation(db, skill.id)
        version = installation.draft_version or installation.active_version if installation else None
        if version is None:
            return []
        return list((version.manifest or {}).get("resources", []))

    async def read_resource(self, db: AsyncSession, identifier: str, resource_path: str) -> tuple[bytes, str]:
        skill = await self._find_skill(db, identifier)
        if skill is None:
            raise SkillNotFoundError(identifier)
        installation = await self._installation(db, skill.id)
        version = installation.draft_version or installation.active_version if installation else None
        if version is None:
            raise SkillNotFoundError(resource_path)
        resources = {item["path"]: item for item in (version.manifest or {}).get("resources", [])}
        resource = resources.get(resource_path)
        if resource is None or resource_path == "SKILL.md":
            raise SkillNotFoundError(resource_path)
        content = self.storage.read_resource(
            version.storage_key,
            resource_path,
            max_bytes=MAX_RESOURCE_READ_BYTES,
            expected_digest=version.package_digest,
        )
        return content, "application/octet-stream"

    async def get_detail(self, db: AsyncSession, identifier: str, *, can_manage: bool) -> dict[str, Any]:
        skill = await self._find_skill(db, identifier)
        if skill is None:
            raise SkillNotFoundError(identifier)
        installation = await self._installation(db, skill.id)
        if installation is None:
            raise SkillNotFoundError(identifier)
        version = installation.draft_version if can_manage and installation.draft_version else installation.active_version
        if version is None or (not can_manage and version.status != SkillVersionStatus.READY):
            raise SkillNotFoundError(identifier)
        manifest = version.manifest or {}
        settings = installation.settings or {}
        compatibility = manifest.get("compatibility", {})
        grant_version_id = version.id if version.id == installation.active_version_id else installation.active_version_id
        grant = next(
            (
                item
                for item in installation.capability_grants
                if item.skill_version_id == grant_version_id and item.revoked_at is None
            ),
            None,
        )
        public_id = _public_skill_id(skill)
        return {
            "id": public_id,
            "skill_id": skill.id,
            "name": skill.canonical_name,
            "label": version.display_name,
            "description": version.description,
            "instructions": manifest.get("instructions", ""),
            "frontmatter": manifest.get("frontmatter", {}),
            "resources": [
                {**item, "executable": item.get("kind") == "script"}
                for item in manifest.get("resources", [])
                if item.get("path") != "SKILL.md"
            ],
            "tools": list(settings.get("tools", [])),
            "default": bool(settings.get("default", False)),
            "enabled": installation.status == SkillInstallationStatus.ENABLED,
            "visibility": settings.get("visibility", "public"),
            "order": int(settings.get("order", 100)),
            "always_on": bool(settings.get("always_on", False)),
            "routable": bool(settings.get("routable", True)),
            "routing_examples": settings.get("routing_examples", {}),
            "version": version.version_number,
            "version_id": version.id,
            "revision": int(installation.revision),
            "digest": version.package_digest,
            "status": version.status.value,
            "origin": {"type": version.source, "digest": version.package_digest},
            "compatibility": compatibility,
            "capability_grants": dict(grant.grants or {}) if grant is not None else {},
            "allowed_actions": [
                "view",
                *( ["edit", "publish", "configure", "rollback", "export", "archive"] if can_manage else [] ),
            ],
            "created_at": _timestamp(version.created_at),
            "updated_at": _timestamp(installation.updated_at),
        }

    async def refresh_registry(self, db: AsyncSession) -> SkillRegistrySnapshot:
        state_result = await db.execute(select(SkillRegistryState).where(SkillRegistryState.id == "global"))
        state = state_result.scalar_one_or_none()
        revision = int(state.revision) if state else 0
        statement = (
            select(SkillInstallation)
            .join(Skill, Skill.id == SkillInstallation.skill_id)
            .where(
                Skill.status == SkillLifecycleStatus.ACTIVE,
                SkillInstallation.active_version_id.is_not(None),
                SkillInstallation.scope_type == SYSTEM_SCOPE_TYPE,
                SkillInstallation.scope_key == SYSTEM_SCOPE_KEY,
            )
            .options(
                selectinload(SkillInstallation.skill).selectinload(Skill.aliases),
                selectinload(SkillInstallation.active_version),
                selectinload(SkillInstallation.capability_grants),
            )
            .execution_options(populate_existing=True)
        )
        result = await db.execute(statement)
        installations = result.scalars().unique().all()
        runtime_skills: list[RuntimeSkill] = []
        failures: list[str] = []
        for installation in installations:
            version = installation.active_version
            if version is None or version.status != SkillVersionStatus.READY:
                continue
            try:
                package = self.storage.load_archive(
                    version.storage_key,
                    expected_digest=version.package_digest,
                ).package
                if package.metadata.name != version.name:
                    raise SkillPackageError("metadata_changed", "stored name does not match version metadata")
                if package.metadata.description != version.description:
                    raise SkillPackageError("metadata_changed", "stored description does not match version metadata")
                manifest = _manifest(package)
                persisted_manifest = dict(version.manifest or {})
                persisted_manifest.pop("version_note", None)
                if _json_value(persisted_manifest) != manifest:
                    raise SkillPackageError("manifest_changed", "stored package manifest does not match version metadata")
                requested_capabilities = _requested_capabilities(package)
                if _json_value(version.requested_capabilities or {}) != requested_capabilities:
                    raise SkillPackageError(
                        "capabilities_changed",
                        "stored package capabilities do not match version metadata",
                    )
                compatibility = manifest.get("compatibility", {})
                ordered_aliases = _sorted_skill_aliases(installation.skill)
                aliases = tuple(alias.alias_name for alias in ordered_aliases)
                public_id = _public_skill_id(installation.skill)
                settings = installation.settings or {}
                grant = next(
                    (
                        item
                        for item in installation.capability_grants
                        if item.skill_version_id == version.id and item.revoked_at is None
                    ),
                    None,
                )
                effective_grants = dict(grant.grants or {}) if grant is not None else {
                    "tools": [],
                    "resources": {"read": []},
                    "scripts": [],
                    "network": [],
                    "secrets": [],
                }
                readable_resources = set(
                    (effective_grants.get("resources") or {}).get("read", [])
                )
                runtime_skills.append(
                    RuntimeSkill(
                        id=public_id,
                        stable_id=installation.skill.id,
                        canonical_name=installation.skill.canonical_name,
                        aliases=aliases,
                        label=version.display_name,
                        description=package.metadata.description,
                        tool_ids=tuple(effective_grants.get("tools", [])),
                        instructions=manifest.get("instructions", ""),
                        resources=tuple(
                            RuntimeSkillResource(
                                path=item["path"],
                                kind=item["kind"],
                                size=int(item["size"]),
                                sha256=item["sha256"],
                            )
                            for item in manifest.get("resources", [])
                            if item.get("path") in readable_resources
                        ),
                        storage_key=version.storage_key,
                        version_id=version.id,
                        version_number=version.version_number,
                        digest=version.package_digest,
                        installation_revision=int(installation.revision),
                        is_default=bool(settings.get("default", False)),
                        enabled=installation.status == SkillInstallationStatus.ENABLED,
                        order=int(settings.get("order", 100)),
                        visibility=settings.get("visibility", "public"),
                        always_on=bool(settings.get("always_on", False)),
                        routable=bool(settings.get("routable", True)),
                        routing_examples=_routing_examples(settings),
                        compatibility_level=compatibility.get("level", "A"),
                        format_compatible=bool(compatibility.get("format_compatible", True)),
                        runtime_ready=bool(compatibility.get("runtime_ready", False)),
                        compatibility_reasons=tuple(compatibility.get("reasons", [])),
                        effective_grants=effective_grants,
                        origin={"type": version.source, "digest": version.package_digest},
                        created_at=_timestamp(version.created_at),
                        updated_at=_timestamp(installation.updated_at),
                    )
                )
            except Exception as exc:
                failures.append(f"{installation.skill_id}: {exc}")
                logger.exception(
                    "Quarantined invalid Skill registry entry for skill_id=%s revision=%s",
                    installation.skill_id,
                    revision,
                )
        if failures:
            logger.error(
                "Publishing Skill registry revision %s with %s quarantined package(s): %s",
                revision,
                len(failures),
                "; ".join(failures),
            )
        runtime_skills.sort(key=lambda item: (item.order, item.id))
        if failures:
            # A package validation/storage failure must never leave a partially
            # trusted runtime catalog. Publish an empty, explicitly degraded
            # snapshot at the DB revision so all runtime lookups fail closed.
            failure_identity = hashlib.sha256(
                "\n".join(sorted(failures)).encode("utf-8")
            ).hexdigest()
            snapshot = SkillRegistrySnapshot(
                revision=revision,
                skills=(),
                degraded=True,
                failure_identity=failure_identity,
            )
        else:
            snapshot = SkillRegistrySnapshot(revision=revision, skills=tuple(runtime_skills))
        if not self.registry.publish(snapshot):
            raise SkillRegistryStaleError(
                f"Skill registry refused revision {revision}; current revision is {self.registry.revision}"
            )
        return self.registry.snapshot

    async def registry_revision(self, db: AsyncSession) -> int:
        result = await db.execute(
            select(SkillRegistryState.revision).where(SkillRegistryState.id == "global")
        )
        value = result.scalar_one_or_none()
        return int(value or 0)

    async def reconcile_registry(self, db: AsyncSession, *, force: bool = False) -> SkillRegistrySnapshot:
        target_revision = await self.registry_revision(db)
        if force or self.registry.revision != target_revision or self.registry.snapshot.degraded:
            snapshot = await self.refresh_registry(db)
        else:
            snapshot = self.registry.snapshot
        if snapshot.revision != target_revision:
            raise SkillRegistryStaleError(
                f"Skill registry is stale at revision {snapshot.revision}; database requires {target_revision}"
            )
        return snapshot

    async def consume_registry_events(self, db: AsyncSession) -> SkillRegistrySnapshot:
        """Reconcile one process and acknowledge outbox events after publication."""

        snapshot = await self.reconcile_registry(db)
        await db.execute(
            update(SkillRegistryEvent)
            .where(
                SkillRegistryEvent.processed_at.is_(None),
                SkillRegistryEvent.revision <= snapshot.revision,
            )
            .values(processed_at=_now())
        )
        await db.commit()
        return snapshot

    async def catalog(self, db: AsyncSession, *, can_manage: bool, tools: list[dict[str, Any]]) -> dict[str, Any]:
        await self.reconcile_registry(db)
        if not can_manage:
            return self.registry.public_catalog(tools)

        statement = (
            select(SkillInstallation)
            .join(Skill, Skill.id == SkillInstallation.skill_id)
            .where(
                Skill.status == SkillLifecycleStatus.ACTIVE,
                SkillInstallation.scope_type == SYSTEM_SCOPE_TYPE,
                SkillInstallation.scope_key == SYSTEM_SCOPE_KEY,
            )
            .options(
                selectinload(SkillInstallation.skill).selectinload(Skill.aliases),
                selectinload(SkillInstallation.active_version),
                selectinload(SkillInstallation.draft_version),
            )
            .execution_options(populate_existing=True)
        )
        result = await db.execute(statement)
        installations = result.scalars().unique().all()
        managed_skills: list[dict[str, Any]] = []
        for installation in installations:
            version = installation.draft_version or installation.active_version
            if version is None:
                continue
            settings = installation.settings or {}
            public_id = _public_skill_id(installation.skill)
            compatibility = (version.manifest or {}).get("compatibility", {})
            managed_skills.append(
                {
                    "id": public_id,
                    "skill_id": installation.skill.id,
                    "name": installation.skill.canonical_name,
                    "label": version.display_name,
                    "description": version.description,
                    "tool_ids": list(settings.get("tools", [])),
                    "is_default": bool(settings.get("default", False)),
                    "enabled": installation.status == SkillInstallationStatus.ENABLED,
                    "visibility": settings.get("visibility", "public"),
                    "order": int(settings.get("order", 100)),
                    "always_on": bool(settings.get("always_on", False)),
                    "routable": bool(settings.get("routable", True)),
                    "routing_examples": settings.get("routing_examples", {}),
                    "version": version.version_number,
                    "revision": int(installation.revision),
                    "digest": version.package_digest,
                    "status": version.status.value,
                    "origin": {"type": version.source, "digest": version.package_digest},
                    "compatibility": compatibility,
                    "updated_at": _timestamp(installation.updated_at),
                }
            )
        managed_skills.sort(key=lambda item: (item["order"], item["id"]))

        catalog = self.registry.public_catalog(tools)
        catalog["skills"] = managed_skills
        catalog["allowed_actions"] = ["view", "create", "import", "manage"]
        return catalog


skill_service = SkillService()
