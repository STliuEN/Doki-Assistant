from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.e2.common import (
    ascii_text,
    canonical_uuid,
    database_now,
    digest,
    generated_or_canonical_uuid,
    utc_datetime,
    versioned_json,
)
from app.e2.errors import E2PrimitiveConflictError, E2PrimitiveValidationError
from app.models.projection_domain import RagGeneration, RagGenerationHead


class SyntheticRagRepository:
    """SQL-only RAG generation/head state; no vector store is opened."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _scope(owner_scope_type: str, owner_scope_id: str, index_kind: str) -> tuple[str, str, str]:
        return (
            ascii_text(owner_scope_type, "owner_scope_type", 32),
            ascii_text(owner_scope_id, "owner_scope_id", 64),
            ascii_text(index_kind, "index_kind", 64),
        )

    async def ensure_head(
        self,
        *,
        owner_scope_type: str,
        owner_scope_id: str,
        index_kind: str,
        head_id: str | None = None,
    ) -> RagGenerationHead:
        owner_scope_type, owner_scope_id, index_kind = self._scope(owner_scope_type, owner_scope_id, index_kind)
        existing = await self.session.scalar(
            select(RagGenerationHead).where(
                RagGenerationHead.owner_scope_type == owner_scope_type,
                RagGenerationHead.owner_scope_id == owner_scope_id,
                RagGenerationHead.index_kind == index_kind,
            )
        )
        if existing is not None:
            return existing
        head = RagGenerationHead(
            id=generated_or_canonical_uuid(head_id, "head_id"),
            owner_scope_type=owner_scope_type,
            owner_scope_id=owner_scope_id,
            index_kind=index_kind,
            revision=1,
        )
        self.session.add(head)
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except IntegrityError:
            existing = await self.session.scalar(
                select(RagGenerationHead).where(
                    RagGenerationHead.owner_scope_type == owner_scope_type,
                    RagGenerationHead.owner_scope_id == owner_scope_id,
                    RagGenerationHead.index_kind == index_kind,
                )
            )
            if existing is None:
                raise
            return existing
        return head

    async def create_generation(
        self,
        *,
        owner_scope_type: str,
        owner_scope_id: str,
        index_kind: str,
        embedding_fingerprint: str,
        generation: int,
        config: dict[str, object],
        config_schema_version: int,
        source_revision: int,
        job_id: str | None = None,
        generation_id: str | None = None,
    ) -> RagGeneration:
        owner_scope_type, owner_scope_id, index_kind = self._scope(owner_scope_type, owner_scope_id, index_kind)
        embedding_fingerprint = digest(embedding_fingerprint, "embedding_fingerprint")
        if not isinstance(generation, int) or generation <= 0:
            raise E2PrimitiveValidationError("generation must be positive")
        if not isinstance(source_revision, int) or source_revision <= 0:
            raise E2PrimitiveValidationError("source_revision must be positive")
        normalized_config = versioned_json(config, config_schema_version, "config_json", 256 * 1024)
        job_id = canonical_uuid(job_id, "job_id", required=False)
        existing = await self.session.scalar(
            select(RagGeneration).where(
                RagGeneration.owner_scope_type == owner_scope_type,
                RagGeneration.owner_scope_id == owner_scope_id,
                RagGeneration.index_kind == index_kind,
                RagGeneration.embedding_fingerprint == embedding_fingerprint,
                RagGeneration.generation == generation,
            )
        )
        if existing is not None:
            if existing.config_json != normalized_config or existing.source_revision != source_revision:
                raise E2PrimitiveConflictError("synthetic RAG generation conflicts with an existing generation")
            return existing
        generation_row = RagGeneration(
            id=generated_or_canonical_uuid(generation_id, "generation_id"),
            owner_scope_type=owner_scope_type,
            owner_scope_id=owner_scope_id,
            index_kind=index_kind,
            embedding_fingerprint=embedding_fingerprint,
            generation=generation,
            config_json=normalized_config,
            config_schema_version=config_schema_version,
            source_revision=source_revision,
            job_id=job_id,
        )
        self.session.add(generation_row)
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except IntegrityError as exc:
            raise E2PrimitiveConflictError("synthetic RAG generation uniqueness constraint rejected the insert") from exc
        return generation_row

    async def mark_ready(self, *, generation_id: str, now: datetime | None = None) -> RagGeneration:
        generation_id = canonical_uuid(generation_id, "generation_id")
        generation = await self.session.get(RagGeneration, generation_id, with_for_update=True)
        if generation is None:
            raise E2PrimitiveValidationError("RAG generation does not exist")
        if generation.status == "ready":
            return generation
        if generation.status != "building":
            raise E2PrimitiveConflictError(f"RAG generation cannot become ready from {generation.status}")
        checked_at = utc_datetime(now, "now") if now else None
        if checked_at is None:
            checked_at = await database_now(self.session)
        generation.status = "ready"
        generation.ready_at = checked_at
        await self.session.flush()
        return generation

    async def mark_failed(self, *, generation_id: str, error_detail: str, now: datetime | None = None) -> RagGeneration:
        generation_id = canonical_uuid(generation_id, "generation_id")
        if not isinstance(error_detail, str) or not error_detail or len(error_detail.encode("utf-8")) > 16 * 1024:
            raise E2PrimitiveValidationError("error_detail is empty or exceeds its UTF-8 limit")
        generation = await self.session.get(RagGeneration, generation_id, with_for_update=True)
        if generation is None:
            raise E2PrimitiveValidationError("RAG generation does not exist")
        if generation.status in {"failed", "retired"}:
            return generation
        if generation.status != "building":
            raise E2PrimitiveConflictError(f"RAG generation cannot fail from {generation.status}")
        checked_at = utc_datetime(now, "now") if now else None
        if checked_at is None:
            checked_at = await database_now(self.session)
        generation.status = "failed"
        generation.error_detail = error_detail
        generation.retired_at = checked_at
        await self.session.flush()
        return generation

    async def stage_generation(self, *, head_id: str, generation_id: str, expected_revision: int) -> RagGenerationHead:
        head_id = canonical_uuid(head_id, "head_id")
        generation_id = canonical_uuid(generation_id, "generation_id")
        if not isinstance(expected_revision, int) or expected_revision <= 0:
            raise E2PrimitiveValidationError("expected_revision must be positive")
        head = await self.session.get(RagGenerationHead, head_id, with_for_update=True)
        generation = await self.session.get(RagGeneration, generation_id)
        if head is None or generation is None:
            raise E2PrimitiveValidationError("RAG head or generation does not exist")
        if head.revision != expected_revision:
            raise E2PrimitiveConflictError("RAG head revision changed before staging")
        if (
            generation.owner_scope_type != head.owner_scope_type
            or generation.owner_scope_id != head.owner_scope_id
            or generation.index_kind != head.index_kind
        ):
            raise E2PrimitiveValidationError("RAG generation does not belong to the requested head")
        if generation.status != "ready":
            raise E2PrimitiveConflictError("only a ready RAG generation can be staged")
        head.staging_generation_id = generation.id
        head.revision = int(head.revision) + 1
        await self.session.flush()
        return head

    async def activate_generation(self, *, head_id: str, generation_id: str, expected_revision: int) -> RagGenerationHead:
        head_id = canonical_uuid(head_id, "head_id")
        generation_id = canonical_uuid(generation_id, "generation_id")
        if not isinstance(expected_revision, int) or expected_revision <= 0:
            raise E2PrimitiveValidationError("expected_revision must be positive")
        head = await self.session.get(RagGenerationHead, head_id, with_for_update=True)
        generation = await self.session.get(RagGeneration, generation_id, with_for_update=True)
        if head is None or generation is None:
            raise E2PrimitiveValidationError("RAG head or generation does not exist")
        if head.revision != expected_revision:
            raise E2PrimitiveConflictError("RAG head revision changed before activation")
        if generation.status != "ready":
            raise E2PrimitiveConflictError("only a ready RAG generation can be activated")
        if (
            generation.owner_scope_type != head.owner_scope_type
            or generation.owner_scope_id != head.owner_scope_id
            or generation.index_kind != head.index_kind
        ):
            raise E2PrimitiveValidationError("RAG generation does not belong to the requested head")
        old_generation = None
        if head.active_generation_id and head.active_generation_id != generation.id:
            old_generation = await self.session.get(RagGeneration, head.active_generation_id, with_for_update=True)
        now = await database_now(self.session)
        head.active_generation_id = generation.id
        if head.staging_generation_id == generation.id:
            head.staging_generation_id = None
        head.revision = int(head.revision) + 1
        if old_generation is not None and old_generation.status == "ready":
            old_generation.status = "retired"
            old_generation.retired_at = now
        await self.session.flush()
        return head
