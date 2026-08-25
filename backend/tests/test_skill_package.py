from __future__ import annotations

import os
import stat
import unicodedata
import warnings
import zipfile
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from app.skills.package import (
    SkillPackageError,
    SkillPackageLimits,
    load_skill_package,
    parse_skill_directory,
    parse_skill_markdown,
    parse_skill_zip,
)

SKILL_MD = """---
name: demo-skill
description: A portable test Skill.
license: MIT
metadata:
  owner: test
tags:
  - portable
---
# Demo

Read references before using scripts.
"""


def _write_directory_package(root: Path) -> Path:
    root.mkdir()
    (root / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
    (root / "references").mkdir()
    (root / "references" / "guide.md").write_text("guide", encoding="utf-8")
    (root / "scripts").mkdir()
    (root / "scripts" / "run.py").write_text("raise RuntimeError('must not execute')\n", encoding="utf-8")
    (root / "assets").mkdir()
    (root / "assets" / "sample.bin").write_bytes(b"asset")
    return root


def _write_zip(path: Path, entries: list[tuple[str, bytes]], *, compression: int = zipfile.ZIP_STORED) -> Path:
    with zipfile.ZipFile(path, "w", compression=compression) as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return path


def test_parse_frontmatter_requires_fields_allows_hyphen_and_preserves_unknown_fields() -> None:
    metadata, body = parse_skill_markdown(SKILL_MD)

    assert metadata.name == "demo-skill"
    assert metadata.description == "A portable test Skill."
    assert metadata.frontmatter["license"] == "MIT"
    assert metadata.frontmatter["metadata"]["owner"] == "test"
    assert metadata.frontmatter["tags"] == ("portable",)
    assert body.startswith("# Demo")
    with pytest.raises(TypeError):
        metadata.frontmatter["license"] = "changed"  # type: ignore[index]


@pytest.mark.parametrize(
    "content,code",
    [
        ("# no frontmatter", "frontmatter_missing"),
        ("---\ndescription: missing name\n---\n", "frontmatter_name"),
        ("---\nname: demo-skill\n---\n", "frontmatter_description"),
        ("---\nname: demo--skill\ndescription: bad\n---\n", "frontmatter_name"),
        ("---\nname: demo-skill\nname: duplicate\ndescription: bad\n---\n", "frontmatter_duplicate_key"),
    ],
)
def test_parse_frontmatter_rejects_invalid_metadata(content: str, code: str) -> None:
    with pytest.raises(SkillPackageError) as error:
        parse_skill_markdown(content)
    assert error.value.code == code


@pytest.mark.parametrize(
    "yaml_value,code",
    [
        ("2026-08-24", "frontmatter_json_type"),
        ("!!binary SGVsbG8=", "frontmatter_json_type"),
        (".nan", "frontmatter_json_number"),
    ],
)
def test_parse_frontmatter_rejects_non_json_yaml_scalars(yaml_value: str, code: str) -> None:
    content = f"---\nname: demo-skill\ndescription: Portable.\nunsafe: {yaml_value}\n---\nBody\n"

    with pytest.raises(SkillPackageError) as error:
        parse_skill_markdown(content)

    assert error.value.code == code
    assert error.value.path == "frontmatter.unsafe"


def test_directory_package_builds_immutable_resource_manifest(tmp_path: Path) -> None:
    source = _write_directory_package(tmp_path / "skill")

    package = load_skill_package(source)

    assert package.package_type == "directory"
    assert package.metadata.name == "demo-skill"
    assert [item.path for item in package.resources] == [
        "assets/sample.bin",
        "references/guide.md",
        "scripts/run.py",
        "SKILL.md",
    ]
    assert {item.kind for item in package.resources} == {"asset", "reference", "script", "instructions"}
    assert all(len(item.sha256) == 64 for item in package.resources)
    with pytest.raises(FrozenInstanceError):
        package.total_uncompressed_bytes = 0  # type: ignore[misc]


def test_zip_package_is_read_without_extracting_or_executing(tmp_path: Path) -> None:
    marker = tmp_path / "executed"
    archive_path = _write_zip(
        tmp_path / "skill.zip",
        [
            ("SKILL.md", SKILL_MD.encode()),
            ("scripts/run.py", f"from pathlib import Path\nPath({str(marker)!r}).touch()\n".encode()),
            ("references/guide.md", b"guide"),
        ],
    )

    package = parse_skill_zip(archive_path)

    assert package.package_type == "zip"
    assert package.metadata.frontmatter["license"] == "MIT"
    assert not marker.exists()
    assert not (tmp_path / "scripts").exists()


@pytest.mark.parametrize(
    "unsafe_name,code",
    [
        ("../escape.txt", "path_traversal"),
        ("/absolute.txt", "path_absolute"),
        ("C:/drive.txt", "path_absolute"),
        ("//server/share.txt", "path_absolute"),
        # Python's zipfile normalizes Windows separators when creating an
        # archive, but the resulting UNC spelling must still be rejected.
        ("\\\\server\\share.txt", "path_absolute"),
        ("CON.txt", "path_device"),
    ],
)
def test_zip_rejects_unsafe_paths(tmp_path: Path, unsafe_name: str, code: str) -> None:
    archive_path = _write_zip(
        tmp_path / "unsafe.zip",
        [("SKILL.md", SKILL_MD.encode()), (unsafe_name, b"unsafe")],
    )

    with pytest.raises(SkillPackageError) as error:
        parse_skill_zip(archive_path)
    assert error.value.code == code


def test_zip_rejects_duplicate_case_and_unicode_normalization_collisions(tmp_path: Path) -> None:
    exact = tmp_path / "exact.zip"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        _write_zip(exact, [("SKILL.md", SKILL_MD.encode()), ("dup.txt", b"1"), ("dup.txt", b"2")])
    with pytest.raises(SkillPackageError, match="duplicate"):
        parse_skill_zip(exact)

    case = _write_zip(
        tmp_path / "case.zip",
        [("SKILL.md", SKILL_MD.encode()), ("References/a.txt", b"1"), ("references/b.txt", b"2")],
    )
    with pytest.raises(SkillPackageError, match="case-insensitive"):
        parse_skill_zip(case)

    composed = "references/" + unicodedata.normalize("NFC", "cafe\u0301") + ".txt"
    decomposed = "references/" + unicodedata.normalize("NFD", "cafe\u0301") + ".txt"
    unicode_archive = _write_zip(
        tmp_path / "unicode.zip",
        [("SKILL.md", SKILL_MD.encode()), (composed, b"1"), (decomposed, b"2")],
    )
    with pytest.raises(SkillPackageError, match="Unicode normalization"):
        parse_skill_zip(unicode_archive)


def test_zip_rejects_symlink_and_device_entries(tmp_path: Path) -> None:
    symlink_path = tmp_path / "symlink.zip"
    with zipfile.ZipFile(symlink_path, "w") as archive:
        archive.writestr("SKILL.md", SKILL_MD)
        info = zipfile.ZipInfo("link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "target")
    with pytest.raises(SkillPackageError) as error:
        parse_skill_zip(symlink_path)
    assert error.value.code == "symlink"

    device_path = tmp_path / "device.zip"
    with zipfile.ZipFile(device_path, "w") as archive:
        archive.writestr("SKILL.md", SKILL_MD)
        info = zipfile.ZipInfo("device")
        info.create_system = 3
        info.external_attr = (stat.S_IFCHR | 0o666) << 16
        archive.writestr(info, b"")
    with pytest.raises(SkillPackageError) as error:
        parse_skill_zip(device_path)
    assert error.value.code == "special_file"


def test_directory_rejects_symlink_and_hardlink(tmp_path: Path) -> None:
    symlink_source = _write_directory_package(tmp_path / "symlink-skill")
    try:
        (symlink_source / "linked.md").symlink_to(symlink_source / "references" / "guide.md")
    except OSError:
        pytest.skip("creating symlinks is unavailable on this platform")
    with pytest.raises(SkillPackageError) as error:
        parse_skill_directory(symlink_source)
    assert error.value.code == "symlink"

    hardlink_source = _write_directory_package(tmp_path / "hardlink-skill")
    try:
        os.link(hardlink_source / "references" / "guide.md", hardlink_source / "guide-copy.md")
    except OSError:
        pytest.skip("creating hardlinks is unavailable on this filesystem")
    with pytest.raises(SkillPackageError) as error:
        parse_skill_directory(hardlink_source)
    assert error.value.code == "hardlink"


def test_package_limits_reject_file_count_sizes_and_zip_bomb_ratio(tmp_path: Path) -> None:
    files_archive = _write_zip(
        tmp_path / "files.zip",
        [("SKILL.md", SKILL_MD.encode()), ("one.txt", b"1")],
    )
    with pytest.raises(SkillPackageError) as error:
        parse_skill_zip(files_archive, limits=SkillPackageLimits(max_files=1))
    assert error.value.code == "file_count"

    large_archive = _write_zip(
        tmp_path / "large.zip",
        [("SKILL.md", SKILL_MD.encode()), ("large.bin", b"x" * 200)],
    )
    with pytest.raises(SkillPackageError) as error:
        parse_skill_zip(large_archive, limits=SkillPackageLimits(max_single_file_bytes=199))
    assert error.value.code == "file_size"

    compressed_archive = _write_zip(
        tmp_path / "compressed.zip",
        [("SKILL.md", SKILL_MD.encode()), ("asset.bin", b"0" * 100_000)],
        compression=zipfile.ZIP_DEFLATED,
    )
    with pytest.raises(SkillPackageError) as error:
        parse_skill_zip(compressed_archive, limits=SkillPackageLimits(max_compression_ratio=10))
    assert error.value.code == "compression_ratio"


def test_package_requires_root_skill_markdown(tmp_path: Path) -> None:
    archive_path = _write_zip(tmp_path / "nested.zip", [("nested/SKILL.md", SKILL_MD.encode())])

    with pytest.raises(SkillPackageError) as error:
        parse_skill_zip(archive_path)
    assert error.value.code == "skill_markdown_missing"
