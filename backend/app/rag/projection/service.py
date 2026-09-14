"""SQL snapshot -> isolated Chroma generations -> atomic fenced publication."""

import asyncio
from uuid import uuid4

from sqlalchemy import func, or_, select

from app.db.uow import SqlUnitOfWork
from app.e2.rag import SyntheticRagRepository
from app.jobs.repository import JobRepository, payload_digest
from app.models.identity_domain import User
from app.models.job_domain import Job
from app.models.projection_domain import RagGeneration, RagGenerationHead
from app.models.rag_runtime import RagArtifact, RagUserState
from app.rag.projection.chroma_adapter import ChromaProjectionAdapter
from app.rag.projection.contracts import IndexConfig, ProjectionUnavailable, QueryConfig
from app.rag.projection.embedding import embedding_dict, embedding_fingerprint, embedding_model, model_snapshot
from app.rag.projection.sources import digest, read_sources, source_manifest, split_sources
from app.services.embedding_config_service import get_embedding_config_service

INDEX_KINDS = ("knowledge", "notes")


async def lock_owner(db, owner):
    if await db.scalar(select(User.id).where(User.id == owner).with_for_update()) is None:
        raise ProjectionUnavailable("owner_missing")


async def current_job(db, owner, context):
    job = await db.scalar(select(Job).where(Job.id == context.job_id).with_for_update().execution_options(populate_existing=True))
    now = await JobRepository(db)._database_now()
    if (job is None or job.status != "running" or job.lease_owner != context.lease_owner
            or job.fencing_token != context.fencing_token or job.lease_expires_at is None
            or job.lease_expires_at.replace(tzinfo=None) <= now.replace(tzinfo=None)):
        raise ProjectionUnavailable("stale_fencing_token")
    if (job.owner_scope_type != "user" or job.owner_scope_id != owner or job.job_type != context.job_type
            or job.payload_json.get("owner_id") != owner or payload_digest(job.payload_json) != job.payload_digest):
        raise ProjectionUnavailable("job_owner_mismatch")
    return job


