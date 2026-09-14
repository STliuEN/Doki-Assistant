"""Fresh SQL visibility boundaries for every E5 reader, independent of caller transactions."""

from copy import deepcopy
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.embedding_config import UserEmbeddingConfig
from app.models.projection_domain import RagGeneration, RagGenerationHead
from app.models.rag_runtime import RagArtifact, RagUserState
from app.rag.projection.contracts import IndexConfig, ProjectionUnavailable, QueryConfig
from app.rag.projection.sources import Source, digest, read_sources, source_manifest
from app.services.embedding_config_service import get_embedding_config_service


@dataclass
class QuerySnapshot:
    token: str
    sources: list[Source]
    index: IndexConfig
    query: dict
    embedding: dict
    artifacts: dict[str, dict]
    revision: int
    query_revision: int


def reader_factory(session):
    if session is None or session.bind is None:
        raise ProjectionUnavailable("rag_sql_session_missing")
    # Do not reuse a repeatable-read snapshot or modify/commit the caller's UoW.
    return async_sessionmaker(session.bind, expire_on_commit=False)


async def read_snapshot(factory, owner: str) -> QuerySnapshot:
    async with factory() as db:
        state = await db.get(RagUserState, owner)
        if state is None or state.status != "ready":
            raise ProjectionUnavailable("rag_rebuild_in_progress", job_id=state.job_id if state else None)
        try:
            index = IndexConfig.model_validate(state.index_config)
            query = QueryConfig.model_validate(state.query_config).model_dump()
        except Exception as error:
            raise ProjectionUnavailable("rag_config_invalid") from error
        sources = await read_sources(db, owner)
        manifest = source_manifest(sources)
        if state.source_digest != digest(manifest):
            raise ProjectionUnavailable("rag_source_changed")
        row = await db.scalar(select(UserEmbeddingConfig).where(UserEmbeddingConfig.canonical_user_id == owner))
        service = get_embedding_config_service()
        config = service.get_system_default(owner) if row is None else service._to_data(row)
        embedding = {name: getattr(config, name) for name in ("provider", "model_type", "model_name", "base_url")}
        artifacts = {}
        for kind in ("knowledge", "notes"):
            head = await db.scalar(select(RagGenerationHead).where(
                RagGenerationHead.owner_scope_type == "user", RagGenerationHead.owner_scope_id == owner,
                RagGenerationHead.index_kind == kind))
            if head is None or head.active_generation_id is None or head.staging_generation_id is not None:
                raise ProjectionUnavailable("rag_generation_missing")
            generation = await db.get(RagGeneration, head.active_generation_id)
            artifact = await db.get(RagArtifact, head.active_generation_id)
            if (generation is None or generation.status != "ready" or generation.owner_scope_type != "user"
                    or generation.owner_scope_id != owner or generation.index_kind != kind):
                raise ProjectionUnavailable("rag_generation_scope_mismatch")
            if artifact is None or artifact.cleanup_status != "retained" or not artifact.receipt:
                raise ProjectionUnavailable("rag_artifact_missing")
            if artifact.manifest_digest != state.source_digest or artifact.manifest != manifest:
                raise ProjectionUnavailable("rag_artifact_stale")
            if generation.config_json.get("index") != index.model_dump():
                raise ProjectionUnavailable("rag_index_changed")
            artifacts[kind] = {"generation": str(generation.id), "head_revision": head.revision,
                "collection": artifact.collection_name, "embedding": deepcopy(artifact.embedding_config),
                "receipt": deepcopy(artifact.receipt), "chunk_count": artifact.chunk_count}
        token = digest({"revision": state.revision, "query_revision": state.query_revision, "source": manifest,
                        "index": index.model_dump(), "query": query, "embedding": embedding, "artifacts": artifacts})
        return QuerySnapshot(token, sources, index, query, embedding, artifacts, state.revision, state.query_revision)


async def assert_current(factory, owner: str, snapshot: QuerySnapshot):
    # This final fresh SQL snapshot is the response's visibility boundary.
    if (await read_snapshot(factory, owner)).token != snapshot.token:
        raise ProjectionUnavailable("rag_snapshot_changed")
