from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.e2.common import (
    ascii_text,
    canonical_uuid,
    digest,
    digest_bytes,
    generated_or_canonical_uuid,
    versioned_json,
)
from app.e2.errors import E2PrimitiveConflictError, E2PrimitiveValidationError
from app.models.projection_domain import SkillPackage, SkillPackageUpload

MAX_ARCHIVE_BYTES = 64 * 1024 * 1024


class SyntheticSkillRepository:
    """SQL-only package/upload facts for synthetic E2 fixtures."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def store_package(
        self,
        *,
        archive: bytes,
        package_digest: str,
        manifest: dict[str, object],
        manifest_schema_version: int,
        created_by: str | None = None,
        package_id: str | None = None,
        canonical_archive_digest: str | None = None,
    ) -> SkillPackage:
        if not isinstance(archive, bytes):
            raise E2PrimitiveValidationError("archive must be bytes")
        if not archive or len(archive) > MAX_ARCHIVE_BYTES:
            raise E2PrimitiveValidationError("archive must be non-empty and at most 64 MiB")
        package_digest = digest(package_digest, "package_digest")
        expected_archive_digest = digest_bytes(archive)
        canonical_archive_digest = canonical_archive_digest or expected_archive_digest
        canonical_archive_digest = digest(canonical_archive_digest, "canonical_archive_digest")
        if canonical_archive_digest != expected_archive_digest:
            raise E2PrimitiveValidationError("canonical_archive_digest does not match archive bytes")
        normalized_manifest = versioned_json(manifest, manifest_schema_version, "manifest_json", 256 * 1024)
        if created_by is not None:
            created_by = ascii_text(created_by, "created_by", 64)
        existing = await self.session.scalar(select(SkillPackage).where(SkillPackage.package_digest == package_digest))
        if existing is not None:
            if existing.canonical_archive_digest != canonical_archive_digest or existing.manifest_json != normalized_manifest:
                raise E2PrimitiveConflictError("synthetic Skill package digest conflicts with an immutable package")
            return existing
        existing_archive = await self.session.scalar(
            select(SkillPackage).where(SkillPackage.canonical_archive_digest == canonical_archive_digest)
        )
        if existing_archive is not None:
            raise E2PrimitiveConflictError("synthetic canonical archive digest already belongs to another package")
        package = SkillPackage(
            id=generated_or_canonical_uuid(package_id, "package_id"),
            package_digest=package_digest,
            canonical_archive_digest=canonical_archive_digest,
            canonical_size_bytes=len(archive),
            canonical_archive=archive,
            manifest_json=normalized_manifest,
            manifest_schema_version=manifest_schema_version,
            created_by=created_by,
        )
        self.session.add(package)
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except IntegrityError as exc:
            raise E2PrimitiveConflictError("synthetic Skill package uniqueness constraint rejected the insert") from exc
        return package

    async def record_upload(
        self,
        *,
        package_id: str,
        raw_archive: bytes,
        uploaded_by: str | None = None,
        request_archive_digest: str | None = None,
        upload_id: str | None = None,
    ) -> SkillPackageUpload:
        package_id = canonical_uuid(package_id, "package_id")
        if not isinstance(raw_archive, bytes):
            raise E2PrimitiveValidationError("raw_archive must be bytes")
        if not raw_archive or len(raw_archive) > MAX_ARCHIVE_BYTES:
            raise E2PrimitiveValidationError("raw_archive must be non-empty and at most 64 MiB")
        expected_digest = digest_bytes(raw_archive)
        request_archive_digest = digest(request_archive_digest or expected_digest, "request_archive_digest")
        if request_archive_digest != expected_digest:
            raise E2PrimitiveValidationError("request_archive_digest does not match raw_archive bytes")
        if uploaded_by is not None:
            uploaded_by = ascii_text(uploaded_by, "uploaded_by", 64)
        if await self.session.get(SkillPackage, package_id) is None:
            raise E2PrimitiveValidationError("skill package does not exist")
        existing = await self.session.scalar(
            select(SkillPackageUpload).where(SkillPackageUpload.request_archive_digest == request_archive_digest)
        )
        if existing is not None:
            if existing.package_id != package_id:
                raise E2PrimitiveConflictError("request archive digest belongs to another package")
            return existing
        upload = SkillPackageUpload(
            id=generated_or_canonical_uuid(upload_id, "upload_id"),
            package_id=package_id,
            request_archive_digest=request_archive_digest,
            original_size_bytes=len(raw_archive),
            raw_archive=raw_archive,
            uploaded_by=uploaded_by,
        )
        self.session.add(upload)
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except IntegrityError as exc:
            raise E2PrimitiveConflictError("synthetic Skill upload uniqueness constraint rejected the insert") from exc
        return upload
