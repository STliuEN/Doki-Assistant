"""Query-only enrichment branches for the E5 projection."""

import re

import httpx

from app.rag.projection.contracts import Chunk, Hit, ProjectionUnavailable


def tokens(text: str) -> list[str]:
    return re.findall(r"[\u4e00-\u9fff]|[a-zA-Z0-9_]+", text.lower())


def bm25(chunks: list[Chunk], query: str, top_k: int) -> list[Hit]:
    if not chunks:
        return []
    try:
        from rank_bm25 import BM25Okapi
        engine = BM25Okapi([tokens(chunk.text) for chunk in chunks])
        raw = engine.get_scores(tokens(query))
    except Exception as error:
        raise ProjectionUnavailable("bm25_unavailable") from error
    if not len(raw):
        return []
    maximum = max(float(value) for value in raw)
    minimum = min(float(value) for value in raw)
    scale = maximum - minimum
    ranked = sorted(((chunks[index], float(value)) for index, value in enumerate(raw)), key=lambda item: item[1], reverse=True)
    return [Hit(chunk, (score - minimum) / scale if scale else 0.0, "") for chunk, score in ranked[:top_k]]


async def hyde(query: str, *, base_url: str, model: str = "qwen3:0.6b") -> str:
    prompt = "根据用户问题写一段用于检索的简短假设性答案，只输出答案正文，不要解释过程。\n用户问题：" + query
    try:
        async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
            response = await client.post(
                base_url.rstrip("/") + "/api/generate",
                json={"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0}},
            )
            response.raise_for_status()
            value = response.json().get("response")
            if not isinstance(value, str) or not value.strip():
                raise ValueError("empty HyDE response")
            return value.strip()
    except Exception as error:
        raise ProjectionUnavailable("hyde_unavailable") from error


async def rerank(hits: list[Hit], query: str, *, model_path: str | None = None) -> list[Hit]:
    if not hits:
        return []
    try:
        from app.rag.reorder_service import ReorderService
        service = ReorderService()
        if model_path:
            service.LOCAL_MODEL_PATH = model_path
        result = await service.reorder_documents(query, [hit.chunk.text for hit in hits])
        if not result.get("success") or len(result.get("documents", [])) != len(hits):
            raise ValueError(result.get("error") or "reranker returned incomplete result")
        buckets: dict[str, list[Hit]] = {}
        for hit in hits:
            buckets.setdefault(hit.chunk.text, []).append(hit)
        ranked: list[Hit] = []
        for value in result["documents"]:
            text = value.get("document", "")
            if not buckets.get(text):
                raise ValueError("reranker returned unknown document")
            original = buckets[text].pop(0)
            ranked.append(Hit(original.chunk, float(value["similarity"]), original.generation))
        return ranked
    except ProjectionUnavailable:
        raise
    except Exception as error:
        raise ProjectionUnavailable("reranker_unavailable") from error
