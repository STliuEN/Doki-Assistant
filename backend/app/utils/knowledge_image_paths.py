import re
from pathlib import Path

from app.utils.path_tool import get_data_path

MD5_PATTERN = re.compile(r"^[0-9a-f]{32}$")
USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,254}$")

IMAGE_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

MAX_BATCH_IMAGE_FILES = 100
MAX_BATCH_IMAGE_BYTES = 25 * 1024 * 1024


class InvalidKnowledgeImagePath(ValueError):
    """Raised when an image path component escapes the knowledge image root."""


def normalize_md5(md5: str) -> str:
    normalized = md5.strip().lower()
    if not MD5_PATTERN.fullmatch(normalized):
        raise InvalidKnowledgeImagePath("md5 must be a 32-character hexadecimal value")
    return normalized


def validate_user_id(user_id: str) -> str:
    if not USER_ID_PATTERN.fullmatch(user_id):
        raise InvalidKnowledgeImagePath("invalid user id")
    return user_id


def validate_image_filename(filename: str) -> str:
    if not FILENAME_PATTERN.fullmatch(filename) or "/" in filename or "\\" in filename or ":" in filename:
        raise InvalidKnowledgeImagePath("invalid image filename")
    if Path(filename).suffix.lower() not in IMAGE_MEDIA_TYPES:
        raise InvalidKnowledgeImagePath("unsupported image extension")
    return filename


def _ensure_contained(candidate: Path, root: Path) -> Path:
    resolved_root = root.resolve()
    resolved_candidate = candidate.resolve()
    if not resolved_candidate.is_relative_to(resolved_root):
        raise InvalidKnowledgeImagePath("image path escapes its storage root")
    return resolved_candidate


def _ensure_not_link(path: Path) -> None:
    is_junction = getattr(path, "is_junction", None)
    if path.is_symlink() or (callable(is_junction) and is_junction()):
        raise InvalidKnowledgeImagePath("symbolic and junction image paths are not allowed")


def get_image_root() -> Path:
    unresolved_root = Path(get_data_path()) / "extracted_images"
    _ensure_not_link(unresolved_root)
    return unresolved_root.resolve()


def resolve_user_image_dir(user_id: str, *, create: bool = False) -> Path:
    root = get_image_root()
    unresolved_user_dir = root / validate_user_id(user_id)
    _ensure_not_link(unresolved_user_dir)
    user_dir = _ensure_contained(unresolved_user_dir, root)
    if create:
        user_dir.mkdir(parents=True, exist_ok=True)
        _ensure_not_link(unresolved_user_dir)
    return _ensure_contained(unresolved_user_dir, root)


def resolve_image_storage_dir(user_id: str, md5: str, *, create: bool = False) -> Path:
    user_dir = resolve_user_image_dir(user_id, create=create)
    unresolved_storage_dir = user_dir / normalize_md5(md5)
    _ensure_not_link(unresolved_storage_dir)
    storage_dir = _ensure_contained(unresolved_storage_dir, user_dir)
    if create:
        storage_dir.mkdir(parents=True, exist_ok=True)
        _ensure_not_link(unresolved_storage_dir)
    return _ensure_contained(unresolved_storage_dir, user_dir)


def resolve_knowledge_image_path(user_id: str, md5: str, filename: str, *, must_exist: bool = False) -> Path:
    storage_dir = resolve_image_storage_dir(user_id, md5, create=False)
    safe_filename = validate_image_filename(filename)
    unresolved_path = storage_dir / safe_filename
    _ensure_not_link(unresolved_path)
    image_path = _ensure_contained(unresolved_path, storage_dir)
    if must_exist and (not image_path.exists() or not image_path.is_file()):
        raise FileNotFoundError(filename)
    return image_path


def get_image_media_type(filename: str) -> str:
    return IMAGE_MEDIA_TYPES[Path(validate_image_filename(filename)).suffix.lower()]
