from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from sqlalchemy import select

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

async def rotate(*, apply: bool) -> int:
    from app.db.db_config import AsyncSessionLocal, async_engine
    from app.models.model_config import UserModelConfig
    from app.utils.crypto_utils import decrypt_text, encrypt_text

    old_key = os.getenv("MODEL_CONFIG_ENCRYPTION_KEY_PREVIOUS")
    new_key = os.getenv("MODEL_CONFIG_ENCRYPTION_KEY")
    if not old_key or not new_key:
        raise RuntimeError(
            "MODEL_CONFIG_ENCRYPTION_KEY_PREVIOUS and MODEL_CONFIG_ENCRYPTION_KEY are required"
        )
    if old_key == new_key:
        raise RuntimeError("The previous and current encryption keys must differ")

    rotated = 0
    already_current = 0
    try:
        async with AsyncSessionLocal() as session:
            configs = list((await session.scalars(select(UserModelConfig))).all())
            for config in configs:
                encrypted = config.api_key_encrypted
                if not encrypted:
                    continue
                try:
                    decrypt_text(encrypted, secret=new_key, strict=True)
                    already_current += 1
                    continue
                except ValueError:
                    pass

                plaintext = decrypt_text(encrypted, secret=old_key, strict=True)
                if apply:
                    config.api_key_encrypted = encrypt_text(plaintext, secret=new_key)
                rotated += 1

            if apply:
                await session.commit()
            else:
                await session.rollback()
    finally:
        await async_engine.dispose()

    print(
        f"model configs: rotate={rotated}, already_current={already_current}, "
        f"mode={'apply' if apply else 'dry-run'}"
    )
    return rotated


async def async_main() -> int:
    parser = argparse.ArgumentParser(description="Rotate encrypted model API keys.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit the rotation. Without this flag the command is a dry run.",
    )
    args = parser.parse_args()
    await rotate(apply=args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(async_main()))
