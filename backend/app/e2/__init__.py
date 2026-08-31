"""Internal E2 SQL state primitives.

This package is deliberately not imported by a product router or service.  The
repositories accept a caller-owned SQLAlchemy session and leave transaction
commit/rollback to that caller, so they can be exercised against synthetic
fixtures without granting access to the existing application data paths.
"""

from app.e2.auth import SyntheticAuthRepository
from app.e2.errors import E2PrimitiveConflictError, E2PrimitiveValidationError
from app.e2.migration import SyntheticMigrationMapRepository
from app.e2.rag import SyntheticRagRepository
from app.e2.skill import SyntheticSkillRepository

__all__ = [
    "E2PrimitiveConflictError",
    "E2PrimitiveValidationError",
    "SyntheticAuthRepository",
    "SyntheticMigrationMapRepository",
    "SyntheticRagRepository",
    "SyntheticSkillRepository",
]
