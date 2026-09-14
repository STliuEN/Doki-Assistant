"""User-owned SQL configuration, rebuild requests and refreshable projection status."""

from uuid import uuid4

from sqlalchemy import select

from app.db.business_authority import BusinessWriteError
from app.db.transaction_context import persist_service_write
from app.jobs.repository import JobRepository
from app.models.embedding_config import UserEmbeddingConfig
from app.models.projection_domain import RagGenerationHead
from app.models.rag_runtime import RagArtifact, RagUserState
from app.rag.projection.contracts import IndexConfig, QueryConfig
from app.rag.projection.query_branches import bind_query_models
from app.rag.projection.service import lock_owner
from app.services.embedding_config_service import get_embedding_config_service


async def locked_state(db, owner):
    await lock_owner(db, owner)
    state = await db.scalar(select(RagUserState).where(RagUserState.user_id == owner).with_for_update().execution_options(populate_existing=True))
    if state is None:
        state = RagUserState(user_id=owner, status="failed", revision=1, query_revision=1,
                             index_config=IndexConfig().model_dump(), query_config=QueryConfig().model_dump(), error_code="rag_not_built")
        db.add(state)
    return state


async def status(db, owner):
    from app.models.job_domain import Job
    state = await db.get(RagUserState, owner, populate_existing=True)
    if state is None:
        return {
            "status": "uninitialized", "revision": 0, "query_revision": 0, "job_id": None, "job_status": None,
            "error_code": "rag_not_built", "index_config": IndexConfig().model_dump(),
            "query_config": QueryConfig().model_dump(), "generations": {},
        }
    job = await db.get(Job, state.job_id, populate_existing=True) if state.job_id else None
    generations = {}
    for head in await db.scalars(select(RagGenerationHead).where(
        RagGenerationHead.owner_scope_type == "user", RagGenerationHead.owner_scope_id == owner,
    )):
        artifact = await db.get(RagArtifact, head.active_generation_id) if head.active_generation_id else None
        generations[head.index_kind] = {"active": head.active_generation_id, "staging": head.staging_generation_id,
                                        "chunks": artifact.chunk_count if artifact else 0}
    return {"status": "queued" if state.status == "building" and job and job.status in {"queued", "retry_wait", "leased"} else state.status,
            "revision": state.revision, "query_revision": state.query_revision, "job_id": state.job_id, "job_status": job.status if job else None,
            "error_code": state.error_code, "index_config": IndexConfig.model_validate(state.index_config).model_dump(),
            "query_config": QueryConfig.model_validate(state.query_config).model_dump(), "generations": generations}


async def queue_locked(db, owner, state, reason):
    if state.job_id:
        from app.models.job_domain import Job
        existing = await db.get(Job, state.job_id)
        if existing and existing.status not in {"succeeded", "cancelled", "dead_letter"}:
            state.status = "building"
            state.error_code = None
            return existing.id
    state.revision += 1
    state.status = "building"
    state.error_code = None
    event_id = str(uuid4())
    # Explicit idempotency within the owner revision; no synchronous parsing or model calls.
    result = await JobRepository(db).enqueue(job_type="e5.rag.rebuild", owner_scope_type="user", owner_scope_id=owner,
        idempotency_key=f"e5:{owner}:{state.revision}", payload={"schema_version": 1, "owner_id": owner, "entity_type": "rag_user_states",
            "entity_id": owner, "event_id": event_id}, payload_schema_version=1, correlation_id=event_id)
    state.job_id = result.job.id
    JobRepository(db).append_audit(action="rag.rebuild_requested", target_type="rag_user_state", target_id=owner,
        job_id=state.job_id, actor_type="user", actor_id=owner, scope_type="user", scope_id=owner,
        correlation_id=event_id, reason=reason, result="queued", after={"revision": state.revision})
    return state.job_id


async def request_rebuild(db, owner, reason="User requested RAG rebuild"):
    state = await locked_state(db, owner)
    await queue_locked(db, owner, state, reason)
    await persist_service_write(db)
    return await status(db, owner)


async def save_index(db, owner, config: IndexConfig, expected_revision: int | None = None):
    state = await locked_state(db, owner)
    if expected_revision is not None and state.revision != expected_revision and not (expected_revision == 0 and state in db.new):
        raise BusinessWriteError("rag_config_revision_conflict")
    if state.index_config != config.model_dump():
        if state.status == "building":
            raise BusinessWriteError("rag_rebuild_in_progress")
        before = dict(state.index_config)
        state.index_config = config.model_dump()
        await queue_locked(db, owner, state, "Index configuration changed")
        JobRepository(db).append_audit(action="rag.index_config_changed", target_type="rag_user_state", target_id=owner,
            actor_type="user", actor_id=owner, scope_type="user", scope_id=owner, correlation_id=str(uuid4()),
            reason="Save declarative index configuration", result="queued", before=before, after=state.index_config)
    await persist_service_write(db)
    return await status(db, owner)


async def save_query(db, owner, config: QueryConfig, expected_revision: int | None = None):
    row = await db.scalar(select(UserEmbeddingConfig).where(UserEmbeddingConfig.canonical_user_id == owner))
    service = get_embedding_config_service()
    embedding = service.get_system_default(owner) if row is None else service._to_data(row)
    pinned = await bind_query_models(config.model_dump(), embedding.base_url, verify=False)
    state = await locked_state(db, owner)
    if expected_revision is not None and state.query_revision != expected_revision and not (expected_revision == 0 and state in db.new):
        raise BusinessWriteError("rag_config_revision_conflict")
    if state.query_config != pinned:
        before = dict(state.query_config)
        state.query_config = pinned
        state.query_revision += 1
        JobRepository(db).append_audit(action="rag.query_config_changed", target_type="rag_user_state", target_id=owner,
            actor_type="user", actor_id=owner, scope_type="user", scope_id=owner, correlation_id=str(uuid4()),
            reason="Save query configuration and model identities without rebuilding", result="saved", before=before, after=pinned)
    await persist_service_write(db)
    return await status(db, owner)
