"""E4 request context and retirement of legacy filesystem write routes."""

from uuid import uuid4

from starlette.responses import JSONResponse

from app.core.e4_process_environment import E4_PROCESS_ENVIRONMENT
from app.db.business_authority import BUSINESS_ACTOR, BUSINESS_CORRELATION


class BusinessBoundaryMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not E4_PROCESS_ENVIRONMENT.get("E4_MIGRATION_ENABLED"):
            await self.app(scope, receive, send)
            return
        path = scope["path"].rstrip("/")
        write = scope["method"] not in {"GET", "HEAD", "OPTIONS"}
        blocked = path.startswith(("/tools", "/api/mcp", "/mcp")) or path == "/knowledge/reranker/switch" or path.startswith("/knowledge/md5")
        if write and blocked:
            response = JSONResponse(
                {"code": 410, "message": "Legacy filesystem/cache write route retired in E4", "data": None, "error_code": "E4_LEGACY_WRITE_RETIRED"},
                status_code=410,
            )
            await response(scope, receive, send)
            return
        actor_token = BUSINESS_ACTOR.set(None)
        correlation_token = BUSINESS_CORRELATION.set(str(uuid4()))
        try:
            await self.app(scope, receive, send)
        finally:
            BUSINESS_ACTOR.reset(actor_token)
            BUSINESS_CORRELATION.reset(correlation_token)
