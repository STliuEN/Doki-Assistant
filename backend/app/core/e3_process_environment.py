"""Immutable E3 settings captured before any module can load dotenv."""

from __future__ import annotations

import os

_E3_PROCESS_NAMES = frozenset(
    {
        "E3_MIGRATION_ENABLED",
        "E3_DATABASE_URL",
        "E3_APPROVAL_TOKEN",
        "E3_PREFLIGHT_FILE",
    }
)

E3_PROCESS_ENVIRONMENT = {name: os.environ[name] for name in _E3_PROCESS_NAMES if name in os.environ}
