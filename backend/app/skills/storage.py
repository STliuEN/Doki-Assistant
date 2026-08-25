"""Content-addressed canonical storage for validated Skill packages."""

from __future__ import annotations

import hashlib
import io
import os
import re
import unicodedata
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from app.skills.package import (
    DEFAULT_SKILL_PACKAGE_LIMITS,
    SkillPackage,
    SkillPackageError,
    SkillPackageLimits,
    parse_skill_directory,
    parse_skill_zip,
)

_STORAGE_KEY_PATTERN = re.compile(r"^objects/(?P<prefix>[0-9a-f]{2})/(?P<digest>[0-9a-f]{64})\.zip$")
_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off", ""})


def default_skill_storage_root() -> Path:
    configured = os.getenv("SKILL_STORAGE_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "data" / "skill_packages"


def _environment_flag(name: str, *, default: bool = False) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    if raw in _TRUE_VALUES:
        return True
    if raw in _FALSE_VALUES:
        return False
    raise RuntimeError(f"{name} must be a boolean value")


def package_digest(package: SkillPackage) -> str:
    """Return a stable digest of normalized paths and file contents."""

    digest = hashlib.sha256()
    for resource in package.resource_manifest:
        digest.update(resource.path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(resource.size).encode("ascii"))
        digest.update(b"\0")
        digest.update(resource.sha256.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def render_skill_markdown(
    *,
    name: str,
    description: str,
    instructions: str,
    frontmatter: Mapping[str, Any] | None = None,
) -> bytes:
    """Render editor data as a portable SKILL.md without private settings."""

    metadata = dict(frontmatter or {})
    metadata["name"] = name.strip()
    metadata["description"] = description.strip()
    ordered = {
        "name": metadata.pop("name"),
        "description": metadata.pop("description"),
        **metadata,
    }
    header = yaml.safe_dump(
        ordered,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    ).rstrip()
    body = instructions.strip()
    return f"---\n{header}\n---\n\n{body}\n".encode("utf-8")


def build_skill_archive(files: Mapping[str, bytes]) -> bytes:
    """Build a deterministic archive; the validator remains the authority."""

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(files, key=lambda item: (unicodedata.normalize("NFC", item).casefold(), item)):
            value = files[path]
            if not isinstance(value, bytes):
                raise TypeError(f"Skill resource {path!r} must be bytes")
            info = zipfile.ZipInfo(path, date_time=_FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            archive.writestr(info, value)
    return buffer.getvalue()


@dataclass(frozen=True, slots=True)
class StoredSkillPackage:
    package: SkillPackage
    digest: str
    storage_key: str
    archive_size: int


class SkillPackageStorage:
    """Store immutable Skill archives outside Git using atomic finalization."""

    def __init__(
        self,
        root: str | os.PathLike[str] | None = None,
        *,
        limits: SkillPackageLimits = DEFAULT_SKILL_PACKAGE_LIMITS,
    ) -> None:
        self.root = Path(root).resolve() if root is not None else default_skill_storage_root()
        self.limits = limits

    def _ensure_directories(self) -> None:
        (self.root / "staging").mkdir(parents=True, exist_ok=True)
        (self.root / "objects").mkdir(parents=True, exist_ok=True)

    def _quarantine_path(self, digest: str) -> Path:
        """Return a unique path for an invalid object before replacement."""

        quarantine = self.root / "quarantine"
        quarantine.mkdir(parents=True, exist_ok=True)
        return quarantine / f"{digest}-{uuid.uuid4()}.zip"

    def check_health(self) -> bool:
        """Verify that the configured filesystem volume is writable and readable."""

        probe = self.root / "staging" / f"health-{uuid.uuid4()}.tmp"
        content = os.urandom(32)
        try:
            self._ensure_directories()
            with probe.open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            return probe.read_bytes() == content
        except OSError:
            return False
        finally:
            try:
                probe.unlink(missing_ok=True)
            except OSError:
                pass

    def _resolve_key(self, storage_key: str) -> Path:
        if not _STORAGE_KEY_PATTERN.fullmatch(storage_key):
            raise SkillPackageError("storage_key", "invalid Skill storage key")
        candidate = (self.root / storage_key).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise SkillPackageError("storage_key", "Skill storage key escapes storage root") from exc
        return candidate

    @staticmethod
    def _key_digest(storage_key: str) -> str:
        match = _STORAGE_KEY_PATTERN.fullmatch(storage_key)
        if match is None or match.group("prefix") != match.group("digest")[:2]:
            raise SkillPackageError("storage_key", "invalid Skill storage key")
        return match.group("digest")

    def _verified_archive(
        self,
        storage_key: str,
        *,
        expected_digest: str | None = None,
    ) -> tuple[bytes, SkillPackage, str]:
        key_digest = self._key_digest(storage_key)
        if expected_digest is not None:
            if not _DIGEST_PATTERN.fullmatch(expected_digest) or expected_digest != key_digest:
                raise SkillPackageError(
                    "storage_digest_mismatch",
                    "Skill version digest does not match its content-addressed storage key",
                )
        path = self._resolve_key(storage_key)
        try:
            archive_bytes = path.read_bytes()
        except FileNotFoundError as exc:
            raise SkillPackageError("storage_missing", "Skill package object is missing") from exc
        if len(archive_bytes) > self.limits.max_archive_bytes:
            raise SkillPackageError("storage_corrupt", "Skill package object exceeds the storage limit")
        package = parse_skill_zip(archive_bytes, limits=self.limits)
        actual_digest = package_digest(package)
        if actual_digest != key_digest:
            raise SkillPackageError(
                "storage_digest_mismatch",
                "Skill package contents do not match the content-addressed storage key",
            )
        return archive_bytes, package, actual_digest

    @staticmethod
    def _normalized_archive(path: Path, package: SkillPackage) -> bytes:
        expected_paths = {item.path for item in package.resource_manifest}
        source_by_normalized: dict[str, zipfile.ZipInfo] = {}
        with zipfile.ZipFile(path, "r") as source:
            for info in source.infolist():
                if info.is_dir():
                    continue
                normalized = unicodedata.normalize("NFC", info.filename)
                source_by_normalized[normalized] = info

            missing = expected_paths - source_by_normalized.keys()
            if missing:
                raise SkillPackageError(
                    "archive_changed",
                    f"validated archive entries disappeared: {', '.join(sorted(missing))}",
                )

            files: dict[str, bytes] = {}
            for resource in package.resource_manifest:
                content = source.read(source_by_normalized[resource.path])
                if len(content) != resource.size or hashlib.sha256(content).hexdigest() != resource.sha256:
                    raise SkillPackageError("archive_changed", "archive changed after validation", path=resource.path)
                files[resource.path] = content
        return build_skill_archive(files)

    def store_archive(self, archive_bytes: bytes) -> StoredSkillPackage:
        if not isinstance(archive_bytes, bytes):
            raise TypeError("archive_bytes must be bytes")
        if len(archive_bytes) > self.limits.max_archive_bytes:
            raise SkillPackageError("archive_size", "ZIP archive exceeds the package limit")

        self._ensure_directories()
        staging_path = self.root / "staging" / f"{uuid.uuid4()}.zip"
        try:
            with staging_path.open("xb") as stream:
                stream.write(archive_bytes)
                stream.flush()
                os.fsync(stream.fileno())

            package = parse_skill_zip(staging_path, limits=self.limits)
            digest = package_digest(package)
            normalized = self._normalized_archive(staging_path, package)
            normalized_path = self.root / "staging" / f"{uuid.uuid4()}.zip"
            try:
                with normalized_path.open("xb") as stream:
                    stream.write(normalized)
                    stream.flush()
                    os.fsync(stream.fileno())

                normalized_package = parse_skill_zip(normalized_path, limits=self.limits)
                if package_digest(normalized_package) != digest:
                    raise SkillPackageError("digest_mismatch", "normalization changed package contents")

                storage_key = f"objects/{digest[:2]}/{digest}.zip"
                final_path = self._resolve_key(storage_key)
                final_path.parent.mkdir(parents=True, exist_ok=True)
                if not final_path.exists():
                    try:
                        os.replace(normalized_path, final_path)
                    except OSError:
                        if not final_path.exists():
                            raise
                else:
                    # Content-addressed objects are immutable, but a damaged
                    # volume or manual tampering can leave the key occupied by
                    # invalid bytes. Preserve those bytes and atomically put
                    # the newly validated object in their place so a retry can
                    # self-heal the object without exposing a partial file.
                    try:
                        self._verified_archive(storage_key, expected_digest=digest)
                    except SkillPackageError:
                        quarantined_path = self._quarantine_path(digest)
                        try:
                            os.replace(final_path, quarantined_path)
                        except FileNotFoundError:
                            # Another writer finalized the object between the
                            # existence check and validation. Its object is
                            # authoritative; leave the candidate staged and
                            # let the normal load below verify it.
                            pass
                        else:
                            try:
                                os.replace(normalized_path, final_path)
                            except OSError:
                                # Best effort recovery if finalization fails
                                # after moving the old object out of the way.
                                if not final_path.exists() and quarantined_path.exists():
                                    os.replace(quarantined_path, final_path)
                                raise
                return self.load_archive(storage_key, expected_digest=digest)
            finally:
                normalized_path.unlink(missing_ok=True)
        finally:
            staging_path.unlink(missing_ok=True)

    def store_files(self, files: Mapping[str, bytes]) -> StoredSkillPackage:
        return self.store_archive(build_skill_archive(files))

    def store_directory(self, source: str | os.PathLike[str]) -> StoredSkillPackage:
        """Import a local directory through the same validator as uploaded packages."""

        root = Path(source).resolve()
        package = parse_skill_directory(root, limits=self.limits)
        files: dict[str, bytes] = {}
        for resource in package.resource_manifest:
            path = (root / Path(resource.path)).resolve()
            try:
                path.relative_to(root)
            except ValueError as exc:
                raise SkillPackageError("path_traversal", "resource escapes package root", path=resource.path) from exc
            content = path.read_bytes()
            if len(content) != resource.size or hashlib.sha256(content).hexdigest() != resource.sha256:
                raise SkillPackageError("file_changed", "resource changed after validation", path=resource.path)
            files[resource.path] = content
        return self.store_files(files)

    def load_archive(
        self,
        storage_key: str,
        *,
        expected_digest: str | None = None,
    ) -> StoredSkillPackage:
        archive_bytes, package, digest = self._verified_archive(
            storage_key,
            expected_digest=expected_digest,
        )
        return StoredSkillPackage(
            package=package,
            digest=digest,
            storage_key=storage_key,
            archive_size=len(archive_bytes),
        )

    def read_archive(self, storage_key: str, *, expected_digest: str | None = None) -> bytes:
        archive_bytes, _, _ = self._verified_archive(
            storage_key,
            expected_digest=expected_digest,
        )
        return archive_bytes

    def read_resource(
        self,
        storage_key: str,
        resource_path: str,
        *,
        max_bytes: int | None = None,
        expected_digest: str | None = None,
    ) -> bytes:
        archive_bytes = self.read_archive(storage_key, expected_digest=expected_digest)
        limit = max_bytes or self.limits.max_single_file_bytes
        try:
            with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as archive:
                matches = [
                    info
                    for info in archive.infolist()
                    if not info.is_dir() and unicodedata.normalize("NFC", info.filename) == resource_path
                ]
                if len(matches) != 1:
                    raise SkillPackageError("resource_missing", "Skill resource does not exist", path=resource_path)
                info = matches[0]
                if info.file_size > limit:
                    raise SkillPackageError("resource_size", "Skill resource exceeds the read limit", path=resource_path)
                content = archive.read(info)
        except zipfile.BadZipFile as exc:
            raise SkillPackageError("storage_corrupt", "Skill package object is corrupt") from exc
        if len(content) > limit:
            raise SkillPackageError("resource_size", "Skill resource exceeds the read limit", path=resource_path)
        return content


skill_package_storage = SkillPackageStorage()


def validate_skill_storage_configuration(
    environment: str,
    *,
    storage: SkillPackageStorage = skill_package_storage,
) -> None:
    """Fail fast when a durable shared filesystem contract is not explicit."""

    backend = os.getenv("SKILL_STORAGE_BACKEND", "filesystem").strip().lower()
    if backend != "filesystem":
        raise RuntimeError("SKILL_STORAGE_BACKEND currently supports only 'filesystem'")

    production = environment.strip().lower() in {"prod", "production"}
    multi_instance = _environment_flag("SKILL_MULTI_INSTANCE")
    if production or multi_instance:
        configured = os.getenv("SKILL_STORAGE_DIR", "").strip()
        if not configured:
            raise RuntimeError(
                "Production and multi-instance deployments require an explicit SKILL_STORAGE_DIR shared durable volume"
            )
        if not Path(configured).expanduser().is_absolute():
            raise RuntimeError("SKILL_STORAGE_DIR must be an absolute path")
        if Path(configured).expanduser().resolve() != storage.root:
            raise RuntimeError("Skill storage was initialized with a different root than SKILL_STORAGE_DIR")
        if not _environment_flag("SKILL_STORAGE_SHARED"):
            raise RuntimeError(
                "Set SKILL_STORAGE_SHARED=true only after SKILL_STORAGE_DIR is mounted as a shared durable volume"
            )

    if not storage.check_health():
        raise RuntimeError("SKILL_STORAGE_DIR failed its writable/readable filesystem health check")