class E5ProjectionService:
    def __init__(self, factory, *, adapter=None, snapshot_provider=model_snapshot):
        self.factory = factory
        self.adapter = adapter
        self.snapshot_provider = snapshot_provider

    async def config(self, db, owner):
        return embedding_dict(await get_embedding_config_service().get_user_config(db, owner))

    async def rebuild(self, session, owner, context):
        del session  # Never use the caller's old repeatable-read snapshot.
        rows = []
        revision = None
        try:
            async with SqlUnitOfWork(self.factory) as uow:
                db = uow.require_session()
                await lock_owner(db, owner)
                await current_job(db, owner, context)
                state = await db.get(RagUserState, owner, with_for_update=True)
                if state is None:
                    state = RagUserState(user_id=owner, revision=1, query_revision=1, index_config=IndexConfig().model_dump(),
                                         query_config=QueryConfig().model_dump())
                    db.add(state)
                state.status = "building"
                state.job_id = context.job_id
                state.error_code = None
                state.revision = int(state.revision) + 1
                revision = state.revision
                index_config = IndexConfig.model_validate(state.index_config).model_dump()
                config = await self.config(db, owner)
                await uow.commit()
            # Parse failures occur after the durable gate and enter the failure path.
            async with self.factory() as db:
                sources = await read_sources(db, owner)
            manifest = source_manifest(sources)
            manifest_digest = digest(manifest)
            chunks = await asyncio.to_thread(split_sources, sources, IndexConfig.model_validate(index_config))
            embedding = await self.snapshot_provider(config)
            adapter = self.adapter or ChromaProjectionAdapter(embedding_model)
            async with SqlUnitOfWork(self.factory) as uow:
                db = uow.require_session()
                await lock_owner(db, owner)
                await current_job(db, owner, context)
                state = await db.get(RagUserState, owner, with_for_update=True)
                self._check_state(state, context, revision)
                state.source_digest = manifest_digest
                repo = SyntheticRagRepository(db)
                for kind in INDEX_KINDS:
                    head = await repo.ensure_head(owner_scope_type="user", owner_scope_id=owner, index_kind=kind)
                    maximum = await db.scalar(select(func.max(RagGeneration.generation)).where(
                        RagGeneration.owner_scope_type == "user", RagGeneration.owner_scope_id == owner, RagGeneration.index_kind == kind)) or 0
                    row = await repo.create_generation(owner_scope_type="user", owner_scope_id=owner, index_kind=kind,
                        embedding_fingerprint=embedding_fingerprint(embedding), generation=int(maximum) + 1,
                        config={"schema_version": 1, "index": index_config, "source_digest": manifest_digest}, config_schema_version=1,
                        source_revision=revision, job_id=context.job_id, generation_id=str(uuid4()))
                    collection = ChromaProjectionAdapter.locator(kind, row.id)
                    # Persist the attempt locator before any external write, including abandoned builds.
                    db.add(RagArtifact(generation_id=row.id, collection_name=collection, job_id=context.job_id,
                        fencing_token=context.fencing_token, manifest=manifest, manifest_digest=manifest_digest,
                        embedding_config=embedding, chunk_count=len(chunks[kind]), cleanup_status="building"))
                    rows.append((kind, head.id, row.id, collection))
                await uow.commit()
            receipts = {}
            for kind, _head_id, generation, collection in rows:
                if await context.cancellation_requested():
                    raise ProjectionUnavailable("rebuild_cancelled")
                receipt = await adapter.build(collection=collection, owner=owner, generation=generation, chunks=chunks[kind], embedding=embedding)
                await adapter.validate(collection=collection, owner=owner, generation=generation, chunks=chunks[kind], receipt=receipt)
                receipts[generation] = receipt
            if await self.snapshot_provider(config) != embedding:
                raise ProjectionUnavailable("embedding_revision_changed")
            async with SqlUnitOfWork(self.factory) as uow:
                db = uow.require_session()
                await lock_owner(db, owner)
                job = await current_job(db, owner, context)
                state = await db.get(RagUserState, owner, with_for_update=True)
                self._check_state(state, context, revision)
                if (digest(source_manifest(await read_sources(db, owner))) != manifest_digest
                        or await self.config(db, owner) != config or state.index_config != index_config):
                    raise ProjectionUnavailable("source_revision_changed")
                repo = SyntheticRagRepository(db)
                retired = []
                for _kind, head_id, generation, _collection in rows:
                    head = await db.get(RagGenerationHead, head_id, with_for_update=True)
                    if head.active_generation_id:
                        previous = await db.get(RagArtifact, head.active_generation_id)
                        if previous is not None:
                            previous.cleanup_status = "pending"
                            retired.append(previous.generation_id)
                    await repo.mark_ready(generation_id=generation)
                    await repo.stage_generation(head_id=head_id, generation_id=generation, expected_revision=int(head.revision))
                    await repo.activate_generation(head_id=head_id, generation_id=generation, expected_revision=int(head.revision))
                    artifact = await db.get(RagArtifact, generation)
                    artifact.receipt = receipts[generation]
                    artifact.cleanup_status = "retained"
                state.status = "ready"
                state.job_id = None
                state.error_code = None
                result = {"schema_version": 1, "status": "ready", "owner_id": owner, "source_count": len(sources),
                          "chunk_count": sum(len(value) for value in chunks.values()), "cleanup_requested": retired}
                JobRepository(db).append_audit(action="rag.published", target_type="rag_user_state", target_id=owner,
                    job_id=job.id, correlation_id=job.correlation_id, scope_type="user", scope_id=owner,
                    reason="Complete corpus published under current job lease", result="ready",
                    after={"revision": revision, "generations": [row[2] for row in rows], "source_digest": manifest_digest})
                await db.flush()
                accepted = await JobRepository(db).succeed(job_id=context.job_id, lease_owner=context.lease_owner,
                    fencing_token=context.fencing_token, result_payload=result, result_schema_version=1)
                if not accepted.accepted:
                    raise ProjectionUnavailable("stale_fencing_token")
                await uow.commit()
                context.mark_sql_completed()
        except Exception as error:
            code = error.code if isinstance(error, ProjectionUnavailable) else "projection_build_failed"
            await self._fail(owner, context, revision, rows, code)
            if isinstance(error, ProjectionUnavailable):
                raise
            raise ProjectionUnavailable(code) from error
        # Cleanup cannot change the committed result or turn publication into failure.
        await self.cleanup(owner, adapter)
        return result

    @staticmethod
    def _check_state(state, context, revision):
        if state is None or state.status != "building" or state.job_id != context.job_id or state.revision != revision:
            raise ProjectionUnavailable("stale_scope_revision")

    async def _fail(self, owner, context, revision, rows, code):
        if revision is None:
            return
        async with SqlUnitOfWork(self.factory) as uow:
            db = uow.require_session()
            await lock_owner(db, owner)
            try:
                await current_job(db, owner, context)
            except ProjectionUnavailable:
                return  # A stale attempt cannot fail a newer attempt of the same job.
            state = await db.get(RagUserState, owner, with_for_update=True)
            if state is not None and state.job_id == context.job_id and state.revision == revision:
                state.status = "failed"
                state.error_code = code
            for _kind, _head, generation, _collection in rows:
                row = await db.get(RagGeneration, generation, with_for_update=True)
                if row is not None and row.status == "building":
                    await SyntheticRagRepository(db).mark_failed(generation_id=generation, error_detail=code)
                    artifact = await db.get(RagArtifact, generation)
                    artifact.cleanup_status = "pending"
            await uow.commit()

    async def cleanup(self, owner, adapter=None):
        adapter = adapter or self.adapter or ChromaProjectionAdapter(embedding_model)
        async with self.factory() as db:
            ids = list(await db.scalars(select(RagArtifact.generation_id).join(RagGeneration).where(
                RagGeneration.owner_scope_type == "user", RagGeneration.owner_scope_id == owner,
                RagArtifact.cleanup_status != "retained")))
        for generation in ids:
            try:
                async with SqlUnitOfWork(self.factory) as uow:
                    db = uow.require_session()
                    await lock_owner(db, owner)
                    artifact = await db.get(RagArtifact, generation, with_for_update=True)
                    row = await db.get(RagGeneration, generation, with_for_update=True)
                    used = await db.scalar(select(RagGenerationHead.id).where(or_(
                        RagGenerationHead.active_generation_id == generation, RagGenerationHead.staging_generation_id == generation)))
                    job = await db.get(Job, artifact.job_id)
                    now = await JobRepository(db)._database_now()
                    live = (job.fencing_token == artifact.fencing_token and job.status in {"running", "leased", "cancel_requested"}
                            and job.lease_expires_at and job.lease_expires_at.replace(tzinfo=None) > now.replace(tzinfo=None))
                    if used or live or row.owner_scope_id != owner or row.owner_scope_type != "user":
                        continue
                    if row.status == "building":
                        await SyntheticRagRepository(db).mark_failed(generation_id=generation, error_detail="abandoned_attempt")
                    if row.status not in {"failed", "retired"}:
                        continue
                    await adapter.delete(collection=artifact.collection_name, owner=owner, generation=generation)
                    artifact.cleanup_status = "deleted"
                    await uow.commit()
            except Exception:
                # The durable locator remains eligible for the next reconciliation.
                continue
