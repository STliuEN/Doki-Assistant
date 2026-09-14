from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.auth.errors import AuthError
from app.core.failed_response import (
    BusinessException,
    auth_exception_handler,
    business_exception_handler,
    general_exception_handler,
    http_exception_handler,
    integrity_error_handler,
    sqlalchemy_error_handler,
    validation_exception_handler,
)
from app.db.business_authority import BusinessWriteError
from app.jobs.repository import JobBackpressureError
from app.rag.projection.contracts import ProjectionUnavailable
from app.rag.vector_store import (
    CHROMA_PROJECTION_UNAVAILABLE_MESSAGE,
    ChromaProjectionUnavailable,
)
from app.skills.service import SKILL_REGISTRY_STALE_MESSAGE, SkillRegistryStaleError


async def skill_registry_stale_exception_handler(request, exc):
    return await http_exception_handler(
        request,
        HTTPException(status_code=503, detail=SKILL_REGISTRY_STALE_MESSAGE),
    )


async def chroma_projection_unavailable_exception_handler(request, exc):
    return await http_exception_handler(
        request,
        HTTPException(
            status_code=503,
            detail=CHROMA_PROJECTION_UNAVAILABLE_MESSAGE,
        ),
    )


async def business_write_error_handler(request, exc):
    return await http_exception_handler(request, HTTPException(status_code=409, detail=str(exc)))


async def business_backpressure_handler(request, exc):
    return await http_exception_handler(request, HTTPException(status_code=429, detail="Business task queue is full; retry later"))


async def rag_projection_unavailable_handler(request, exc):
    import os
    owner = getattr(request.state, "e3_auth_user_id", None)
    repairable = exc.code.startswith("chroma_") or exc.code in {
        "rag_source_changed", "rag_artifact_stale", "rag_generation_missing", "rag_artifact_missing", "rag_rebuild_in_progress",
        "rag_candidate_invalid", "rag_chunk_count_changed", "rag_embedding_changed", "rag_index_changed",
    }
    if owner and repairable and os.getenv("E5_RAG_ENABLED", "false").lower() in {"true", "1", "yes", "on"}:
        try:
            from app.db.db_config import AsyncSessionLocal
            from app.rag.projection.settings import request_rebuild
            async with AsyncSessionLocal() as db:
                db.info["e4_actor_id"] = owner
                value = await request_rebuild(db, owner, "RAG read detected " + exc.code)
                exc.job_id = value["job_id"]
        except Exception:
            # SQL failure must preserve the original 503; no in-request rebuilding or fallback.
            pass
    return JSONResponse(status_code=503, content={"code": 503, "message": "RAG temporarily unavailable", "data": exc.as_dict()})


def register_exception_handlers(app):
    """Register application exception handlers."""

    app.add_exception_handler(AuthError, auth_exception_handler)
    app.add_exception_handler(BusinessWriteError, business_write_error_handler)
    app.add_exception_handler(JobBackpressureError, business_backpressure_handler)
    app.add_exception_handler(ProjectionUnavailable, rag_projection_unavailable_handler)
    app.add_exception_handler(SkillRegistryStaleError, skill_registry_stale_exception_handler)
    app.add_exception_handler(
        ChromaProjectionUnavailable,
        chroma_projection_unavailable_exception_handler,
    )
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(IntegrityError, integrity_error_handler)
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_error_handler)
    app.add_exception_handler(BusinessException, business_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
