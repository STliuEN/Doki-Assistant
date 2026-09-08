import asyncio
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.business_boundary import BusinessBoundaryMiddleware
from app.db.business_authority import BUSINESS_ACTOR, BUSINESS_CORRELATION


def test_e4_retired_routes_and_request_context():
    async def scenario():
        app = FastAPI()
        app.add_middleware(BusinessBoundaryMiddleware)

        @app.post("/probe")
        async def probe():
            assert BUSINESS_ACTOR.get() is None
            assert BUSINESS_CORRELATION.get()
            BUSINESS_ACTOR.set("request-only")
            return {"ok": True}

        with patch("app.core.business_boundary.E4_PROCESS_ENVIRONMENT", {"E4_MIGRATION_ENABLED": "enabled"}):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                for path in ("/tools/new", "/mcp/servers", "/api/mcp/servers", "/knowledge/reranker/switch", "/knowledge/md5/clear"):
                    assert (await client.post(path)).status_code == 410
                assert (await client.post("/probe")).status_code == 200
                assert (await client.post("/probe")).status_code == 200
                assert BUSINESS_ACTOR.get() is None and BUSINESS_CORRELATION.get() is None
    asyncio.run(scenario())


def test_django_legacy_boundary_is_installed_and_blocks_business_routes():
    text = (Path(__file__).resolve().parents[2] / "DjangoUserService/DjangoUserService/settings.py").read_text(encoding="utf-8")
    assert "LegacyBusinessReadOnlyMiddleware" in text
    boundary = (Path(__file__).resolve().parents[2] / "DjangoUserService/DjangoUserService/legacy_boundary.py").read_text(encoding="utf-8")
    for route in ('"/user', '"/file', '"/admin'):
        assert route in boundary
