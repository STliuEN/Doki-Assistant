from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.e2.common import ascii_text, canonical_uuid, digest, generated_or_canonical_uuid, required_text
from app.e2.errors import E2PrimitiveConflictError
from app.models.identity_domain import MigrationMap


class SyntheticMigrationMapRepository:
    """Idempotent legacy-to-UUID mapping facts for synthetic E2 fixtures."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def map_source(
        self,
        *,
        migration_batch_id: str,
        source_system: str,
        entity_type: str,
        source_id: str,
        target_uuid: str,
        source_digest: str,
        mapping_id: str | None = None,
    ) -> MigrationMap:
        migration_batch_id = ascii_text(migration_batch_id, "migration_batch_id", 64)
        source_system = ascii_text(source_system, "source_system", 64)
        entity_type = ascii_text(entity_type, "entity_type", 64)
        source_id = required_text(source_id, "source_id", 255)
        target_uuid = canonical_uuid(target_uuid, "target_uuid")
        source_digest = digest(source_digest, "source_digest")
        existing = await self.session.scalar(
            select(MigrationMap).where(
                MigrationMap.source_system == source_system,
                MigrationMap.entity_type == entity_type,
                MigrationMap.source_id == source_id,
            )
        )
        if existing is not None:
            if existing.target_uuid != target_uuid or existing.source_digest != source_digest:
                raise E2PrimitiveConflictError("synthetic source mapping conflicts with an existing digest or target")
            return existing
        mapping = MigrationMap(
            id=generated_or_canonical_uuid(mapping_id, "mapping_id"),
            migration_batch_id=migration_batch_id,
            source_system=source_system,
            entity_type=entity_type,
            source_id=source_id,
            target_uuid=target_uuid,
            source_digest=source_digest,
        )
        self.session.add(mapping)
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except IntegrityError as exc:
            raise E2PrimitiveConflictError("synthetic source mapping uniqueness constraint rejected the insert") from exc
        return mapping
