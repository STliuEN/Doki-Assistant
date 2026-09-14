"""Actual application routers, local Ollama and replica-only SQL fault recovery."""

import argparse
import asyncio
import base64
import hashlib
import io
import json
import os
import secrets
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))


async def run(directory):
    import httpx
    from fastapi import FastAPI
    from PIL import Image
    from sqlalchemy import select

    from app.core.business_boundary import BusinessBoundaryMiddleware
    from app.core.failed_response_register import register_exception_handlers
    from app.db.db_config import AsyncSessionLocal, async_engine, verify_database_schema
    from app.models.chat_history import ChatMessage, ChatSession
    from app.models.skill_domain import SkillRunBinding
    from app.router.chat import chat_router
    from app.router.knowledge_router import knowledge_router
    from app.router.note_router import note_router
    from app.router.skill_router import skill_router
    from app.router.user import user_router
    from ops.e5.verify_closure import protected_state
    from ops.e6_e7.acceptance_env import docker, environment, save

    await verify_database_schema()
    app = FastAPI()
    app.add_middleware(BusinessBoundaryMiddleware)
    register_exception_handlers(app)
    for router in (user_router, chat_router, skill_router, knowledge_router, note_router):
        app.include_router(router)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    before = protected_state()
    report = {"stage": "E6E7", "transport": "httpx-ASGI-real-routers-real-SQL", "model": "local-Ollama-qwen3:0.6b", "checks": []}

    def check(name, **facts):
        report["checks"].append({"case": name, "passed": True, **facts})
        save(directory / "http-closure-progress.json", report)
        print(name + ": passed", flush=True)

    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1", timeout=180) as client:
        identities = []
        for suffix in ("media", "note"):
            username = "e6e7-http-" + suffix + "-" + uuid4().hex[:8]
            password = secrets.token_urlsafe(20)
            response = await client.post(
                "/user/register/",
                json={"username": username, "email": username + "@local.invalid", "password": password, "confirm_password": password},
            )
            assert response.status_code == 200, (response.status_code, response.json().get("message"))
            response = await client.post("/user/login/", json={"username": username, "password": password})
            assert response.status_code == 200
            data = response.json()["data"]
            identities.append({"username": username, "password": password, "user_id": data["user"]["id"], "token": data["token"]})
        save(directory / "http-identities.private.json", identities)
        media_user, note_user = identities
        headers = {"Authorization": "Bearer " + media_user["token"]}
        other_headers = {"Authorization": "Bearer " + note_user["token"]}
        check("HTTP register and password login for two isolated users")

        buffer = io.BytesIO()
        Image.new("RGB", (31, 23), (201, 52, 88)).save(buffer, format="PNG")
        image = buffer.getvalue()
        content = b"# HTTP SQL image\n![image](data:image/png;base64," + base64.b64encode(image) + b")\n"
        response = await client.post(
            "/knowledge/add/multiple/stream", headers=headers, files=[("files", ("http-closure.md", content, "text/markdown"))]
        )
        assert response.status_code == 200 and "text/event-stream" in response.headers["content-type"], response.status_code
        accepted = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        assert any(item.get("event_type") == "accepted" for item in accepted), accepted
        md5 = hashlib.md5(content).hexdigest()
        response = await client.get(f"/knowledge/image/{md5}/embedded-1.png", headers=headers)
        assert response.status_code == 200 and response.content == image
        batch = await client.get("/knowledge/images/all/" + md5, headers=headers)
        assert batch.status_code == 200 and batch.json()["data"]["total"] == 1
        denied = await client.get(f"/knowledge/image/{md5}/embedded-1.png", headers=other_headers)
        assert denied.status_code == 404
        check("HTTP upload SSE accepted then SQL image and batch access; cross-user 404", image_md5=md5)

        response = await client.post(
            "/note/create",
            headers=other_headers,
            json={"title": "E6E7 HTTP acceptance", "content": "Note written through real HTTP router", "tags": [], "category": "acceptance"},
        )
        assert response.status_code == 200, (response.status_code, response.json().get("message"))
        note_id = response.json()["data"]["id"]
        listing = await client.get("/note/list", headers=other_headers)
        assert any(item["id"] == note_id for item in listing.json()["data"]["notes"])
        check("HTTP note creation and owner-scoped list", note_id=note_id)

        session_id = str(uuid4())
        response = await client.post(
            "/chat/agent/query/stream",
            headers=headers,
            json={
                "session_id": session_id,
                "query": "Use what_time_is_now once and reply briefly with the returned current time. /no_think",
                "skill_ids": ["system_context"],
                "tool_ids": ["current_time"],
            },
        )
        assert response.status_code == 200, (response.status_code, response.text[:300])
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        save(directory / "http-sse-events.json", events)
        assert not any(event.get("type") == "error" or event.get("event_type") == "error" for event in events), "Chat SSE error"
        async with AsyncSessionLocal() as db:
            binding = await db.scalar(select(SkillRunBinding).where(SkillRunBinding.session_id == session_id))
            assert binding and binding.user_id == media_user["user_id"] and binding.skill_bindings
            session = await db.get(ChatSession, session_id)
            assert session and session.canonical_user_id == media_user["user_id"]
            messages = list(await db.scalars(select(ChatMessage).where(ChatMessage.session_id == session_id)))
            assert len(messages) >= 2 and any(row.role == "assistant" and row.content for row in messages)
        check("local-model chat SSE persists owner session messages and authorized RunBinding", session_id=session_id, event_count=len(events))
        denied_session = await client.post(
            "/chat/agent/query/stream",
            headers=other_headers,
            json={
                "session_id": session_id,
                "query": "Do not access another user's session",
                "skill_ids": ["system_context"],
                "tool_ids": ["current_time"],
            },
        )
        assert denied_session.status_code == 403
        check("first-turn session transaction rejects cross-owner reuse", denied_status=403)

        private = json.loads((directory / "credentials.private.json").read_text(encoding="utf-8"))
        environment(directory)
        await async_engine.dispose()
        stopped = False
        try:
            await asyncio.to_thread(docker, "stop", "--time", "10", private["container"])
            stopped = True
            response = await client.get(f"/knowledge/image/{md5}/embedded-1.png", headers=headers)
            assert response.status_code == 500 and response.json().get("data") is None
            core = await client.get("/chat/prompt-modes")
            assert core.status_code == 200
            check("replica SQL unavailable fails closed without image fallback; process route survives", protected_image_status=500)
        finally:
            if stopped:
                await asyncio.to_thread(docker, "start", private["container"])
                for _ in range(60):
                    try:
                        await asyncio.to_thread(
                            docker,
                            "exec",
                            "--env",
                            "MYSQL_PWD",
                            private["container"],
                            "mysql",
                            "--protocol=TCP",
                            "-h127.0.0.1",
                            "-u" + private["username"],
                            "-NBe",
                            "SELECT 1",
                            env=dict(os.environ, MYSQL_PWD=private["password"]),
                        )
                        break
                    except RuntimeError:
                        await asyncio.sleep(1)
                else:
                    raise RuntimeError("Acceptance replica restart timed out")
        response = await client.get(f"/knowledge/image/{md5}/embedded-1.png", headers=headers)
        assert response.status_code == 200 and response.content == image, (response.status_code, response.text[:150])
        assert protected_state() == before
        check("replica restart restores authenticated image access; new-api unchanged")
        report.update(status="passed", new_api_before=before, new_api_after=protected_state())
        save(directory / "http-closure.json", report)
    await async_engine.dispose()


def main():
    from ops.e6_e7.acceptance_env import preflight

    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    os.environ.update(preflight(directory, ("runtime", "validate")))
    os.environ.update(
        AUTH_JWT_SECRET=secrets.token_hex(32),
        DEBUG_MODE="false",
        E4_RUNNER_ENABLED="false",
        LLM_TYPE="OLLAMA",
        OLLAMA_MODEL_NAME="qwen3:0.6b",
        REDIS_HOST="127.0.0.1",
        REDIS_PORT="18020",
        REDIS_DB="4",
        RATE_LIMIT_ENABLED="false",
        SKILL_STORAGE_DIR=str(directory / "absent-legacy-packages"),
    )
    asyncio.run(run(directory))


if __name__ == "__main__":
    main()
