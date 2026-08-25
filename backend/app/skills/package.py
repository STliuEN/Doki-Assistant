"""Read and validate portable Skill packages without executing their code."""

from __future__ import annotations

import hashlib
import io
import math
import os
import re
import stat
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, BinaryIO, Literal, Mapping

import yaml

_SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_DRIVE_PATH_PATTERN = re.compile(r"^[a-zA-Z]:")
_WINDOWS_DEVICE_NAMES = {
    "aux",
    "clock$",
    "con",
    "nul",
    "prn",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}
_CHUNK_SIZE = 64 * 1024
MAX_SKILL_INSTRUCTIONS_BYTES = 64 * 1024
# Compatibility alias for callers that imported the original constant name.
MAX_SKILL_INSTRUCTIONS_CHARS = MAX_SKILL_INSTRUCTIONS_BYTES
MAX_SKILL_MARKDOWN_BYTES = 256 * 1024
MAX_SKILL_FRONTMATTER_BYTES = 64 * 1024
MAX_SKILL_FRONTMATTER_NODES = 4096
MAX_SKILL_FRONTMATTER_DEPTH = 64


class SkillPackageError(ValueError):
    """A deterministic validation failure suitable for an API error response."""

    def __init__(self, code: str, detail: str, *, path: str | None = None) -> None:
        self.code = code
        self.detail = detail
        self.path = path
        location = f" ({path})" if path else ""
        super().__init__(f"{code}{location}: {detail}")


@dataclass(frozen=True, slots=True)
class SkillPackageLimits:
    """Resource limits applied before a package is accepted."""

    max_entries: int = 512
    max_files: int = 256
    max_single_file_bytes: int = 8 * 1024 * 1024
    max_total_uncompressed_bytes: int = 32 * 1024 * 1024
    max_archive_bytes: int = 64 * 1024 * 1024
    max_compression_ratio: float = 200.0
    max_path_length: int = 512
    max_path_depth: int = 24
    max_segment_length: int = 255

    def __post_init__(self) -> None:
        integer_fields = (
            "max_entries",
            "max_files",
            "max_single_file_bytes",
            "max_total_uncompressed_bytes",
            "max_archive_bytes",
            "max_path_length",
            "max_path_depth",
            "max_segment_length",
        )
        if any(getattr(self, field_name) <= 0 for field_name in integer_fields):
            raise ValueError("Skill package limits must be positive")
        if self.max_compression_ratio <= 0:
            raise ValueError("max_compression_ratio must be positive")


DEFAULT_SKILL_PACKAGE_LIMITS = SkillPackageLimits()


@dataclass(frozen=True, slots=True)
class SkillMetadata:
    name: str
    description: str
    frontmatter: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class SkillResource:
    path: str
    kind: Literal["instructions", "script", "reference", "asset", "resource"]
    size: int
    sha256: str
    compressed_size: int | None = None


@dataclass(frozen=True, slots=True)
class SkillPackage:
    source: str
    package_type: Literal["directory", "zip"]
    metadata: SkillMetadata
    instructions: str
    resource_manifest: tuple[SkillResource, ...]
    total_uncompressed_bytes: int

    @property
    def resources(self) -> tuple[SkillResource, ...]:
        """A concise alias for callers that do not need the manifest wording."""

        return self.resource_manifest


@dataclass(frozen=True, slots=True)
class _DirectoryFile:
    path: Path
    relative_path: str
    initial_stat: os.stat_result


@dataclass(frozen=True, slots=True)
class _ReadResult:
    size: int
    sha256: str
    content: bytes | None


class _FrontmatterLoader(yaml.SafeLoader):
    """SafeLoader variant that rejects aliases and duplicate mapping keys."""

    def __init__(self, stream: Any) -> None:
        super().__init__(stream)
        self._skill_node_count = 0
        self._skill_node_depth = 0

    def compose_node(self, parent: Any, index: Any) -> Any:
        if self.check_event(yaml.AliasEvent):
            raise SkillPackageError("frontmatter_alias", "YAML aliases are not allowed")
        self._skill_node_count += 1
        self._skill_node_depth += 1
        try:
            if (
                self._skill_node_count > MAX_SKILL_FRONTMATTER_NODES
                or self._skill_node_depth > MAX_SKILL_FRONTMATTER_DEPTH
            ):
                raise SkillPackageError(
                    "frontmatter_complexity",
                    "YAML frontmatter exceeds the node or nesting-depth limit",
                )
            return super().compose_node(parent, index)
        finally:
            self._skill_node_depth -= 1


