from __future__ import annotations

import asyncio

import pytest

from app.core.skill_body_limit import SkillDraftBodyLimitMiddleware


def _run_request(
    *,
    path: str,
    chunks: list[bytes],
    headers: list[tuple[bytes, bytes]],
    limit: int = 8,
) -> tuple[list[dict], dict[str, int | bool]]:
    messages = [
        {
            "type": "http.request",
            "body": chunk,
            "more_body": index < len(chunks) - 1,
        }
        for index, chunk in enumerate(chunks)
    ]
    state: dict[str, int | bool] = {"receive_calls": 0, "completed": False}
    sent: list[dict] = []

    async def receive():
        state["receive_calls"] = int(state["receive_calls"]) + 1
        if messages:
            return messages.pop(0)
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    async def downstream(_scope, downstream_receive, downstream_send):
        while True:
            message = await downstream_receive()
            if message["type"] != "http.request" or not message.get("more_body", False):
                break
        state["completed"] = True
        await downstream_send({"type": "http.response.start", "status": 204, "headers": []})
        await downstream_send({"type": "http.response.body", "body": b""})

    middleware = SkillDraftBodyLimitMiddleware(downstream, max_body_bytes=limit)
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST" if path.endswith("/drafts") or path.endswith("/imports") else "PUT",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers,
        "client": ("test", 1),
        "server": ("test", 80),
    }
    asyncio.run(middleware(scope, receive, send))
    return sent, state


@pytest.mark.parametrize("headers", [[], [(b"content-length", b"1")]])
def test_streamed_draft_body_limit_rejects_missing_or_forged_content_length(headers) -> None:
    sent, state = _run_request(
        path="/skills/example/draft",
        chunks=[b"12345", b"67890"],
        headers=headers,
    )

    assert sent[0]["status"] == 413
    assert state == {"receive_calls": 2, "completed": False}


def test_declared_oversize_is_rejected_without_reading_or_running_dependencies() -> None:
    sent, state = _run_request(
        path="/skills/drafts",
        chunks=[b"ignored"],
        headers=[(b"content-length", b"99")],
    )

    assert sent[0]["status"] == 413
    assert state == {"receive_calls": 0, "completed": False}


def test_skill_zip_multipart_import_is_outside_the_json_draft_cap() -> None:
    sent, state = _run_request(
        path="/skills/imports",
        chunks=[b"12345", b"67890"],
        headers=[],
    )

    assert sent[0]["status"] == 204
    assert state == {"receive_calls": 2, "completed": True}
