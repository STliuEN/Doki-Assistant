from fastapi import Depends, Query
from fastapi.routing import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.success_response import success_response
from app.db.db_config import get_db
from app.schemas.memory import MemoryCreate, MemoryPostpone, MemoryUpdate
from app.services.memory_service import memory_service
from app.utils.auth_utils import get_current_user_id

memory_router = APIRouter(prefix="/memory", tags=["memory"])


@memory_router.get("/today")
async def get_today_memories(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    memories = await memory_service.get_today_memories(db, user_id)
    return success_response(data={"memories": memories, "total_count": len(memories)})


@memory_router.get("/list")
async def list_memories(
    type: str | None = Query(None),
    status: str | None = Query(None),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    memories = await memory_service.list_memories(db, user_id, type=type, status=status)
    return success_response(data={"memories": memories, "total_count": len(memories)})


@memory_router.post("/create")
async def create_memory(
    payload: MemoryCreate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    memory = await memory_service.create_memory(db, user_id, payload)
    return success_response(message="记忆事项创建成功", data=memory)


@memory_router.get("/{memory_id}")
async def get_memory(
    memory_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    memory = await memory_service.get_memory_dict(db, user_id, memory_id)
    if not memory:
        return success_response(message="记忆事项不存在")
    return success_response(data=memory)


@memory_router.put("/{memory_id}")
async def update_memory(
    memory_id: str,
    payload: MemoryUpdate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    memory = await memory_service.update_memory(db, user_id, memory_id, payload)
    if not memory:
        return success_response(message="记忆事项不存在")
    return success_response(message="记忆事项已更新", data=memory)


@memory_router.post("/{memory_id}/complete")
async def complete_memory(
    memory_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await memory_service.complete_memory(db, user_id, memory_id)
    return success_response(message=result["message"], data=result)


@memory_router.post("/{memory_id}/reviewed")
async def mark_memory_reviewed(
    memory_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await memory_service.mark_reviewed(db, user_id, memory_id)
    return success_response(message=result["message"], data=result)


@memory_router.post("/{memory_id}/postpone")
async def postpone_memory(
    memory_id: str,
    payload: MemoryPostpone,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await memory_service.postpone_memory(db, user_id, memory_id, payload.days)
    return success_response(message=result["message"], data=result)


@memory_router.post("/{memory_id}/archive")
async def archive_memory(
    memory_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await memory_service.archive_memory(db, user_id, memory_id)
    return success_response(message=result["message"], data=result)


@memory_router.delete("/{memory_id}")
async def delete_memory(
    memory_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    deleted = await memory_service.delete_memory(db, user_id, memory_id)
    if not deleted:
        return success_response(message="记忆事项不存在")
    return success_response(message="记忆事项已删除")


@memory_router.get("/{memory_id}/review-question")
async def get_memory_review_question(
    memory_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    question = await memory_service.generate_review_question(db, user_id, memory_id)
    return success_response(data=question)
