"""Immutable E4 process settings captured before dotenv can be loaded."""

from __future__ import annotations

import os

from app.db.e4_guard import E4_ENVIRONMENT_NAMES

E4_PROCESS_ENVIRONMENT = {
    name: os.environ[name]
    for name in (
        *E4_ENVIRONMENT_NAMES,
        "E4_RUNNER_ENABLED",
        "JOB_LEASE_SECONDS",
        "JOB_HEARTBEAT_SECONDS",
        "JOB_POLL_SECONDS",
        "JOB_SHUTDOWN_DRAIN_SECONDS",
    )
    if name in os.environ
}
