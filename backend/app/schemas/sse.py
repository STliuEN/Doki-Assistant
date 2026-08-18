import json
from typing import Any

from pydantic import BaseModel, ConfigDict

SSE_SCHEMA_VERSION = "1.0"
SSE_OPENAPI_RESPONSE = {
    200: {
        "description": "Versioned Server-Sent Events stream",
        "content": {
            "text/event-stream": {
                "schema": {"type": "string"},
                "example": (
                    'data: {"schema_version":"1.0","type":"response",'
                    '"content":"hello"}\n\n'
                ),
            }
        },
    }
}


class SSEEventEnvelope(BaseModel):
    """Shared, backward-compatible SSE contract.

    Event-specific fields remain at the top level for existing clients. New
    clients can gate parsing on ``schema_version``.
    """

    model_config = ConfigDict(extra="allow")

    schema_version: str = SSE_SCHEMA_VERSION
    type: str | None = None
    event_type: str | None = None
    content: str | None = None
    session_id: str | None = None


def encode_sse(payload: dict[str, Any], *, event: str | None = None) -> str:
    normalized = {**payload, "schema_version": SSE_SCHEMA_VERSION}
    prefix = f"event: {event}\n" if event else ""
    return f"{prefix}data: {json.dumps(normalized, ensure_ascii=False)}\n\n"
