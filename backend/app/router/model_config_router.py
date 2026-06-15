from fastapi import Depends, HTTPException, status
from fastapi.routing import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import rate_limit
from app.core.success_response import success_response
from app.db.db_config import get_db
from app.schemas.model_config import ModelConfigCreate, ModelConfigTestRequest, ModelConfigUpdate
from app.services.model_config_service import get_model_config_service
from app.utils.auth_utils import get_current_user_id

model_config_router = APIRouter(prefix="/model-config", tags=["model-config"])


@model_config_router.get("/list")
async def list_model_configs(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    svc = get_model_config_service()
    configs = await svc.list_configs(db, user_id)
    return success_response(data=configs)


@model_config_router.get("/default")
async def get_default_model_config(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    svc = get_model_config_service()
    config = await svc.get_default_config(db, user_id)
    return success_response(data=svc._to_response(config) if config else None)


@model_config_router.post("/create")
async def create_model_config(
    payload: ModelConfigCreate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit(limit=20, window=60)),
):
    svc = get_model_config_service()
    config = await svc.create_config(db, user_id, payload)
    return success_response(message="model config created", data=config)


@model_config_router.put("/{config_id}")
async def update_model_config(
    config_id: str,
    payload: ModelConfigUpdate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit(limit=20, window=60)),
):
    svc = get_model_config_service()
    config = await svc.update_config(db, user_id, config_id, payload)
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="model config not found")
    return success_response(message="model config updated", data=config)


@model_config_router.delete("/{config_id}")
async def delete_model_config(
    config_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit(limit=20, window=60)),
):
    svc = get_model_config_service()
    deleted = await svc.delete_config(db, user_id, config_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="model config not found")
    return success_response(message="model config deleted")


@model_config_router.post("/{config_id}/set-default")
async def set_default_model_config(
    config_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    svc = get_model_config_service()
    config = await svc.set_default(db, user_id, config_id)
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="model config not found")
    return success_response(message="default model config updated", data=config)


@model_config_router.post("/test")
async def test_model_config(
    payload: ModelConfigTestRequest,
    user_id: str = Depends(get_current_user_id),
    _: None = Depends(rate_limit(limit=10, window=60)),
):
    svc = get_model_config_service()
    result = await svc.test_payload(payload)
    return success_response(message="model config test completed", data={**result, "user_id": user_id})


@model_config_router.post("/{config_id}/test")
async def test_saved_model_config(
    config_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit(limit=10, window=60)),
):
    svc = get_model_config_service()
    result = await svc.test_saved(db, user_id, config_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="model config not found")
    return success_response(message="model config test completed", data=result)
