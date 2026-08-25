"""Hard request-size guards for every standard Skill write endpoint."""

from __future__ import annotations

from tempfile import SpooledTemporaryFile

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.skills.schema import (
    MAX_SKILL_DRAFT_JSON_BODY_BYTES,
    MAX_SKILL_IMPORT_BODY_BYTES,
    MAX_SKILL_JSON_BODY_BYTES,
)

_REPLAY_CHUNK_BYTES = 64 * 1024
_SPOOL_MEMORY_BYTES = 1024 * 1024
_SKILL_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _normalized_skill_path(scope: Scope) -> str | None:
    path = str(scope.get("path", "")).rstrip("/") or "/"
    if path == "/api/skills" or path.startswith("/api/skills/"):
        path = path.removeprefix("/api")
    if path == "/skills" or path.startswith("/skills/"):
        return path
    return None


def _skill_write_limit(scope: Scope) -> int | None:
    if str(scope.get("method", "")).upper() not in _SKILL_WRITE_METHODS:
        return None
    path = _normalized_skill_path(scope)
    if path is None:
        return None
    if path == "/skills/imports":
        return MAX_SKILL_IMPORT_BODY_BYTES
    if path == "/skills/drafts" or (
        path.startswith("/skills/") and path.endswith("/draft")
    ):
        return MAX_SKILL_DRAFT_JSON_BODY_BYTES
    return MAX_SKILL_JSON_BODY_BYTES


class SkillRequestBodyLimitMiddleware:
    """Buffer bounded Skill writes before auth and request-model parsing.

    Small payloads stay in memory. Large ZIP and resource-editor requests are
    spooled to a temporary file so chunked bodies cannot bypass the limit.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_body_bytes: int | None = None,
    ) -> None:
        if max_body_bytes is not None and max_body_bytes <= 0:
            raise ValueError("max_body_bytes must be positive")
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        route_limit = _skill_write_limit(scope) if scope["type"] == "http" else None
        normalized_path = _normalized_skill_path(scope) if route_limit is not None else None
        # The injectable override is retained for the historical draft-only
        # unit-test contract; production routing always uses per-endpoint caps.
        limit = (
            self.max_body_bytes
            if self.max_body_bytes is not None and normalized_path is not None and (
                normalized_path == "/skills/drafts"
                or normalized_path.endswith("/draft")
            )
            else route_limit
        )
        if limit is None:
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        raw_content_length = headers.get(b"content-length")
        if raw_content_length is not None:
            try:
                declared_length = int(raw_content_length)
            except ValueError:
                await self._reject(
                    scope,
                    receive,
                    send,
                    status_code=400,
                    message="Invalid Content-Length header",
                )
                return
            if declared_length < 0:
                await self._reject(
                    scope,
                    receive,
                    send,
                    status_code=400,
                    message="Invalid Content-Length header",
                )
                return
            if declared_length > limit:
                await self._reject(
                    scope,
                    receive,
                    send,
                    status_code=413,
                    message=self._limit_message(limit),
                )
                return

        spool = SpooledTemporaryFile(max_size=_SPOOL_MEMORY_BYTES, mode="w+b")
        received_bytes = 0
        disconnected = False
        try:
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    disconnected = True
                    break
                if message["type"] != "http.request":
                    continue
                body = message.get("body", b"")
                received_bytes += len(body)
                if received_bytes > limit:
                    await self._reject(
                        scope,
                        receive,
                        send,
                        status_code=413,
                        message=self._limit_message(limit),
                    )
                    return
                spool.write(body)
                if not message.get("more_body", False):
                    break

            spool.seek(0)
            replay_finished = False

            async def replay_receive() -> Message:
                nonlocal replay_finished
                if disconnected or replay_finished:
                    return {"type": "http.disconnect"}
                chunk = spool.read(_REPLAY_CHUNK_BYTES)
                if chunk:
                    more_body = spool.tell() < received_bytes
                    replay_finished = not more_body
                    return {
                        "type": "http.request",
                        "body": chunk,
                        "more_body": more_body,
                    }
                replay_finished = True
                return {"type": "http.request", "body": b"", "more_body": False}

            await self.app(scope, replay_receive, send)
        finally:
            spool.close()

    @staticmethod
    def _limit_message(limit: int) -> str:
        return f"Skill request body exceeds {limit} bytes"

    @staticmethod
    async def _reject(
        scope: Scope,
        receive: Receive,
        send: Send,
        *,
        status_code: int,
        message: str,
    ) -> None:
        response = JSONResponse(
            status_code=status_code,
            content={"code": status_code, "message": message, "data": None},
        )
        await response(scope, receive, send)


# Compatibility import used by the application and earlier tests.
SkillDraftBodyLimitMiddleware = SkillRequestBodyLimitMiddleware
