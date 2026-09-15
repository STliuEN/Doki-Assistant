"""E8 smoke against the already running Doki current migrated target."""

import argparse
import json
import secrets
from pathlib import Path

import httpx


def main(directory: Path):
    c = httpx.Client(base_url="http://127.0.0.1:18000", trust_env=False, timeout=180)
    user = "e8-live-" + secrets.token_hex(4)
    password = secrets.token_urlsafe(20)
    checks = []

    def check(name, response, expected=200):
        assert response.status_code == expected, (name, response.status_code, response.text[:500])
        checks.append({"case": name, "passed": True, "http": response.status_code})
        if not response.content or "text/event-stream" in response.headers.get("content-type", ""):
            return None
        return response.json().get("data")

    check(
        "register",
        c.post("/user/register/", json={"username": user, "email": user + "@local.invalid", "password": password, "confirm_password": password}),
    )
    data = check("login", c.post("/user/login/", json={"username": user, "password": password}))
    c.headers["Authorization"] = "Bearer " + data["token"]
    check("session query", c.get("/user/sessions/"))
    catalog_response = c.get("/skills/catalog")
    check("Skill catalog", catalog_response)
    check("RAG status", c.get("/knowledge/rag/status"))
    check("readiness", c.get("/health/ready"))
    note = check(
        "note create", c.post("/note/create", json={"title": "E8 live smoke", "content": "Current target SQL smoke", "tags": [], "category": "e8"})
    )
    listing = check("note list", c.get("/note/list"))
    assert any(row["id"] == note["id"] for row in listing["notes"])
    exported = check("note export", c.get(f"/note/{note['id']}/export"))
    assert "E8 live smoke" in exported["markdown"]
    sid = secrets.token_hex(16)
    response = c.post(
        "/chat/agent/query/stream",
        json={
            "session_id": sid,
            "query": "Use what_time_is_now once and reply briefly. /no_think",
            "skill_ids": ["system_context"],
            "tool_ids": ["current_time"],
        },
    )
    check("chat SSE", response)
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert events and not any(e.get("type") == "error" or e.get("event_type") == "error" for e in events)
    checks[-1]["event_count"] = len(events)
    report = {
        "stage": "E8",
        "transport": "live-http-real-Doki-real-SQL",
        "status": "passed",
        "checks": checks,
        "user": "ephemeral",
        "session_id": sid,
    }
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "business-smoke.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "passed", "checks": len(checks)}))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("directory", type=Path)
    a = p.parse_args()
    main(a.directory.resolve())
