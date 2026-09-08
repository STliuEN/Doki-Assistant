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
from app.e4.importer import (
    BusinessBundle,
    E4BundleValidationError,
    E4BusinessBundle,
    E4BusinessImporter,
    E4ImportBlocked,
    E4ImportConflict,
    E4Importer,
    E4ImportError,
    E4ImportResult,
    ImportResult,
    build_business_dry_run,
    bundle_file_sha256,
    load_business_bundle,
)
from app.e4.repository import (
    E4_BATCH_TRANSITIONS,
    E4_ENTITY_TRANSITIONS,
    E4ConflictError,
    E4MigrationRepository,
    E4Repository,
    E4RepositoryError,
    E4StateError,
    E4ValidationError,
    MappingResult,
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
    "E4_BATCH_TRANSITIONS",
    "E4_ENTITY_TRANSITIONS",
    "E4ConflictError",
    "E4MigrationRepository",
    "E4Repository",
    "E4RepositoryError",
    "E4StateError",
    "E4ValidationError",
    "MappingResult",
    "BusinessBundle",
    "E4BusinessBundle",
    "E4BusinessImporter",
    "E4BundleValidationError",
    "E4ImportBlocked",
    "E4ImportConflict",
    "E4ImportError",
    "E4ImportResult",
    "E4Importer",
    "ImportResult",
    "build_business_dry_run",
    "bundle_file_sha256",
    "load_business_bundle",
]
