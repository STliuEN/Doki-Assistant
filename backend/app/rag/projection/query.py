"""SQL-authorized retrieval with a fresh final visibility check."""

import asyncio
import math

from app.rag.projection.chroma_adapter import ChromaProjectionAdapter
from app.rag.projection.contracts import Hit, ProjectionUnavailable, QueryConfig, RetrievalResult
from app.rag.projection.embedding import embedding_fingerprint, embedding_model, model_snapshot
from app.rag.projection.query_branches import bind_query_models, bm25, hyde, rerank
from app.rag.projection.snapshot import assert_current, read_snapshot, reader_factory
from app.rag.projection.sources import split_sources


def rank_key(hit):
    return (-hit.score, hit.chunk.index_kind, hit.chunk.source_id, hit.chunk.position, hit.chunk.id)


async def query_user(session, owner: str, query: str, *, query_config_override: dict | None = None) -> RetrievalResult:
    factory = reader_factory(session)
    snapshot = await read_snapshot(factory, owner)
    try:
        config = QueryConfig.model_validate({**snapshot.query, **(query_config_override or {})}).model_dump()
    except Exception as error:
        raise ProjectionUnavailable("query_config_invalid") from error
    embedding = await model_snapshot(snapshot.embedding)
    fingerprint = embedding_fingerprint(embedding)
    expected = await asyncio.to_thread(split_sources, snapshot.sources, snapshot.index)
    if any(expected.values()):
        config = await bind_query_models(config, embedding["base_url"])
    adapter = ChromaProjectionAdapter(embedding_model)
    generations = {kind: item["generation"] for kind, item in snapshot.artifacts.items()}
    # Validate both indexes even when notes are not included in the answer.
    for kind, artifact in snapshot.artifacts.items():
        if embedding_fingerprint(artifact["embedding"]) != fingerprint:
            raise ProjectionUnavailable("rag_embedding_changed")
        if len(expected[kind]) != artifact["chunk_count"]:
            raise ProjectionUnavailable("rag_chunk_count_changed")
        await adapter.validate(collection=artifact["collection"], owner=owner, generation=artifact["generation"],
                               chunks=expected[kind], receipt=artifact["receipt"])
    retrieval_query = await hyde(query, base_url=embedding["base_url"], model=config["hyde_model"],
                                 expected_digest=config["hyde_model_digest"]) if config["hyde"] and any(expected.values()) else query
    authoritative = {chunk.id: chunk for items in expected.values() for chunk in items}
    allowed = set(config["source_ids"])

    def authorize(chunk):
        if authoritative.get(chunk.id) != chunk:
            raise ProjectionUnavailable("rag_candidate_invalid")
        return not allowed or chunk.source_id in allowed

    hits = []
    lexical_chunks = []
    for kind, artifact in snapshot.artifacts.items():
        if kind == "notes" and not config["notes"]:
            continue
        vector_hits = await adapter.query(collection=artifact["collection"], owner=owner, generation=artifact["generation"],
                                          query=retrieval_query, embedding=embedding, top_k=config["top_k"] * 3)
        for hit in vector_hits:
            if hit.generation != artifact["generation"] or hit.chunk.index_kind != kind or not math.isfinite(hit.score):
                raise ProjectionUnavailable("rag_candidate_invalid")
            if authorize(hit.chunk):
                hits.append(hit)
        if config["bm25"]:
            candidates = await adapter.chunks(collection=artifact["collection"], owner=owner, generation=artifact["generation"])
            for chunk in candidates:
                if chunk.index_kind != kind:
                    raise ProjectionUnavailable("rag_candidate_invalid")
                if authorize(chunk):
                    lexical_chunks.append(chunk)
    if config["bm25"]:
        lexical = await asyncio.to_thread(bm25, sorted(lexical_chunks, key=lambda c: c.id), retrieval_query, config["top_k"] * 3)
        vector_scores = {hit.chunk.id: hit.score for hit in hits}
        lexical_scores = {hit.chunk.id: hit.score for hit in lexical}
        hits = [Hit(authoritative[key], 0.7 * vector_scores.get(key, 0.0) + 0.3 * lexical_scores.get(key, 0.0),
                    generations[authoritative[key].index_kind]) for key in sorted(set(vector_scores) | set(lexical_scores))]
    hits.sort(key=rank_key)
    if config["rerank"]:
        hits = await rerank(hits[:config["top_k"] * 3], query, model_name=config["reranker_model"], expected_digest=config["reranker_model_digest"])
    for hit in hits:
        if not authorize(hit.chunk) or hit.generation != generations.get(hit.chunk.index_kind) or not math.isfinite(hit.score):
            raise ProjectionUnavailable("rag_candidate_invalid")
    hits = sorted(hits, key=rank_key)[:config["top_k"]]
    if embedding_fingerprint(await model_snapshot(snapshot.embedding)) != fingerprint:
        raise ProjectionUnavailable("rag_embedding_changed")
    await assert_current(factory, owner, snapshot)
    return RetrievalResult(documents=[hit.chunk.text for hit in hits], scores=[hit.score for hit in hits],
                           source_ids=[hit.chunk.source_id for hit in hits], generation=generations, hits=hits)
