"""Offline E4 migration primitives.

The package intentionally contains no database, network, settings, or ORM
dependency.  Its identity dry-run accepts explicit snapshots and returns a
redacted, deterministic report that a later E4 adapter may review before any
SQL write is considered.
"""

from app.e4.identity import (
    E4_IDENTITY_TOOL_VERSION,
    IdentityDecision,
    IdentityDryRunError,
    IdentityDryRunReport,
    IdentityInput,
    SourceKey,
    build_identity_dry_run,
    deterministic_target_uuid,
    identity_report_to_dict,
    load_identity_input,
    write_identity_report,
)

__all__ = [
    "E4_IDENTITY_TOOL_VERSION",
    "IdentityDecision",
    "IdentityDryRunError",
    "IdentityDryRunReport",
    "IdentityInput",
    "SourceKey",
    "build_identity_dry_run",
    "deterministic_target_uuid",
    "identity_report_to_dict",
    "load_identity_input",
    "write_identity_report",
]
