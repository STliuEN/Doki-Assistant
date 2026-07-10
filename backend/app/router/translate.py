from fastapi import Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import rate_limit
from app.db.db_config import get_db
from app.schemas.translate import DialogueTranslateRequest
from app.services.model_config_service import get_model_config_service
from app.services.translate_service import stream_dialogue_translation
from app.utils.auth_utils import get_current_user_id

translate_router = APIRouter(prefix="/translate", tags=["translate"])


@translate_router.post("/dialogue/stream")
async def dialogue_translate_stream(
    request: DialogueTranslateRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit(limit=20, window=60)),
):
    language_a = request.language_a.strip()
    language_b = request.language_b.strip()
    text = request.text.strip()

    if not language_a or not language_b:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="language_a and language_b are required")
    if language_a == language_b:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="language_a and language_b must be different")
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="text is required")

    model_config = None
    if request.model_config_id and request.model_config_id != "system-default":
        svc = get_model_config_service()
        model_config = await svc.get_config(db, user_id, request.model_config_id)
        if model_config is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="model config not found")

    return StreamingResponse(
        stream_dialogue_translation(
            language_a,
            language_b,
            text,
            model_config=model_config,
            fast_mode=request.fast_mode,
            custom_instruction=request.custom_instruction,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
