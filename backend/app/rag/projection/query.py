"""User-scoped E5 query binding. It never falls back to legacy collections."""

from sqlalchemy import select

from app.models.embedding_config import UserEmbeddingConfig
from app.models.knowledge_document import KnowledgeSourceDocument
from app.models.note import Note
from app.models.projection_domain import RagGenerationHead
from app.models.rag_runtime import RagArtifact, RagUserState
from app.rag.projection.chroma_adapter import ChromaProjectionAdapter
from app.rag.projection.contracts import Hit, ProjectionUnavailable, RetrievalResult
from app.rag.projection.embedding import embedding_fingerprint, embedding_model, model_snapshot
from app.rag.projection.query_branches import bm25, hyde, rerank
from app.rag.projection.sources import digest, read_sources, source_manifest
from app.services.embedding_config_service import get_embedding_config_service


async def query_user(session, owner: str, query: str, *, query_config_override: dict | None = None) -> RetrievalResult:
    state = await session.get(RagUserState, owner)
    if state is None or state.status != "ready":
        raise ProjectionUnavailable("rag_rebuild_in_progress", job_id=state.job_id if state else None)
    query_config = {**state.query_config, **(query_config_override or {})}
    from app.rag.projection.contracts import QueryConfig
    try:
        query_config = QueryConfig.model_validate(query_config).model_dump()
    except Exception as error:
        raise ProjectionUnavailable("query_config_invalid") from error
    config_row = await session.scalar(select(UserEmbeddingConfig).where(UserEmbeddingConfig.canonical_user_id == owner))
    config = get_embedding_config_service().get_system_default(owner) if config_row is None else get_embedding_config_service()._to_data(config_row)
    config_value = await model_snapshot({name: getattr(config, name) for name in ("provider", "model_type", "model_name", "base_url")})
    current_manifest_digest = digest(source_manifest(await read_sources(session, owner)))
    current_embedding_fingerprint = embedding_fingerprint(config_value)
    if state.source_digest != current_manifest_digest:
        raise ProjectionUnavailable("rag_source_changed")
    adapter = ChromaProjectionAdapter(embedding_model)
    retrieval_query = query
    if query_config["hyde"]:
        retrieval_query = await hyde(query, base_url=config_value["base_url"])
    hits = []
    branch_chunks = []
    generations = {}
    for kind in ("knowledge", "notes"):
        if kind == "notes" and not query_config["notes"]:
            continue
        head = await session.scalar(select(RagGenerationHead).where(
            RagGenerationHead.owner_scope_type == "user",
            RagGenerationHead.owner_scope_id == owner,
            RagGenerationHead.index_kind == kind,
        ))
        if head is None or head.active_generation_id is None:
            raise ProjectionUnavailable("rag_generation_missing")
        artifact = await session.get(RagArtifact, head.active_generation_id)
        if artifact is None:
            raise ProjectionUnavailable("rag_artifact_missing")
        if artifact.manifest_digest != current_manifest_digest:
            raise ProjectionUnavailable("rag_artifact_stale")
        if (
            artifact.embedding_config
            and embedding_fingerprint(artifact.embedding_config) != current_embedding_fingerprint
        ):
            raise ProjectionUnavailable("rag_embedding_changed")
        generations[kind] = str(head.active_generation_id)
        vector_hits = await adapter.query(
            collection=artifact.collection_name, owner=owner, generation=str(head.active_generation_id),
            query=retrieval_query, embedding=config_value, top_k=int(query_config["top_k"] * 3),
        )
        hits.extend(vector_hits)
        if query_config["bm25"]:
            branch_chunks.extend(await adapter.chunks(
                collection=artifact.collection_name, owner=owner, generation=str(head.active_generation_id)))
    knowledge_ids = await session.scalars(
        select(KnowledgeSourceDocument.canonical_id).where(
            KnowledgeSourceDocument.canonical_user_id == owner,
            KnowledgeSourceDocument.status != "excluded",
        )
    )
    note_ids = await session.scalars(
        select(Note.canonical_id).where(Note.canonical_user_id == owner)
    )
    valid_ids = {str(value) for value in knowledge_ids if value}
    valid_ids.update(str(value) for value in note_ids if value)
    hits = [hit for hit in hits if hit.chunk.source_id in valid_ids]
    if query_config["source_ids"]:
        allowed = set(query_config["source_ids"])
        hits = [hit for hit in hits if hit.chunk.source_id in allowed]
        branch_chunks = [chunk for chunk in branch_chunks if chunk.source_id in allowed]
    if query_config["bm25"]:
        bm25_hits = bm25(branch_chunks, retrieval_query, int(query_config["top_k"] * 3))
        vector_scores = {item.chunk.id: item.score for item in hits}
        lexical_scores = {item.chunk.id: item.score for item in bm25_hits}
        combined_ids = set(vector_scores) | set(lexical_scores)
        by_id = {item.chunk.id: item for item in hits}
        for candidate in bm25_hits:
            candidate = Hit(candidate.chunk, candidate.score, generations.get(candidate.chunk.index_kind, ""))
            by_id.setdefault(candidate.chunk.id, candidate)
        hits = [
            Hit(by_id[chunk_id].chunk, 0.7 * vector_scores.get(chunk_id, 0.0) + 0.3 * lexical_scores.get(chunk_id, 0.0), by_id[chunk_id].generation)
            for chunk_id in combined_ids
        ]
    if query_config["rerank"]:
        hits = await rerank(hits[: int(query_config["top_k"] * 3)], query)
    hits.sort(key=lambda hit: hit.score, reverse=True)
    hits = hits[: int(query_config["top_k"])]
    return RetrievalResult(
        documents=[hit.chunk.text for hit in hits],
        scores=[hit.score for hit in hits],
        source_ids=[hit.chunk.source_id for hit in hits],
        generation=generations,
        hits=hits,
    )
