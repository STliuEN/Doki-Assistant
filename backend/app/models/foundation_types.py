from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, LargeBinary, String
from sqlalchemy.dialects import mysql


def utc_now() -> datetime:
    return datetime.now(UTC)


def ascii_string(length: int):
    return String(length).with_variant(
        mysql.VARCHAR(length=length, charset="ascii", collation="ascii_bin"),
        "mysql",
    )


def binary_string(length: int):
    return String(length).with_variant(
        mysql.VARCHAR(length=length, charset="utf8mb4", collation="utf8mb4_bin"),
        "mysql",
    )


UUID_TYPE = String(36).with_variant(
    mysql.CHAR(length=36, charset="ascii", collation="ascii_bin"),
    "mysql",
)
DIGEST_TYPE = String(64).with_variant(
    mysql.CHAR(length=64, charset="ascii", collation="ascii_bin"),
    "mysql",
)
UTC_DATETIME = DateTime(timezone=True).with_variant(mysql.DATETIME(fsp=6), "mysql")
LONG_BLOB = LargeBinary().with_variant(mysql.LONGBLOB(), "mysql")

UUID_PATTERN = "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
DIGEST_PATTERN = "^[0-9a-f]{64}$"
