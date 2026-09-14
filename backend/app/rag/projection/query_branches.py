"""Query-only enrichment branches for the E5 projection."""

import math
import re

import httpx

from app.rag.projection.contracts import Chunk, Hit, ProjectionUnavailable


def tokens(text: str) -> list[str]:
    return re.findall(r"[\u4e00-\u9fff]|[a-zA-Z0-9_]+", text.lower())


def bm25(chunks: list[Chunk], query: str, top_k: int) -> list[Hit]:
    if not chunks or not tokens(query):
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
    ranked = sorted(((chunks[index], float(value)) for index, value in enumerate(raw)), key=lambda item: (-item[1], item[0].id))
    return [Hit(chunk, (score - minimum) / scale if scale else 0.0, "") for chunk, score in ranked[:top_k]]


async def ollama_model_digest(base_url: str, model: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            response = await client.get(base_url.rstrip("/") + "/api/tags")
            response.raise_for_status()
            result = next(item["digest"] for item in response.json()["models"] if item["name"] in {model, model + ":latest"})
            if not re.fullmatch(r"[a-f0-9]{64}", result):
                raise ValueError("Missing immutable model identity")
            return result
    except Exception as error:
        raise ProjectionUnavailable("hyde_model_unavailable") from error


async def bind_query_models(config: dict, base_url: str, *, verify=True) -> dict:
    from app.rag.projection.local_reranker import model_fingerprint
    value = dict(config)
    for enabled, name, key in (("hyde", "hyde_model", "hyde_model_digest"), ("rerank", "reranker_model", "reranker_model_digest")):
        if not value[enabled]:
            continue
        actual = (await ollama_model_digest(base_url, value[name])) if enabled == "hyde" else (await model_fingerprint(value[name]))["digest"]
        if verify and value.get(key) and value[key] != actual:
            raise ProjectionUnavailable(enabled + "_model_changed")
        value[key] = actual
    return value


async def hyde(query: str, *, base_url: str, model: str = "qwen3:0.6b", expected_digest: str | None = None) -> str:
    prompt = "根据用户问题写一段用于检索的简短假设性答案，只输出答案正文，不要解释过程。\n用户问题：" + query
    try:
        if expected_digest and await ollama_model_digest(base_url, model) != expected_digest:
            raise ProjectionUnavailable("hyde_model_changed")
        async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
            response = await client.post(
                base_url.rstrip("/") + "/api/generate",
                json={"model": model, "prompt": prompt, "stream": False, "think": False,
                      "options": {"temperature": 0, "seed": 0, "num_predict": 256}},
            )
            response.raise_for_status()
            value = response.json().get("response")
            if not isinstance(value, str) or not value.strip():
                raise ValueError("empty HyDE response")
            if expected_digest and await ollama_model_digest(base_url, model) != expected_digest:
                raise ProjectionUnavailable("hyde_model_changed")
            return value.strip()
    except ProjectionUnavailable:
        raise
    except Exception as error:
        raise ProjectionUnavailable("hyde_unavailable") from error


async def rerank(hits: list[Hit], query: str, *, model_name: str = "qwen3-reranker-4b", expected_digest: str | None = None) -> list[Hit]:
    if not hits:
        return []
    try:
        from app.rag.projection.local_reranker import score
        scores = await score(query, [hit.chunk.text for hit in hits], model_name=model_name, expected_digest=expected_digest)
        if len(scores) != len(hits) or any(not math.isfinite(value) for value in scores):
            raise ValueError("reranker returned invalid scores")
        return sorted([Hit(hit.chunk, value, hit.generation) for hit, value in zip(hits, scores)], key=lambda hit: (-hit.score, hit.chunk.id))
    except ProjectionUnavailable:
        raise
    except Exception as error:
        raise ProjectionUnavailable("reranker_unavailable") from error
