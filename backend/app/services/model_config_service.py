import uuid

import httpx
from fastapi import HTTPException, status
from langchain_core.messages import HumanMessage
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_config import UserModelConfig
from app.schemas.model_config import ModelConfigCreate, ModelConfigResponse, ModelConfigTestRequest, ModelConfigUpdate
from app.utils.crypto_utils import decrypt_text, encrypt_text, mask_secret
from app.utils.model_provider import create_chat_model_from_config


SUPPORTED_MODEL_TYPES = {"default", "ollama", "openai_compatible"}
USER_EDITABLE_MODEL_TYPES = {"ollama", "openai_compatible"}
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"


class ModelConfigService:
    def _validate_model_type(self, model_type: str):
        if model_type not in SUPPORTED_MODEL_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported model_type: {model_type}",
            )

    def _validate_user_editable_model_type(self, model_type: str):
        if model_type not in USER_EDITABLE_MODEL_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"model_type cannot be configured by user: {model_type}",
            )

    def _to_response(self, config: UserModelConfig) -> ModelConfigResponse:
        api_key = decrypt_text(config.api_key_encrypted)
        return ModelConfigResponse(
            id=config.id,
            user_id=config.user_id,
            model_type=config.model_type,
            provider=config.provider or "",
            model_name=config.model_name or "",
            base_url=config.base_url or "",
            api_key_masked=mask_secret(api_key),
            is_default=config.is_default,
            is_active=config.is_active,
            created_at=str(config.created_at) if config.created_at else None,
            updated_at=str(config.updated_at) if config.updated_at else None,
        )

    async def list_configs(self, db: AsyncSession, user_id: str) -> list[ModelConfigResponse]:
        stmt = (
            select(UserModelConfig)
            .where(UserModelConfig.user_id == user_id)
            .order_by(UserModelConfig.created_at.desc())
        )
        result = await db.execute(stmt)
        return [self._to_response(config) for config in result.scalars().all()]

    async def get_config(self, db: AsyncSession, user_id: str, config_id: str) -> UserModelConfig | None:
        stmt = select(UserModelConfig).where(UserModelConfig.id == config_id, UserModelConfig.user_id == user_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_default_config(self, db: AsyncSession, user_id: str) -> UserModelConfig | None:
        stmt = select(UserModelConfig).where(
            UserModelConfig.user_id == user_id,
            UserModelConfig.is_default == True,  # noqa: E712
            UserModelConfig.is_active == True,  # noqa: E712
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    def get_system_default_config(self) -> ModelConfigResponse:
        import os

        llm_type = os.getenv("LLM_TYPE", "ALIYUN").upper()
        if llm_type == "OLLAMA":
            provider = "ollama"
            model_name = os.getenv("OLLAMA_MODEL_NAME", "")
            base_url = os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL)
        else:
            provider = "aliyun"
            model_name = os.getenv("ALIYUN_MODEL_NAME", os.getenv("CHAT_MODEL_NAME", "qwen3-max"))
            base_url = os.getenv("ALIYUN_BASE_URL", "")

        return ModelConfigResponse(
            id="system-default",
            user_id="system",
            model_type="default",
            provider=provider,
            model_name=model_name,
            base_url=base_url,
            api_key_masked="环境变量",
            is_default=True,
            is_active=True,
            created_at=None,
            updated_at=None,
        )

    async def create_config(self, db: AsyncSession, user_id: str, payload: ModelConfigCreate) -> ModelConfigResponse:
        self._validate_user_editable_model_type(payload.model_type)
        config = UserModelConfig(
            id=str(uuid.uuid4()),
            user_id=user_id,
            model_type=payload.model_type,
            provider=payload.provider,
            model_name=payload.model_name,
            base_url=payload.base_url,
            api_key_encrypted=encrypt_text(payload.api_key),
            is_default=payload.is_default,
            is_active=payload.is_active,
        )
        if payload.is_default:
            await self._clear_default(db, user_id)
        db.add(config)
        await db.commit()
        await db.refresh(config)
        return self._to_response(config)

    async def update_config(self, db: AsyncSession, user_id: str, config_id: str, payload: ModelConfigUpdate) -> ModelConfigResponse | None:
        config = await self.get_config(db, user_id, config_id)
        if not config:
            return None

        if payload.model_type is not None:
            self._validate_user_editable_model_type(payload.model_type)
            config.model_type = payload.model_type
        if payload.provider is not None:
            config.provider = payload.provider
        if payload.model_name is not None:
            config.model_name = payload.model_name
        if payload.base_url is not None:
            config.base_url = payload.base_url
        if payload.api_key is not None and payload.api_key != "":
            config.api_key_encrypted = encrypt_text(payload.api_key)
        if payload.is_active is not None:
            config.is_active = payload.is_active
        if payload.is_default is not None:
            config.is_default = payload.is_default
            if payload.is_default:
                await self._clear_default(db, user_id, exclude_id=config.id)

        await db.commit()
        await db.refresh(config)
        return self._to_response(config)

    async def delete_config(self, db: AsyncSession, user_id: str, config_id: str) -> bool:
        config = await self.get_config(db, user_id, config_id)
        if not config:
            return False
        await db.delete(config)
        await db.commit()
        return True

    async def set_default(self, db: AsyncSession, user_id: str, config_id: str) -> ModelConfigResponse | None:
        config = await self.get_config(db, user_id, config_id)
        if not config:
            return None
        await self._clear_default(db, user_id, exclude_id=config.id)
        config.is_default = True
        config.is_active = True
        await db.commit()
        await db.refresh(config)
        return self._to_response(config)

    async def _clear_default(self, db: AsyncSession, user_id: str, exclude_id: str | None = None):
        stmt = update(UserModelConfig).where(UserModelConfig.user_id == user_id)
        if exclude_id:
            stmt = stmt.where(UserModelConfig.id != exclude_id)
        await db.execute(stmt.values(is_default=False))

    async def test_payload(self, payload: ModelConfigTestRequest) -> dict:
        self._validate_user_editable_model_type(payload.model_type)
        config = UserModelConfig(
            id="test",
            user_id="test",
            model_type=payload.model_type,
            provider=payload.provider,
            model_name=payload.model_name,
            base_url=payload.base_url,
            api_key_encrypted=encrypt_text(payload.api_key),
            is_default=False,
            is_active=True,
        )
        return await self._ping_config(config)

    async def test_saved(self, db: AsyncSession, user_id: str, config_id: str) -> dict | None:
        config = await self.get_config(db, user_id, config_id)
        if not config:
            return None
        return await self._ping_config(config)

    async def test_system_default(self) -> dict:
        return await self._ping_config(None)

    async def list_ollama_models(self, base_url: str | None = None) -> dict:
        url = (base_url or DEFAULT_OLLAMA_BASE_URL).strip().rstrip("/")
        if not url:
            url = DEFAULT_OLLAMA_BASE_URL

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{url}/api/tags")
            response.raise_for_status()
            data = response.json()
            models = [
                item.get("name")
                for item in data.get("models", [])
                if isinstance(item, dict) and item.get("name")
            ]
            return {"ok": True, "base_url": url, "models": models, "error": ""}
        except Exception as exc:
            return {"ok": False, "base_url": url, "models": [], "error": str(exc)}

    async def _ping_config(self, config: UserModelConfig | None) -> dict:
        try:
            model = create_chat_model_from_config(config, streaming=False)
            response = await model.ainvoke([HumanMessage(content="Please answer with one word: ok")])
            result = str(getattr(response, "content", response)).strip()
            return {"ok": True, "result": result or "ok", "error": ""}
        except Exception as exc:
            return {"ok": False, "result": "", "error": str(exc)}


_model_config_service: ModelConfigService | None = None


def get_model_config_service() -> ModelConfigService:
    global _model_config_service
    if _model_config_service is None:
        _model_config_service = ModelConfigService()
    return _model_config_service
