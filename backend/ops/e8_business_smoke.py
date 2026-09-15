"""E8 business smoke on an isolated SQL fixture using the real FastAPI routers."""

import argparse
import asyncio
import json
import os
import secrets
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))


async def run(directory: Path):
    import httpx
    from fastapi import FastAPI

    from app.core.business_boundary import BusinessBoundaryMiddleware
    from app.core.failed_response_register import register_exception_handlers
    from app.db.db_config import async_engine, verify_database_schema
    from app.router.chat import chat_router
    from app.router.health import health_router
    from app.router.knowledge_router import knowledge_router
    from app.router.note_router import note_router
    from app.router.rag_router import rag_router
    from app.router.skill_router import skill_router
    from app.router.user import user_router
    from ops.e6_e7.acceptance_env import save

    await verify_database_schema()
    app = FastAPI()
    app.add_middleware(BusinessBoundaryMiddleware)
    register_exception_handlers(app)
    for router in (user_router, skill_router, knowledge_router, rag_router, chat_router, note_router, health_router):
        app.include_router(router)
    report = {"stage": "E8", "transport": "ASGI-real-routers-real-SQL", "checks": []}

    def check(name, **facts):
        report["checks"].append({"case": name, "passed": True, **facts})
        save(directory / "business-smoke-progress.json", report)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://e8.local", timeout=180) as c:
        username = "e8-smoke-" + secrets.token_hex(4)
        password = secrets.token_urlsafe(20)
        r = await c.post(
            "/user/register/", json={"username": username, "email": username + "@local.invalid", "password": password, "confirm_password": password}
        )
        assert r.status_code == 200, r.text
        r = await c.post("/user/login/", json={"username": username, "password": password})
        assert r.status_code == 200, r.text
        identity = r.json()["data"]
        c.headers["Authorization"] = "Bearer " + identity["token"]
        check("register and login", user_id=identity["user"]["id"])
        r = await c.get("/user/sessions/")
        assert r.status_code == 200
        check("session query")
        r = await c.get("/skills/catalog")
        assert r.status_code == 200
        skill_count = len(r.json()["data"]["skills"])
        check("Skill catalog", skill_count=skill_count)
        r = await c.get("/knowledge/rag/status")
        assert r.status_code == 200
        check("RAG status", status=r.json()["data"]["status"])
        r = await c.get("/health/ready")
        assert r.status_code == 200
        check("readiness", http=200)
        r = await c.post("/note/create", json={"title": "E8 smoke note", "content": "SQL authority smoke content", "tags": [], "category": "e8"})
        assert r.status_code == 200, r.text
        note_id = r.json()["data"]["id"]
        r = await c.get("/note/list")
        assert r.status_code == 200 and any(n["id"] == note_id for n in r.json()["data"]["notes"])
        check("note create and list", note_id=note_id)
        r = await c.get(f"/note/{note_id}/export")
        assert r.status_code == 200 and "E8 smoke note" in r.json()["data"]["markdown"]
        check("note export")
        session_id = str(uuid4())
        chat_payload = {"session_id": session_id, "query": "Reply briefly that the E8 empty fixture is reachable. /no_think"}
        if skill_count:
            chat_payload.update(skill_ids=["system_context"], tool_ids=["current_time"])
        r = await c.post("/chat/agent/query/stream", json=chat_payload)
        assert r.status_code == 200, r.text[:500]
        events = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]
        assert events and not any(e.get("type") == "error" or e.get("event_type") == "error" for e in events)
        check("chat SSE", session_id=session_id, event_count=len(events))
    await async_engine.dispose()
    report["status"] = "passed"
    save(directory / "business-smoke.json", report)
    print(json.dumps({"status": "passed", "checks": len(report["checks"])}))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("directory", type=Path)
    a = p.parse_args()
    d = a.directory.resolve()
    from ops.e6_e7.acceptance_env import preflight

    os.environ.update(preflight(d, ("runtime", "validate")))
    os.environ.update(
        E8_ENABLED="true",
        E6E7_ENABLED="true",
        E5_RAG_ENABLED="true",
        RATE_LIMIT_ENABLED="false",
        LLM_TYPE="OLLAMA",
        OLLAMA_MODEL_NAME="qwen3:0.6b",
        AUTH_JWT_SECRET=secrets.token_hex(32),
        SKILL_STORAGE_DIR=str(d / "absent-legacy-packages"),
    )
    asyncio.run(run(d))
