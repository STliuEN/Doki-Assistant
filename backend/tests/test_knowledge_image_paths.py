import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.router.knowledge_service import KnowledgeService
from app.utils import knowledge_image_paths
from app.utils.knowledge_image_paths import InvalidKnowledgeImagePath

USER_ID = "user-123"
MD5 = "a" * 32


@pytest.fixture
def image_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(knowledge_image_paths, "get_data_path", lambda: str(tmp_path))
    return tmp_path / "extracted_images"


def test_storage_path_is_normalized_and_contained(image_root: Path) -> None:
    storage_dir = knowledge_image_paths.resolve_image_storage_dir(USER_ID, MD5.upper(), create=True)

    assert storage_dir == image_root / USER_ID / MD5
    assert storage_dir.is_dir()


@pytest.mark.parametrize("md5", ["../secrets", "a" * 31, "g" * 32, "C:" + "a" * 30, "a" * 32 + "\\.."])
def test_invalid_md5_is_rejected(image_root: Path, md5: str) -> None:
    with pytest.raises(InvalidKnowledgeImagePath):
        knowledge_image_paths.resolve_image_storage_dir(USER_ID, md5)


@pytest.mark.parametrize(
    "filename",
    ["..\\secret.png", "../secret.png", "C:secret.png", "/secret.png", "note.txt", "..", "image.png/extra"],
)
def test_invalid_filename_is_rejected(image_root: Path, filename: str) -> None:
    knowledge_image_paths.resolve_image_storage_dir(USER_ID, MD5, create=True)

    with pytest.raises(InvalidKnowledgeImagePath):
        knowledge_image_paths.resolve_knowledge_image_path(USER_ID, MD5, filename)


def test_read_resolution_does_not_create_directories(image_root: Path) -> None:
    path = knowledge_image_paths.resolve_knowledge_image_path(USER_ID, MD5, "p0_i0.png")

    assert path == image_root / USER_ID / MD5 / "p0_i0.png"
    assert not image_root.exists()


def test_symlink_components_are_rejected(image_root: Path, tmp_path: Path) -> None:
    root_target = tmp_path / "root-target"
    root_target.mkdir()
    other_user_dir = image_root / "other-user"
    try:
        image_root.symlink_to(root_target, target_is_directory=True)
        with pytest.raises(InvalidKnowledgeImagePath):
            knowledge_image_paths.get_image_root()
        image_root.unlink()

        other_user_dir.mkdir(parents=True)
        user_link = image_root / USER_ID
        user_link.symlink_to(other_user_dir, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks are unavailable: {exc}")

    with pytest.raises(InvalidKnowledgeImagePath):
        knowledge_image_paths.resolve_user_image_dir(USER_ID)

    user_link.unlink()
    user_dir = image_root / USER_ID
    other_storage_dir = user_dir / ("b" * 32)
    other_storage_dir.mkdir(parents=True)
    storage_link = user_dir / MD5
    storage_link.symlink_to(other_storage_dir, target_is_directory=True)

    with pytest.raises(InvalidKnowledgeImagePath):
        knowledge_image_paths.resolve_image_storage_dir(USER_ID, MD5)

    storage_link.unlink()
    storage_dir = knowledge_image_paths.resolve_image_storage_dir(USER_ID, MD5, create=True)
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"outside")
    image_link = storage_dir / "p0_i0.png"
    image_link.symlink_to(outside)

    with pytest.raises(InvalidKnowledgeImagePath):
        knowledge_image_paths.resolve_knowledge_image_path(USER_ID, MD5, image_link.name, must_exist=True)


def test_batch_reader_filters_non_images_and_returns_supported_images(image_root: Path) -> None:
    storage_dir = knowledge_image_paths.resolve_image_storage_dir(USER_ID, MD5, create=True)
    (storage_dir / "p0_i0.png").write_bytes(b"png")
    (storage_dir / "ignored.txt").write_text("not an image", encoding="utf-8")

    result = asyncio.run(KnowledgeService().handle_get_batch_images(USER_ID, MD5))

    assert result["md5"] == MD5
    assert set(result["images"]) == {"p0_i0.png"}
    assert result["images"]["p0_i0.png"].startswith("data:image/png;base64,")


def test_batch_reader_enforces_total_size_budget(image_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage_dir = knowledge_image_paths.resolve_image_storage_dir(USER_ID, MD5, create=True)
    (storage_dir / "p0_i0.png").write_bytes(b"too-large")
    monkeypatch.setattr("app.router.knowledge_service.MAX_BATCH_IMAGE_BYTES", 1)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(KnowledgeService().handle_get_batch_images(USER_ID, MD5))

    assert exc_info.value.status_code == 413
