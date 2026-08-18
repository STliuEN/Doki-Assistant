import inspect
import json

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.core.success_response import success_response
from app.rag.sse_models import SSEEvent
from app.schemas.api import ApiResponse
from app.schemas.models import RAGResponse
from app.schemas.sse import SSE_SCHEMA_VERSION, encode_sse


def _sse_payload(value: str) -> dict:
    data_line = next(line for line in value.splitlines() if line.startswith("data: "))
    return json.loads(data_line.removeprefix("data: "))


def test_api_response_serializes_the_runtime_envelope() -> None:
    response = success_response(data=RAGResponse(response="ok"))

    assert isinstance(response, ApiResponse)
    assert response.model_dump(mode="json") == {
        "code": 200,
        "message": "success",
        "data": {"response": "ok"},
    }


def test_openapi_uses_the_envelope_for_declared_json_routes() -> None:
    from main import app

    schema = app.openapi()
    response_schema = schema["paths"]["/chat/rag/query"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]

    assert "ApiResponse" in response_schema["$ref"]


def test_real_fastapi_response_matches_the_published_envelope() -> None:
    from main import app

    client = TestClient(app)
    try:
        response = client.get("/chat/prompt-modes")
    finally:
        client.close()

    assert response.status_code == 200
    assert response.json().keys() == {"code", "message", "data"}
    assert response.json()["code"] == 200
    assert isinstance(response.json()["data"], list)


@pytest.mark.parametrize("origins", [[], ["*"]])
def test_production_rejects_missing_or_wildcard_cors(origins: list[str]) -> None:
    from main import _validate_cors_origins

    with pytest.raises(RuntimeError, match="explicit CORS_ALLOWED_ORIGINS"):
        _validate_cors_origins("production", origins)


def test_all_canonical_json_handlers_publish_the_envelope_in_openapi() -> None:
    from main import app

    schema = app.openapi()
    missing: list[str] = []

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if "success_response(" not in inspect.getsource(route.endpoint):
            continue
        for method in route.methods - {"HEAD", "OPTIONS"}:
            operation = schema["paths"][route.path][method.lower()]
            status_code = str(route.status_code or 200)
            response_schema = (
                operation["responses"]
                .get(status_code, {})
                .get("content", {})
                .get("application/json", {})
                .get("schema", {})
            )
            if "ApiResponse" not in json.dumps(response_schema):
                missing.append(f"{method} {route.path}")

    assert not missing, f"JSON handlers missing ApiResponse OpenAPI schemas: {missing}"


def test_all_sse_routes_publish_the_versioned_stream_contract() -> None:
    from main import app

    schema = app.openapi()
    sse_operations = {
        ("/chat/agent/query/stream", "post"),
        ("/chat/agent/confirm", "post"),
        ("/chat/session/{session_id}/messages/{message_id}/regenerate/stream", "post"),
        ("/knowledge/add/multiple/stream", "post"),
        ("/note/assist/stream", "post"),
        ("/translate/dialogue/stream", "post"),
    }

    for path, method in sse_operations:
        content = schema["paths"][path][method]["responses"]["200"]["content"]
        assert "text/event-stream" in content
        assert SSE_SCHEMA_VERSION in content["text/event-stream"]["example"]

    sse_paths = {path for path, _ in sse_operations}
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path in sse_paths:
            assert "Access-Control-Allow-Origin" not in inspect.getsource(route.endpoint)


def test_sse_encoder_adds_a_stable_schema_version() -> None:
    payload = _sse_payload(
        encode_sse(
            {
                "schema_version": "caller-controlled",
                "type": "response",
                "content": "hello",
            }
        )
    )

    assert payload["schema_version"] == SSE_SCHEMA_VERSION
    assert payload["type"] == "response"


def test_knowledge_progress_uses_the_same_sse_version() -> None:
    payload = _sse_payload(SSEEvent(event_type="start", message="starting").to_sse())

    assert payload["schema_version"] == SSE_SCHEMA_VERSION
    assert payload["event_type"] == "start"
