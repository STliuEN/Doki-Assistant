"""Replay SQL-backed business projections using current authoritative state."""

from __future__ import annotations

import asyncio
import json

from sqlalchemy import select

from app.db.business_authority import BusinessWriteError, canonical_uuid
from app.db.business_owner import business_owner_filter, business_owner_matches
from app.db.uow import SqlUnitOfWork
from app.jobs.repository import JobRepository, payload_digest
from app.jobs.runner import JobHandlerError, JobHandlerRegistry
from app.models.job_domain import Job
from app.models.memory_item import MemoryItem
from app.models.note import Note


def business_handlers(factory, *, projector=None, tagger=None) -> JobHandlerRegistry:
    registry = JobHandlerRegistry()

    async def project(payload, context):
        try:
            owner = canonical_uuid(payload['owner_id'])
            canonical_uuid(payload['event_id'])
            identifier = str(payload['entity_id'])
        except (KeyError, BusinessWriteError) as error:
            raise JobHandlerError('invalid_business_job', 'Invalid business projection payload', permanent=True) from error
        if await context.cancellation_requested():
            raise JobHandlerError('cancel_requested', 'Projection cancelled')
        async with factory() as session:
            if projector is not None:
                await projector(session, context.job_type, payload)
            elif context.job_type == 'e4.note.project':
                from app.services.note_service import NoteService
                service = NoteService()
                note = await session.get(Note, identifier)
                if note is not None and not business_owner_matches(note, owner):
                    raise JobHandlerError('owner_mismatch', 'Projection owner mismatch', permanent=True)
                await service._delete_note_vector(session, owner, identifier)
                if note is not None:
                    await service._add_note_vector(session, owner, identifier, note.title, note.content)
            else:
                raise JobHandlerError('projection_stage_not_enabled', 'Knowledge generation activation requires E5', permanent=True)
        return {'schema_version': 1, 'projected': True}

    async def enrich(payload, context):
        try:
            owner = canonical_uuid(payload["owner_id"])
            canonical_uuid(payload["event_id"])
            identifier = str(payload["entity_id"])
            if payload.get("schema_version") != 1 or payload.get("entity_type") != "notes":
                raise BusinessWriteError("Unsupported business job payload")
        except (KeyError, BusinessWriteError) as error:
            raise JobHandlerError("invalid_business_job", "Invalid enrichment payload", permanent=True) from error
        async with factory() as session:
            note = await session.scalar(select(Note).where(Note.id == identifier, business_owner_filter(Note, owner)))
            if note is None or (not payload.get('force') and (note.tags is not None or note.category is not None)):
                return {'schema_version': 1, 'skipped': True}
            original_content = note.content
            original_tags, original_category = note.tags, note.category
        if tagger is None:
            from langchain_core.messages import HumanMessage

            from app.core.background_init import init_manager
            from app.services.note_service import NoteService
            from app.utils.prompt_loader import load_prompt
            prompt = load_prompt('auto_tag_prompt').replace('{content}', original_content)
            response = await asyncio.wait_for(init_manager.chat_model.ainvoke([HumanMessage(content=prompt)]), timeout=60)
            result = json.loads(NoteService._extract_json(response.content))
        else:
            result = await tagger(original_content)
        if not isinstance(result, dict):
            raise JobHandlerError('invalid_tag_result', 'Invalid note metadata response')
        tags = result.get('tags', [])
        category = result.get('category', 'life')
        if (
            not isinstance(tags, list)
            or not all(isinstance(tag, str) for tag in tags)
            or not isinstance(category, str)
            or len(category) > 50
            or len(tags) > 100
            or any(len(tag) > 100 for tag in tags)
        ):
            raise JobHandlerError('invalid_tag_result', 'Invalid note metadata response')
        async with SqlUnitOfWork(factory) as uow:
            session = uow.require_session()
            job = await session.scalar(select(Job).where(Job.id == context.job_id).with_for_update())
            now = await JobRepository(session)._database_now()
            if (
                job is None
                or job.status != "running"
                or job.lease_owner != context.lease_owner
                or job.fencing_token != context.fencing_token
                or job.lease_expires_at is None
                or job.lease_expires_at.replace(tzinfo=None) <= now.replace(tzinfo=None)
            ):
                raise JobHandlerError('stale_fencing_token', 'Note enrichment lease no longer current')
            if (
                job.owner_scope_type != "user"
                or job.owner_scope_id != owner
                or job.job_type != context.job_type
                or job.payload_digest != payload_digest(payload)
            ):
                raise JobHandlerError('job_payload_mismatch', 'Business job identity mismatch', permanent=True)
            session.info['e4_correlation_id'] = job.correlation_id
            session.info['e4_actor_id'] = owner
            note = await session.scalar(select(Note).where(Note.id == identifier, business_owner_filter(Note, owner)).with_for_update())
            if note is None or note.content != original_content or note.tags != original_tags or note.category != original_category:
                return {'schema_version': 1, 'skipped': True}
            note.tags, note.category = tags, category
            existing = await session.scalar(
                select(MemoryItem.id).where(
                    business_owner_filter(MemoryItem, owner),
                    MemoryItem.source_type == "note",
                    MemoryItem.source_id == identifier,
                    MemoryItem.type == "review",
                )
            )
            if existing is None:
                from app.services.memory_service import memory_service
                await memory_service.create_review_for_note(session, owner, identifier, note.title, (note.content or '')[:200])
            await session.flush()
            accepted = await JobRepository(session).succeed(
                job_id=job.id,
                lease_owner=context.lease_owner,
                fencing_token=context.fencing_token,
                result_payload={"schema_version": 1, "enriched": True},
                result_schema_version=1,
            )
            if not accepted.accepted:
                raise JobHandlerError('stale_fencing_token', 'Note enrichment completion refused')
            await uow.commit()
            context.mark_sql_completed()
        return {'schema_version': 1, 'enriched': True}

    if projector is not None:
        registry.register('e4.note.project', project)
        registry.register('e4.knowledge.project', project)
        registry.register('e4.embedding.rebuild', project)
    registry.register('e4.note.enrich', enrich)
    return registry
