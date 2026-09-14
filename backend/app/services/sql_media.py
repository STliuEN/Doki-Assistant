"""Image bytes and source ownership are SQL facts; no path or network fallback."""

import base64
import hashlib
import io
import re
import zipfile
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException
from PIL import Image
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.auth.audit import record_audit
from app.models.e4_migration import MediaAsset
from app.models.e6_e7_domain import SourceMedia
from app.models.knowledge_document import KnowledgeSourceDocument

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_IMAGES = 256
_MIME = {"PNG": "image/png", "JPEG": "image/jpeg", "GIF": "image/gif", "WEBP": "image/webp"}


def validate_image(content):
    if not content or len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Image size limit exceeded")
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format not in _MIME or image.width * image.height > 40_000_000:
                raise ValueError("unsupported image")
            mime = _MIME[image.format]
            image.verify()
    except (ValueError, OSError, Image.DecompressionBombError) as exc:
        raise HTTPException(409, "Invalid or unsupported image bytes") from exc
    return mime


def extract_images(content, extension):
    """Read only embedded image bytes; never fetch a URL or extract host files."""
    extension = extension.lower().lstrip(".")
    images = []
    total = 0

    def add(data, filename, page):
        nonlocal total
        mime = validate_image(data)
        total += len(data)
        if len(images) >= MAX_IMAGES or total > MAX_TOTAL_BYTES:
            raise HTTPException(413, "Document image budget exceeded")
        images.append((filename, page, data, mime))

    if extension == "pdf":
        import pymupdf
        with pymupdf.open(stream=content, filetype="pdf") as document:
            if document.needs_pass or document.page_count > 1000:
                raise HTTPException(413, "PDF image extraction limit exceeded")
            for number, page in enumerate(document):
                for index, value in enumerate(page.get_images(full=True)):
                    with_image = document.extract_image(value[0])
                    data = with_image["image"]
                    if with_image["ext"] not in {"png", "jpg", "jpeg", "webp", "gif"}:
                        pixmap = pymupdf.Pixmap(document, value[0])
                        if pixmap.n > 4:
                            pixmap = pymupdf.Pixmap(pymupdf.csRGB, pixmap)
                        data = pixmap.tobytes("png")
                        suffix = "png"
                    else:
                        suffix = with_image["ext"]
                    add(data, f"page-{number + 1}-image-{index + 1}.{suffix}", number + 1)
    elif extension in {"docx", "pptx"}:
        prefix = "word/media/" if extension == "docx" else "ppt/media/"
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = [info for info in archive.infolist() if info.filename.startswith(prefix) and not info.is_dir()]
            if len(infos) > MAX_IMAGES or sum(info.file_size for info in infos) > MAX_TOTAL_BYTES:
                raise HTTPException(413, "Document image budget exceeded")
            for index, info in enumerate(infos):
                if info.file_size > MAX_IMAGE_BYTES or info.file_size / max(1, info.compress_size) > 200:
                    raise HTTPException(413, "Embedded image expansion limit exceeded")
                suffix = info.filename.rsplit(".", 1)[-1].lower()
                # Unsupported vector/office metafiles are not exposed as active content.
                if suffix not in {"png", "jpg", "jpeg", "gif", "webp"}:
                    continue
                add(archive.read(info), f"embedded-{index + 1}.{suffix}", 0)
    elif extension in {"md", "markdown"}:
        text = content.decode("utf-8-sig")
        for index, match in enumerate(re.finditer(r"data:image/(png|jpeg|gif|webp);base64,([A-Za-z0-9+/=]+)", text)):
            encoded = match[2]
            if len(encoded) > (MAX_IMAGE_BYTES * 4 // 3 + 4):
                raise HTTPException(413, "Embedded image limit exceeded")
            add(base64.b64decode(encoded, validate=True), f"embedded-{index + 1}.{match[1]}", 0)
    return images


async def store_source_images(db, document, images):
    owner = document.canonical_user_id
    if not owner or not document.canonical_id:
        raise HTTPException(409, "Canonical source owner is required")
    source_digest = hashlib.sha256(document.content_blob).hexdigest()
    if document.artifact_digest != source_digest:
        raise HTTPException(409, "Source bytes changed")
    await db.execute(delete(SourceMedia).where(SourceMedia.source_id == document.canonical_id, SourceMedia.user_id == owner))
    for filename, page, data, mime in images:
        if validate_image(data) != mime:
            raise HTTPException(409, "Image MIME mismatch")
        digest = hashlib.sha256(data).hexdigest()
        asset_id = str(uuid5(NAMESPACE_URL, f"doki:media:{owner}:{digest}"))
        asset = await db.get(MediaAsset, asset_id)
        if asset is None:
            try:
                async with db.begin_nested():
                    asset = MediaAsset(id=asset_id, canonical_user_id=owner, scope_type="user", scope_id=owner,
                                       source_system="e6e7-media", source_id=f"{owner}:{digest}", migration_batch_id="e6e7-runtime",
                                       content_digest=digest, artifact_digest=digest, legacy_md5=hashlib.md5(data).hexdigest(),
                                       filename=filename, mime_type=mime, byte_size=len(data), content_blob=data, status="active")
                    db.add(asset)
                    await db.flush()
            except IntegrityError:
                asset = await db.get(MediaAsset, asset_id, populate_existing=True)
                if asset is None:
                    raise
        verify_asset(asset, owner)
        db.add(SourceMedia(source_id=document.canonical_id, media_id=asset_id, user_id=owner,
                           filename=filename, page=page, source_digest=source_digest))
    await db.flush()
    await record_audit(db, action="media.source_ingested", target_type="knowledge_source", target_id=document.canonical_id,
                       actor_id=owner, result="succeeded", reason="Store embedded images with canonical source ownership",
                       scope_type="user", scope_id=owner, content_digest=source_digest, after={"image_count": len(images)})


def verify_asset(asset, owner):
    if asset.canonical_user_id != owner or (asset.scope_type, asset.scope_id) != ("user", owner) or asset.status != "active":
        raise HTTPException(404, "Image not found")
    content = bytes(asset.content_blob)
    digest = hashlib.sha256(content).hexdigest()
    if (asset.byte_size != len(content) or asset.artifact_digest != digest or asset.content_digest != digest
            or validate_image(content) != asset.mime_type):
        raise HTTPException(409, "Image integrity check failed")
    return content


async def source_images(db, owner, *, md5=None, source_id=None):
    if md5 is not None and not re.fullmatch(r"[0-9a-fA-F]{32}", md5):
        raise HTTPException(400, "Invalid document digest")
    statement = select(KnowledgeSourceDocument).where(KnowledgeSourceDocument.canonical_user_id == owner,
                                                      KnowledgeSourceDocument.status != "excluded")
    statement = statement.where(KnowledgeSourceDocument.md5 == md5.lower()) if md5 else statement.where(
        KnowledgeSourceDocument.canonical_id == source_id)
    sources = list(await db.scalars(statement.execution_options(populate_existing=True)))
    if len(sources) != 1:
        raise HTTPException(404 if not sources else 409, "Document not found or ambiguous")
    source = sources[0]
    actual = hashlib.sha256(source.content_blob).hexdigest()
    if actual != source.artifact_digest:
        raise HTTPException(409, "Source integrity check failed")
    rows = (await db.execute(select(SourceMedia, MediaAsset).join(MediaAsset, MediaAsset.id == SourceMedia.media_id).where(
        SourceMedia.source_id == source.canonical_id, SourceMedia.user_id == owner,
    ).order_by(SourceMedia.page, SourceMedia.filename).execution_options(populate_existing=True))).all()
    result = []
    for link, asset in rows:
        if link.source_digest != actual:
            raise HTTPException(409, "Source image revision changed")
        result.append({"filename": link.filename, "page": link.page, "media_id": asset.id,
                       "mime_type": asset.mime_type, "content": verify_asset(asset, owner),
                       "url": f"/knowledge/image/{source.md5}/{link.filename}"})
    return result


async def image_response(db, owner, md5, filename):
    if not filename or filename in {".", ".."} or any(char in filename for char in "/\\\x00"):
        raise HTTPException(400, "Invalid image name")
    rows = await source_images(db, owner, md5=md5)
    result = next((row for row in rows if row["filename"] == filename), None)
    if result is None:
        raise HTTPException(404, "Image not found")
    return result


async def batch_images(db, owner, md5):
    images = await source_images(db, owner, md5=md5)
    return {"md5": md5, "images": {row["filename"]: f"data:{row['mime_type']};base64,{base64.b64encode(row['content']).decode()}"
                                    for row in images}, "total": len(images)}
