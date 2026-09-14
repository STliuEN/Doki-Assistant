import asyncio
import sys
from types import ModuleType

from app.rag.projection.contracts import Chunk, Hit
from app.rag.projection.query_branches import bm25, hyde, rerank


def chunks():
    return [
        Chunk("a", "系统架构与数据库设计", "source-a", "digest-a", "knowledge", 0),
        Chunk("b", "今天的天气和通勤安排", "source-b", "digest-b", "notes", 0),
    ]


def test_bm25_uses_live_chunk_text_and_returns_ranked_hits():
    result = bm25(chunks(), "数据库设计", 2)
    assert result[0].chunk.id == "a"
    assert all(hit.generation == "" for hit in result)


def test_hyde_calls_ollama_generate(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"response": "数据库架构与索引优化"}

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def post(self, url, **kwargs):
            assert url.endswith("/api/generate") and kwargs["json"]["stream"] is False
            return Response()

    monkeypatch.setattr("app.rag.projection.query_branches.httpx.AsyncClient", Client)
    assert asyncio.run(hyde("如何设计数据库", base_url="http://ollama")) == "数据库架构与索引优化"


def test_rerank_preserves_chunk_identity(monkeypatch):
    module = ModuleType("app.rag.reorder_service")

    class Service:
        async def reorder_documents(self, _query, documents):
            return {"success": True, "documents": [{"document": documents[1], "similarity": 0.9}, {"document": documents[0], "similarity": 0.1}]}

    module.ReorderService = Service
    monkeypatch.setitem(sys.modules, "app.rag.reorder_service", module)
    hits = [Hit(chunks()[0], 0.2, "generation"), Hit(chunks()[1], 0.3, "generation")]
    result = asyncio.run(rerank(hits, "query"))
    assert [hit.chunk.id for hit in result] == ["b", "a"]
    assert [hit.generation for hit in result] == ["generation", "generation"]
