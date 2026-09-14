"""Replica-only positive and negative SQL media acceptance."""

import argparse
import asyncio
import hashlib
import json
import os
import sys
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))


async def run(directory):
    from app.db.db_config import AsyncSessionLocal, async_engine, verify_database_schema
    from app.models.e4_migration import MediaAsset
    from app.models.identity_domain import User
    from app.models.knowledge_document import KnowledgeSourceDocument
    from app.services.sql_media import image_response, source_images, store_source_images, verify_asset

    owner = "2e2c05f2-d031-527e-b463-93c9f0cccbfa"
    other = "f4aff4a5-2f5a-535a-825f-b6a906d9cd12"
    image_buffer = BytesIO()
    Image.new("RGB", (32, 24), (40, 120, 220)).save(image_buffer, format="PNG")
    image = image_buffer.getvalue()
    content = b"synthetic-e6e7-media-source"
    source_id = str(uuid4())
    md5 = hashlib.md5(content).hexdigest()
    artifact = hashlib.sha256(content).hexdigest()
    report = {}
    try:
        await verify_database_schema()
        async with AsyncSessionLocal() as db, db.begin():
            if await db.get(User, owner) is None or await db.get(User, other) is None:
                raise RuntimeError("Replica fixture owners are missing")
            source = KnowledgeSourceDocument(id=source_id, user_id=owner, canonical_id=source_id,
                canonical_user_id=owner, md5=md5, content_digest=artifact, artifact_digest=artifact,
                filename="e6e7-media-fixture.md", original_filename="e6e7-media-fixture.md",
                file_ext="md", mime_type="text/markdown", file_size=len(content), content_blob=content,
                status="indexed")
            db.add(source)
            await db.flush()
            await store_source_images(db, source, [("fixture.png", 0, image, "image/png")])
            rows = await source_images(db, owner, source_id=source_id)
            assert len(rows) == 1 and rows[0]["content"] == image
            report["positive"] = {"stored": True, "owner_read": True, "digest": hashlib.sha256(image).hexdigest()}
            try:
                await image_response(db, other, md5, "fixture.png")
            except Exception as exc:
                report["cross_user_rejected"] = type(exc).__name__
            else:
                raise AssertionError("cross-user media access was accepted")
            asset = await db.get(MediaAsset, rows[0]["media_id"])
            asset.content_blob = b"corrupted"
            try:
                verify_asset(asset, owner)
            except Exception as exc:
                report["corruption_rejected"] = type(exc).__name__
            else:
                raise AssertionError("corrupted media was accepted")
            report.update({"stage": "E6E7", "fixture": "replica-only", "old_media_count_before_fixture": 0})
        (directory / "media-acceptance.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report))
    finally:
        await async_engine.dispose()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    from ops.e6_e7.acceptance_env import preflight
    os.environ.update(preflight(args.directory.resolve(), purposes=("runtime", "validate")))
    os.environ.update({"E6E7_ENABLED": "true", "E5_RAG_ENABLED": "true", "ENV": "dev"})
    asyncio.run(run(args.directory.resolve()))


if __name__ == "__main__":
    main()
