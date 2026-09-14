"""E5 configuration and projection lifecycle bound to the authenticated owner."""

import os
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.success_response import success_response
from app.db.db_config import get_db
from app.rag.projection import settings
from app.rag.projection.contracts import IndexConfig, QueryConfig
from app.schemas.api import ApiResponse
from app.utils.auth_utils import get_current_user_id


def enabled():
    if os.getenv("E5_RAG_ENABLED", "false").lower() not in {"true", "1", "yes", "on"}:
        raise HTTPException(404, "E5 RAG is not enabled")


rag_router = APIRouter(prefix="/knowledge/rag", tags=["knowledge"], dependencies=[Depends(enabled)])


class QueryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    config: QueryConfig
    expected_revision: int | None = Field(default=None, ge=0)


class IndexUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    config: IndexConfig
    expected_revision: int | None = Field(default=None, ge=0)


class GenerationStatus(BaseModel):
    active: str | None
    staging: str | None
    chunks: int


class RagStatus(BaseModel):
    status: Literal["uninitialized", "queued", "building", "ready", "failed"]
    revision: int
    query_revision: int
    job_id: str | None
    job_status: str | None
    error_code: str | None
    index_config: IndexConfig
    query_config: QueryConfig
    generations: dict[str, GenerationStatus]


@rag_router.get("/status", response_model=ApiResponse[RagStatus])
async def rag_status(owner: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    return success_response(data=await settings.status(db, owner))


@rag_router.put("/query-config", response_model=ApiResponse[RagStatus])
async def update_query(payload: QueryUpdate, owner: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db, scope="function")):
    return success_response(data=await settings.save_query(db, owner, payload.config, payload.expected_revision))


@rag_router.put("/index-config", status_code=202, response_model=ApiResponse[RagStatus])
async def update_index(payload: IndexUpdate, owner: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db, scope="function")):
    return success_response(data=await settings.save_index(db, owner, payload.config, payload.expected_revision))


@rag_router.post("/rebuild", status_code=202, response_model=ApiResponse[RagStatus])
async def rebuild(owner: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db, scope="function")):
    return success_response(data=await settings.request_rebuild(db, owner))
