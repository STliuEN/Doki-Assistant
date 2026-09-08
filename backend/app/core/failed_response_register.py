from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
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


def register_exception_handlers(app):
    """Register application exception handlers."""

    app.add_exception_handler(AuthError, auth_exception_handler)
    app.add_exception_handler(BusinessWriteError, business_write_error_handler)
    app.add_exception_handler(JobBackpressureError, business_backpressure_handler)
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
