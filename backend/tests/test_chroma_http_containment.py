from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.failed_response_register import register_exception_handlers
from app.db.db_config import get_db
from app.rag.vector_store import (
    CHROMA_PROJECTION_UNAVAILABLE_MESSAGE,
    ChromaProjectionUnavailable,
)
from app.router import knowledge_router as knowledge_router_module
from app.router import knowledge_service as knowledge_service_module
from app.router.chat import chat_router
from app.router.knowledge_router import get_knowledge_service, knowledge_router
from app.services.session_query_service import get_session_query_service
from app.utils.auth_utils import get_current_user_id


class _UnavailableVectorStore:
    def __init__(self, *args, **kwargs) -> None:
        raise ChromaProjectionUnavailable("internal quarantine details")


class _UnavailableRagQueryService:
    async def handle_rag_query(self, query: str, user_id: str) -> str:
        raise ChromaProjectionUnavailable("internal quarantine details")


def _build_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setattr(
        knowledge_service_module,
        "VectorStoreService",
        _UnavailableVectorStore,
    )
    monkeypatch.setattr(
        knowledge_router_module,
        "VectorStoreService",
        _UnavailableVectorStore,
    )

    app = FastAPI()
    app.include_router(knowledge_router)
    app.include_router(chat_router)
    register_exception_handlers(app)

    async def fake_user() -> str:
        return "e1-user"

    async def fake_db() -> object:
        return object()

    app.dependency_overrides[get_current_user_id] = fake_user
    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_session_query_service] = _UnavailableRagQueryService
    return app


@pytest.mark.parametrize(
    ("method", "path", "request_kwargs"),
    [
        (
            "POST",
            "/knowledge/add/single",
            {"files": {"file": ("doc.txt", b"fixture", "text/plain")}},
        ),
        (
            "POST",
            "/knowledge/add/multiple",
            {"files": [("files", ("doc.txt", b"fixture", "text/plain"))]},
        ),
        (
            "POST",
            "/knowledge/add/multiple/stream",
            {"files": [("files", ("doc.txt", b"fixture", "text/plain"))]},
        ),
        ("DELETE", "/knowledge/clean", {}),
        ("DELETE", "/knowledge/md5/clear", {}),
        ("DELETE", "/knowledge/md5/delete/fixture-md5", {}),
        ("DELETE", "/knowledge/delete/filename?filename=doc.txt", {}),
        ("GET", "/knowledge/md5/list", {}),
        ("GET", "/knowledge/md5/fixture-md5", {}),
        (
            "POST",
            "/knowledge/embedding/switch",
            {"json": {"model_name": "fixture-model"}},
        ),
        ("GET", "/knowledge/detail?filename=doc.txt", {}),
        ("GET", "/knowledge/chunks?filename=doc.txt", {}),
        ("POST", "/chat/rag/query", {"json": {"query": "fixture"}}),
    ],
)
def test_chroma_dependent_http_routes_return_stable_503(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    request_kwargs: dict,
) -> None:
    app = _build_app(monkeypatch)

    with TestClient(app) as client:
        response = client.request(method, path, **request_kwargs)

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {
        "code": 503,
        "message": CHROMA_PROJECTION_UNAVAILABLE_MESSAGE,
        "data": None,
    }


def test_source_list_remains_available_without_chroma(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _build_app(monkeypatch)

    class _SourceOnlyKnowledgeService:
        async def handle_get_user_knowledge(self, user_id: str, db: object) -> list:
            return []

    app.dependency_overrides[get_knowledge_service] = _SourceOnlyKnowledgeService
    with TestClient(app) as client:
        response = client.get("/knowledge/list")

    assert response.status_code == 200
    assert response.json()["data"] == {"documents": [], "total_count": 0}


def test_chroma_dependent_routes_publish_503_in_openapi() -> None:
    from main import app

    schema = app.openapi()
    operations: list[tuple[str, dict]] = [
        ("POST /knowledge/add/single", schema["paths"]["/knowledge/add/single"]["post"]),
        ("POST /knowledge/add/multiple", schema["paths"]["/knowledge/add/multiple"]["post"]),
        (
            "POST /knowledge/add/multiple/stream",
            schema["paths"]["/knowledge/add/multiple/stream"]["post"],
        ),
        ("DELETE /knowledge/clean", schema["paths"]["/knowledge/clean"]["delete"]),
        ("GET /knowledge/md5/list", schema["paths"]["/knowledge/md5/list"]["get"]),
        ("POST /knowledge/embedding/switch", schema["paths"]["/knowledge/embedding/switch"]["post"]),
        ("GET /knowledge/detail", schema["paths"]["/knowledge/detail"]["get"]),
        ("GET /knowledge/chunks", schema["paths"]["/knowledge/chunks"]["get"]),
        ("POST /chat/rag/query", schema["paths"]["/chat/rag/query"]["post"]),
    ]

    for label, operation in operations:
        unavailable = operation["responses"]["503"]
        assert unavailable["description"] == CHROMA_PROJECTION_UNAVAILABLE_MESSAGE, label
        assert "ApiResponse" in unavailable["content"]["application/json"]["schema"]["$ref"], label

    assert "503" not in schema["paths"]["/knowledge/list"]["get"]["responses"]
