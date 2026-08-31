from __future__ import annotations


class E2PrimitiveValidationError(ValueError):
    """A synthetic E2 primitive input violated the frozen SQL contract."""


class E2PrimitiveConflictError(RuntimeError):
    """A synthetic E2 primitive conflicts with an existing immutable fact."""
