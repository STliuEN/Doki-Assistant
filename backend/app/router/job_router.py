"""Owner-scoped SQL task status, never inferred from Redis or SSE memory."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.success_response import success_response
from app.db.db_config import get_db
from app.models.job_domain import Job
from app.schemas.api import ApiResponse
from app.utils.auth_utils import get_current_user_id

job_router = APIRouter(prefix="/jobs", tags=["jobs"])


@job_router.get("", response_model=ApiResponse[Any])
async def list_jobs(
    correlation_id: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    statement = select(Job).where(Job.owner_scope_type == "user", Job.owner_scope_id == user_id)
    if correlation_id:
        statement = statement.where(Job.correlation_id == correlation_id)
    jobs = list((await db.scalars(statement.order_by(Job.created_at.desc(), Job.id).limit(limit))).all())
    return success_response(
        data={"jobs": [{"id": job.id, "status": job.status, "job_type": job.job_type, "correlation_id": job.correlation_id} for job in jobs]}
    )


@job_router.get("/{job_id}", response_model=ApiResponse[Any])
async def get_job(job_id: str, user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db, scope="function")):
    job = await db.scalar(select(Job).where(Job.id == job_id, Job.owner_scope_type == "user", Job.owner_scope_id == user_id))
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return success_response(
        data={
            "id": job.id,
            "status": job.status,
            "job_type": job.job_type,
            "correlation_id": job.correlation_id,
            "attempt_count": job.attempt_count,
            "error_code": job.error_code,
            "result": job.result_json,
        }
    )