def _construct_unique_mapping(loader: _FrontmatterLoader, node: yaml.MappingNode, deep: bool = False) -> dict[str, Any]:
    loader.flatten_mapping(node)
    result: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise SkillPackageError("frontmatter_key", "YAML mapping keys must be strings")
        if key in result:
            raise SkillPackageError("frontmatter_duplicate_key", f"duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_FrontmatterLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set | frozenset):
        return frozenset(_freeze(item) for item in value)
    return value


def _validate_json_value(value: Any, *, path: str = "frontmatter") -> None:
    if value is None or isinstance(value, str | bool | int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SkillPackageError(
                "frontmatter_json_number",
                "YAML numeric values must be finite JSON numbers",
                path=path,
            )
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _validate_json_value(item, path=f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, path=f"{path}[{index}]")
        return
    raise SkillPackageError(
        "frontmatter_json_type",
        f"YAML value type {type(value).__name__} is not JSON-compatible",
        path=path,
    )


def parse_skill_markdown(content: bytes | str) -> tuple[SkillMetadata, str]:
    """Parse the required YAML frontmatter and return metadata plus Markdown body."""

    if isinstance(content, bytes):
        if len(content) > MAX_SKILL_MARKDOWN_BYTES:
            raise SkillPackageError("skill_markdown_size", "SKILL.md exceeds the 256 KiB byte limit")
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise SkillPackageError("skill_markdown_encoding", "SKILL.md must be UTF-8") from exc
    elif isinstance(content, str):
        if len(content.encode("utf-8")) > MAX_SKILL_MARKDOWN_BYTES:
            raise SkillPackageError("skill_markdown_size", "SKILL.md exceeds the 256 KiB byte limit")
        text = content.removeprefix("\ufeff")
    else:
        raise TypeError("content must be bytes or str")

    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        raise SkillPackageError("frontmatter_missing", "SKILL.md must start with YAML frontmatter")

    closing_index: int | None = None
    for index, line in enumerate(lines[1:], start=1):
        if line.rstrip("\r\n") == "---":
            closing_index = index
            break
    if closing_index is None:
        raise SkillPackageError("frontmatter_unclosed", "SKILL.md YAML frontmatter is not closed")

    raw_frontmatter = "".join(lines[1:closing_index])
    if len(raw_frontmatter.encode("utf-8")) > MAX_SKILL_FRONTMATTER_BYTES:
        raise SkillPackageError("frontmatter_complexity", "YAML frontmatter exceeds the 64 KiB byte limit")
    try:
        parsed = yaml.load(raw_frontmatter, Loader=_FrontmatterLoader)
    except SkillPackageError:
        raise
    except (RecursionError, OverflowError) as exc:
        raise SkillPackageError("frontmatter_complexity", "YAML frontmatter is too deeply nested") from exc
    except yaml.YAMLError as exc:
        raise SkillPackageError("frontmatter_invalid", f"invalid YAML frontmatter: {exc}") from exc
    if not isinstance(parsed, dict):
        raise SkillPackageError("frontmatter_type", "SKILL.md frontmatter must be a mapping")
    _validate_json_value(parsed)

    name = parsed.get("name")
    description = parsed.get("description")
    if not isinstance(name, str) or not name.strip():
        raise SkillPackageError("frontmatter_name", "frontmatter requires a non-empty string name")
    name = name.strip()
    if len(name) > 64 or not _SKILL_NAME_PATTERN.fullmatch(name):
        raise SkillPackageError(
            "frontmatter_name",
            "name must contain lowercase letters, numbers, and single hyphens only (maximum 64 characters)",
        )
    if not isinstance(description, str) or not description.strip():
        raise SkillPackageError("frontmatter_description", "frontmatter requires a non-empty string description")
    description = description.strip()
    if len(description) > 1024:
        raise SkillPackageError("frontmatter_description", "description must not exceed 1024 characters")

    immutable_frontmatter = _freeze(parsed)
    body = "".join(lines[closing_index + 1 :])
    if len(body.encode("utf-8")) > MAX_SKILL_INSTRUCTIONS_BYTES:
        raise SkillPackageError(
            "skill_instructions_size",
            "Skill instructions exceed the 64 KiB UTF-8 byte limit",
        )
    return SkillMetadata(name=name, description=description, frontmatter=immutable_frontmatter), body


class _PathRegistry:
    """Detect collisions that would alias on common case-insensitive filesystems."""

    def __init__(self, limits: SkillPackageLimits) -> None:
        self._limits = limits
        self._identity: dict[str, tuple[str, str]] = {}
        self._kind: dict[str, Literal["file", "directory"]] = {}
        self._explicit: set[str] = set()

    def add(self, raw_path: str, *, is_directory: bool) -> str:
        segments, normalized_segments = _validate_relative_path(raw_path, self._limits)
        for index in range(1, len(segments) + 1):
            raw_prefix = "/".join(segments[:index])
            normalized_prefix = "/".join(normalized_segments[:index])
            collision_key = normalized_prefix.casefold()
            expected_kind: Literal["file", "directory"] = (
                "directory" if index < len(segments) or is_directory else "file"
            )

            previous_identity = self._identity.get(collision_key)
            if previous_identity is not None and previous_identity[0] != raw_prefix:
                collision_type = (
                    "Unicode normalization"
                    if previous_identity[1] == normalized_prefix
                    else "case-insensitive"
                )
                raise SkillPackageError(
                    "path_collision",
                    f"{collision_type} path collision with {previous_identity[0]}",
                    path=raw_path,
                )

            previous_kind = self._kind.get(collision_key)
            if previous_kind is not None and previous_kind != expected_kind:
                raise SkillPackageError(
                    "path_type_collision",
                    "the same path is used as both a file and directory",
                    path=raw_path,
                )
            self._identity.setdefault(collision_key, (raw_prefix, normalized_prefix))
            self._kind.setdefault(collision_key, expected_kind)

            is_final = index == len(segments)
            if is_final:
                if collision_key in self._explicit:
                    raise SkillPackageError("path_duplicate", "duplicate package entry", path=raw_path)
                self._explicit.add(collision_key)

        return "/".join(normalized_segments)


def _validate_relative_path(raw_path: str, limits: SkillPackageLimits) -> tuple[list[str], list[str]]:
    if not isinstance(raw_path, str) or not raw_path:
        raise SkillPackageError("path_empty", "package entries must have a non-empty path")
    if "\x00" in raw_path or any(ord(character) < 32 for character in raw_path):
        raise SkillPackageError("path_control_character", "path contains a control character", path=raw_path)
    if "\\" in raw_path:
        raise SkillPackageError("path_separator", "backslashes and UNC paths are not allowed", path=raw_path)
    if raw_path.startswith("/") or raw_path.startswith("//") or _DRIVE_PATH_PATTERN.match(raw_path):
        raise SkillPackageError("path_absolute", "absolute, drive, and UNC paths are not allowed", path=raw_path)

    entry_path = raw_path[:-1] if raw_path.endswith("/") else raw_path
    if not entry_path:
        raise SkillPackageError("path_empty", "the archive root is not a valid entry", path=raw_path)
    segments = entry_path.split("/")
    if len(segments) > limits.max_path_depth:
        raise SkillPackageError("path_depth", "path depth exceeds the package limit", path=raw_path)
    if any(segment in {"", ".", ".."} for segment in segments):
        raise SkillPackageError("path_traversal", "empty, dot, and parent path segments are not allowed", path=raw_path)

    normalized_segments: list[str] = []
    for segment in segments:
        normalized = unicodedata.normalize("NFC", segment)
        if len(normalized) > limits.max_segment_length:
            raise SkillPackageError("path_segment_length", "path segment exceeds the package limit", path=raw_path)
        if ":" in normalized:
            raise SkillPackageError("path_colon", "drive and alternate-stream path syntax is not allowed", path=raw_path)
        if normalized.endswith((" ", ".")):
            raise SkillPackageError("path_portability", "path segments may not end with a space or dot", path=raw_path)
        device_stem = normalized.rstrip(" .").split(".", 1)[0].casefold()
        if device_stem in _WINDOWS_DEVICE_NAMES:
            raise SkillPackageError("path_device", "reserved device names are not allowed", path=raw_path)
        normalized_segments.append(normalized)

    normalized_path = "/".join(normalized_segments)
    if len(normalized_path) > limits.max_path_length:
        raise SkillPackageError("path_length", "path exceeds the package limit", path=raw_path)
    return segments, normalized_segments


def _has_reparse_point(path: Path, file_stat: os.stat_result | None = None) -> bool:
    is_junction = getattr(os.path, "isjunction", None)
    if is_junction is not None and is_junction(path):
        return True
    attributes = getattr(file_stat, "st_file_attributes", 0) if file_stat is not None else 0
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(reparse_flag and attributes & reparse_flag)


def _validate_regular_stat(file_stat: os.stat_result, path: Path) -> None:
    if not stat.S_ISREG(file_stat.st_mode):
        raise SkillPackageError("special_file", "only regular files are allowed", path=str(path))
    if file_stat.st_nlink != 1:
        raise SkillPackageError("hardlink", "hard-linked files are not allowed", path=str(path))
    if _has_reparse_point(path, file_stat):
        raise SkillPackageError("symlink", "reparse points and links are not allowed", path=str(path))


def _same_file(left: os.stat_result, right: os.stat_result) -> bool:
    left_identity = (left.st_dev, left.st_ino)
    right_identity = (right.st_dev, right.st_ino)
    if left_identity == (0, 0) or right_identity == (0, 0):
        return True
    return left_identity == right_identity


def _read_stream(
    stream: BinaryIO,
    *,
    expected_size: int,
    max_bytes: int,
    collect: bool,
    path: str,
) -> _ReadResult:
    digest = hashlib.sha256()
    chunks: list[bytes] | None = [] if collect else None
    size = 0
    while True:
        chunk = stream.read(_CHUNK_SIZE)
        if not chunk:
            break
        size += len(chunk)
        if size > max_bytes:
            raise SkillPackageError("file_size", "file exceeds the package limit", path=path)
        digest.update(chunk)
        if chunks is not None:
            chunks.append(chunk)
    if size != expected_size:
        raise SkillPackageError("file_changed", "file size changed while the package was read", path=path)
    return _ReadResult(size=size, sha256=digest.hexdigest(), content=b"".join(chunks) if chunks is not None else None)


def _read_directory_file(record: _DirectoryFile, limits: SkillPackageLimits, *, collect: bool) -> _ReadResult:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(record.path, flags)
    except OSError as exc:
        raise SkillPackageError("file_open", f"could not safely open file: {exc}", path=record.relative_path) from exc

    try:
        opened_stat = os.fstat(descriptor)
        _validate_regular_stat(opened_stat, record.path)
        if not _same_file(record.initial_stat, opened_stat):
            raise SkillPackageError("file_changed", "file identity changed while the package was read", path=record.relative_path)
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = -1
            result = _read_stream(
                stream,
                expected_size=record.initial_stat.st_size,
                max_bytes=limits.max_single_file_bytes,
                collect=collect,
                path=record.relative_path,
            )
        final_stat = record.path.lstat()
        if not _same_file(record.initial_stat, final_stat) or final_stat.st_size != record.initial_stat.st_size:
            raise SkillPackageError("file_changed", "file changed while the package was read", path=record.relative_path)
        return result
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _read_source_archive(path: Path, limits: SkillPackageLimits) -> bytes:
    try:
        initial_stat = path.lstat()
    except OSError as exc:
        raise SkillPackageError("source_missing", f"could not stat archive: {exc}", path=str(path)) from exc
    if path.is_symlink() or _has_reparse_point(path, initial_stat):
        raise SkillPackageError("symlink", "the package archive may not be a link", path=str(path))
    _validate_regular_stat(initial_stat, path)
    if initial_stat.st_size > limits.max_archive_bytes:
        raise SkillPackageError("archive_size", "ZIP archive exceeds the package limit", path=str(path))
    record = _DirectoryFile(path=path, relative_path=path.name, initial_stat=initial_stat)
    archive_limits = SkillPackageLimits(
        max_entries=limits.max_entries,
        max_files=limits.max_files,
        max_single_file_bytes=limits.max_archive_bytes,
        max_total_uncompressed_bytes=limits.max_total_uncompressed_bytes,
        max_archive_bytes=limits.max_archive_bytes,
        max_compression_ratio=limits.max_compression_ratio,
        max_path_length=limits.max_path_length,
        max_path_depth=limits.max_path_depth,
        max_segment_length=limits.max_segment_length,
    )
    result = _read_directory_file(record, archive_limits, collect=True)
    assert result.content is not None
    return result.content


def _resource_kind(path: str) -> Literal["instructions", "script", "reference", "asset", "resource"]:
    if path == "SKILL.md":
        return "instructions"
    root = path.split("/", 1)[0].casefold()
    if root == "scripts":
        return "script"
    if root == "references":
        return "reference"
    if root == "assets":
        return "asset"
    return "resource"


def _build_package(
    *,
    source: Path,
    package_type: Literal["directory", "zip"],
    skill_markdown: bytes | None,
    resources: list[SkillResource],
    total_size: int,
) -> SkillPackage:
    if skill_markdown is None:
        raise SkillPackageError("skill_markdown_missing", "package root must contain SKILL.md")
    metadata, instructions = parse_skill_markdown(skill_markdown)
    manifest = tuple(sorted(resources, key=lambda item: (item.path.casefold(), item.path)))
    return SkillPackage(
        source=str(source.resolve()),
        package_type=package_type,
        metadata=metadata,
        instructions=instructions,
        resource_manifest=manifest,
        total_uncompressed_bytes=total_size,
    )


def parse_skill_directory(
    source: str | os.PathLike[str],
    *,
    limits: SkillPackageLimits = DEFAULT_SKILL_PACKAGE_LIMITS,
) -> SkillPackage:
    """Validate a directory-backed Skill package and return its immutable manifest."""

    root = Path(source)
    try:
        root_stat = root.lstat()
    except OSError as exc:
        raise SkillPackageError("source_missing", f"could not stat package directory: {exc}", path=str(root)) from exc
    if root.is_symlink() or _has_reparse_point(root, root_stat):
        raise SkillPackageError("symlink", "the package directory may not be a link", path=str(root))
    if not stat.S_ISDIR(root_stat.st_mode):
        raise SkillPackageError("source_type", "directory Skill source must be a directory", path=str(root))

    registry = _PathRegistry(limits)
    files: list[_DirectoryFile] = []
    entry_count = 0

    def scan(directory: Path, relative_parent: str = "") -> None:
        nonlocal entry_count
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as exc:
            raise SkillPackageError("directory_read", f"could not read package directory: {exc}", path=str(directory)) from exc
        for entry in entries:
            entry_count += 1
            if entry_count > limits.max_entries:
                raise SkillPackageError("entry_count", "package contains too many entries")
            raw_relative = f"{relative_parent}/{entry.name}" if relative_parent else entry.name
            entry_path = Path(entry.path)
            try:
                # DirEntry.stat() on some Windows/Python combinations omits
                # stable file identity and link-count fields. Path.lstat()
                # supplies the information needed for hard-link detection.
                entry_stat = entry_path.lstat()
            except OSError as exc:
                raise SkillPackageError("entry_stat", f"could not stat package entry: {exc}", path=raw_relative) from exc
            if entry.is_symlink() or _has_reparse_point(entry_path, entry_stat):
                raise SkillPackageError("symlink", "links and reparse points are not allowed", path=raw_relative)
            if stat.S_ISDIR(entry_stat.st_mode):
                normalized = registry.add(raw_relative, is_directory=True)
                scan(entry_path, normalized)
                continue
            normalized = registry.add(raw_relative, is_directory=False)
            _validate_regular_stat(entry_stat, entry_path)
            if entry_stat.st_size > limits.max_single_file_bytes:
                raise SkillPackageError("file_size", "file exceeds the package limit", path=normalized)
            files.append(_DirectoryFile(entry_path, normalized, entry_stat))
            if len(files) > limits.max_files:
                raise SkillPackageError("file_count", "package contains too many files")

    scan(root)
    declared_total = sum(record.initial_stat.st_size for record in files)
    if declared_total > limits.max_total_uncompressed_bytes:
        raise SkillPackageError("total_size", "package exceeds the total uncompressed size limit")

    resources: list[SkillResource] = []
    skill_markdown: bytes | None = None
    actual_total = 0
    for record in files:
        collect = record.relative_path == "SKILL.md"
        result = _read_directory_file(record, limits, collect=collect)
        actual_total += result.size
        if actual_total > limits.max_total_uncompressed_bytes:
            raise SkillPackageError("total_size", "package exceeds the total uncompressed size limit")
        resources.append(
            SkillResource(
                path=record.relative_path,
                kind=_resource_kind(record.relative_path),
                size=result.size,
                sha256=result.sha256,
            )
        )
        if collect:
            skill_markdown = result.content

    return _build_package(
        source=root,
        package_type="directory",
        skill_markdown=skill_markdown,
        resources=resources,
        total_size=actual_total,
    )


def _validate_zip_entry_type(info: zipfile.ZipInfo) -> None:
    unix_mode = (info.external_attr >> 16) & 0xFFFF
    file_type = stat.S_IFMT(unix_mode)
    if file_type == stat.S_IFLNK:
        raise SkillPackageError("symlink", "ZIP symlink entries are not allowed", path=info.filename)
    special_types = {stat.S_IFCHR, stat.S_IFBLK, stat.S_IFIFO, stat.S_IFSOCK}
    if file_type in special_types:
        raise SkillPackageError("special_file", "ZIP device and special-file entries are not allowed", path=info.filename)
    if info.is_dir() and file_type not in {0, stat.S_IFDIR}:
        raise SkillPackageError("entry_type", "ZIP directory has an invalid file type", path=info.filename)
    if not info.is_dir() and file_type not in {0, stat.S_IFREG}:
        raise SkillPackageError("entry_type", "ZIP entry is not a regular file", path=info.filename)


def parse_skill_zip(
    source: str | os.PathLike[str] | bytes,
    *,
    limits: SkillPackageLimits = DEFAULT_SKILL_PACKAGE_LIMITS,
) -> SkillPackage:
    """Validate a ZIP-backed Skill package in memory without extracting it."""

    if isinstance(source, bytes):
        if len(source) > limits.max_archive_bytes:
            raise SkillPackageError("archive_size", "ZIP archive exceeds the package limit")
        source_path = Path("<memory>")
        archive_bytes = source
    else:
        source_path = Path(source)
        archive_bytes = _read_source_archive(source_path, limits)
    registry = _PathRegistry(limits)
    resources: list[SkillResource] = []
    skill_markdown: bytes | None = None
    file_count = 0
    total_size = 0
    total_compressed_size = 0

    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except (OSError, zipfile.BadZipFile) as exc:
        raise SkillPackageError("zip_invalid", f"invalid ZIP archive: {exc}", path=str(source_path)) from exc

    with archive:
        infos = archive.infolist()
        if len(infos) > limits.max_entries:
            raise SkillPackageError("entry_count", "package contains too many ZIP entries")
        validated: list[tuple[zipfile.ZipInfo, str]] = []
        for info in infos:
            if info.flag_bits & 0x1:
                raise SkillPackageError("zip_encrypted", "encrypted ZIP entries are not allowed", path=info.filename)
            _validate_zip_entry_type(info)
            normalized = registry.add(info.filename, is_directory=info.is_dir())
            if info.is_dir():
                continue
            file_count += 1
            if file_count > limits.max_files:
                raise SkillPackageError("file_count", "package contains too many files")
            if info.file_size > limits.max_single_file_bytes:
                raise SkillPackageError("file_size", "file exceeds the package limit", path=normalized)
            total_size += info.file_size
            total_compressed_size += info.compress_size
            if total_size > limits.max_total_uncompressed_bytes:
                raise SkillPackageError("total_size", "package exceeds the total uncompressed size limit")
            ratio = info.file_size / max(info.compress_size, 1)
            if ratio > limits.max_compression_ratio:
                raise SkillPackageError("compression_ratio", "ZIP entry exceeds the compression-ratio limit", path=normalized)
            validated.append((info, normalized))

        aggregate_ratio = total_size / max(total_compressed_size, 1)
        if aggregate_ratio > limits.max_compression_ratio:
            raise SkillPackageError("compression_ratio", "ZIP archive exceeds the compression-ratio limit")

        actual_total = 0
        for info, normalized in validated:
            collect = normalized == "SKILL.md"
            try:
                with archive.open(info, "r") as stream:
                    result = _read_stream(
                        stream,
                        expected_size=info.file_size,
                        max_bytes=limits.max_single_file_bytes,
                        collect=collect,
                        path=normalized,
                    )
            except SkillPackageError:
                raise
            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                raise SkillPackageError("zip_read", f"could not read ZIP entry: {exc}", path=normalized) from exc
            actual_total += result.size
            if actual_total > limits.max_total_uncompressed_bytes:
                raise SkillPackageError("total_size", "package exceeds the total uncompressed size limit")
            resources.append(
                SkillResource(
                    path=normalized,
                    kind=_resource_kind(normalized),
                    size=result.size,
                    sha256=result.sha256,
                    compressed_size=info.compress_size,
                )
            )
            if collect:
                skill_markdown = result.content

    return _build_package(
        source=source_path,
        package_type="zip",
        skill_markdown=skill_markdown,
        resources=resources,
        total_size=total_size,
    )


def load_skill_package(
    source: str | os.PathLike[str],
    *,
    limits: SkillPackageLimits = DEFAULT_SKILL_PACKAGE_LIMITS,
) -> SkillPackage:
    """Load either a directory or ZIP package based on the source type."""

    source_path = Path(source)
    if source_path.is_dir() and not source_path.is_symlink():
        return parse_skill_directory(source_path, limits=limits)
    return parse_skill_zip(source_path, limits=limits)
