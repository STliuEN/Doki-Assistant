"""Production SQL authority for immutable Skill archives; never reads host files."""

import hashlib
import io
import unicodedata
import zipfile
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.projection_domain import SkillPackage as PackageRow
from app.models.projection_domain import SkillPackageUpload
from app.skills.package import DEFAULT_SKILL_PACKAGE_LIMITS, SkillPackageError, parse_skill_zip
from app.skills.storage import SkillPackageStorage, StoredSkillPackage, build_skill_archive, package_digest


class SqlSkillPackageStorage:
    def __init__(self, session, *, actor_id=None, source_kind="upload"):
        self.session = session
        self.actor_id = actor_id
        self.source_kind = source_kind

    async def _insert_once(self, row, model, identity):
        existing = await self.session.scalar(select(model).where(model.id == identity).with_for_update())
        if existing is not None:
            return existing
        try:
            async with self.session.begin_nested():
                self.session.add(row)
                await self.session.flush()
        except IntegrityError:
            existing = await self.session.scalar(select(model).where(model.id == identity).with_for_update())
            if existing is None:
                raise
            return existing
        return row

    async def store_raw(self, raw: bytes, *, package_id=None):
        if len(raw) > DEFAULT_SKILL_PACKAGE_LIMITS.max_archive_bytes:
            raise SkillPackageError("archive_size", "ZIP archive exceeds the package limit")
        digest = hashlib.sha256(raw).hexdigest()
        identity = str(uuid5(NAMESPACE_URL, "doki:skill-upload:" + digest))
        row = await self._insert_once(SkillPackageUpload(
            id=identity, package_id=package_id, request_archive_digest=digest,
            original_size_bytes=len(raw), raw_archive=raw, uploaded_by=self.actor_id,
            source_kind=self.source_kind,
        ), SkillPackageUpload, identity)
        if bytes(row.raw_archive) != raw or row.original_size_bytes != len(raw):
            raise SkillPackageError("storage_digest_mismatch", "Stored upload bytes drifted")
        return row

    async def store_archive(self, archive_bytes: bytes) -> StoredSkillPackage:
        from app.skills.service import _manifest

        package = parse_skill_zip(archive_bytes)
        digest = package_digest(package)
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            members = {unicodedata.normalize("NFC", info.filename): info for info in archive.infolist() if not info.is_dir()}
            canonical = build_skill_archive({item.path: archive.read(members[item.path]) for item in package.resource_manifest})
        canonical_package = parse_skill_zip(canonical)
        if package_digest(canonical_package) != digest:
            raise SkillPackageError("digest_mismatch", "Canonicalization changed package contents")
        identity = str(uuid5(NAMESPACE_URL, "doki:skill-package:" + digest))
        row = await self._insert_once(PackageRow(
            id=identity, package_digest=digest, canonical_archive_digest=hashlib.sha256(canonical).hexdigest(),
            canonical_size_bytes=len(canonical), canonical_archive=canonical,
            manifest_json=_manifest(canonical_package), manifest_schema_version=1, created_by=self.actor_id,
        ), PackageRow, identity)
        self._verify(row, digest)
        upload = await self.store_raw(archive_bytes, package_id=row.id)
        return StoredSkillPackage(canonical_package, digest, f"objects/{digest[:2]}/{digest}.zip", len(canonical), row.id, upload.id)

    @staticmethod
    def _verify(row, digest):
        from app.skills.service import _manifest

        if row is None:
            raise SkillPackageError("storage_missing", "SQL Skill package is missing")
        content = bytes(row.canonical_archive)
        if (row.package_digest != digest or len(content) != row.canonical_size_bytes
                or hashlib.sha256(content).hexdigest() != row.canonical_archive_digest):
            raise SkillPackageError("storage_digest_mismatch", "SQL Skill archive digest or length changed")
        package = parse_skill_zip(content)
        if package_digest(package) != digest or row.manifest_json != _manifest(package) or row.manifest_schema_version != 1:
            raise SkillPackageError("manifest_changed", "SQL Skill content or resource manifest changed")
        return package

    async def _read(self, storage_key, expected_digest):
        key_digest = SkillPackageStorage._key_digest(storage_key)
        if key_digest != expected_digest:
            raise SkillPackageError("storage_digest_mismatch", "Expected Skill version does not match storage identity")
        row = await self.session.scalar(select(PackageRow).where(PackageRow.package_digest == key_digest).execution_options(populate_existing=True))
        package = self._verify(row, key_digest)
        return row, package

    async def load_archive(self, storage_key, *, expected_digest):
        row, package = await self._read(storage_key, expected_digest)
        return StoredSkillPackage(package, row.package_digest, storage_key, row.canonical_size_bytes, row.id)

    async def read_archive(self, storage_key, *, expected_digest):
        row, _ = await self._read(storage_key, expected_digest)
        return bytes(row.canonical_archive)

    async def read_resource(self, storage_key, resource_path, *, max_bytes, expected_digest):
        row, package = await self._read(storage_key, expected_digest)
        resource = next((item for item in package.resource_manifest if item.path == resource_path), None)
        if resource is None:
            raise SkillPackageError("resource_missing", "Resource not present in immutable package")
        if resource.size > max_bytes:
            raise SkillPackageError("resource_size", "Resource exceeds read limit")
        with zipfile.ZipFile(io.BytesIO(row.canonical_archive)) as archive:
            content = archive.read(resource.path)
        if hashlib.sha256(content).hexdigest() != resource.sha256:
            raise SkillPackageError("storage_digest_mismatch", "Resource content drifted")
        return content
