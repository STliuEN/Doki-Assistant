from __future__ import annotations


class AuthError(Exception):
    """An authentication failure with a stable client-facing code."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 401,
        data: dict | None = None,
        audit_actor_id: str | None = None,
        audit_target_id: str | None = None,
        audit_context: dict | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.data = data
        self.audit_actor_id = audit_actor_id
        self.audit_target_id = audit_target_id
        self.audit_context = audit_context or {}
        super().__init__(message)


AUTH_INVALID_CREDENTIALS = "AUTH_INVALID_CREDENTIALS"
AUTH_ACCOUNT_DISABLED = "AUTH_ACCOUNT_DISABLED"
AUTH_ACCOUNT_LOCKED = "AUTH_ACCOUNT_LOCKED"
AUTH_SESSION_INVALID = "AUTH_SESSION_INVALID"
AUTH_REFRESH_INVALID = "AUTH_REFRESH_INVALID"
AUTH_REFRESH_REPLAY = "AUTH_REFRESH_REPLAY"
AUTH_FORBIDDEN = "AUTH_FORBIDDEN"
AUTH_CONFLICT = "AUTH_CONFLICT"
AUTH_VALIDATION = "AUTH_VALIDATION"
