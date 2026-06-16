import os
import uuid
from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.embedding_config import UserEmbeddingConfig
from app.services.model_config_service import DEFAULT_OLLAMA_BASE_URL, get_model_config_service
from app.utils.model_provider import create_ollama_embedding_model


@dataclass(frozen=True)
class EmbeddingConfigData:
    id: str
    user_id: str
    provider: str
    model_type: str
    model_name: str
    base_url: str
    is_active: bool = True
    created_at: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class EmbeddingConfigService:
    def get_system_default(self, user_id: str = "system") -> EmbeddingConfigData:
        embed_type = os.getenv("EMBED_MODEL_TYPE", "OLLAMA").upper()
        if embed_type == "ALIYUN":
            return EmbeddingConfigData(
                id="system-default",
                user_id=user_id,
                provider="aliyun",
                model_type="aliyun",
                model_name=os.getenv("ALIYUN_EMBED_MODEL_NAME", "qwen3-embedding"),
                base_url="",
            )

        return EmbeddingConfigData(
            id="system-default",
            user_id=user_id,
            provider="ollama",
            model_type="ollama",
            model_name=os.getenv("TEXT_EMBEDDING_MODEL_NAME", "qwen3-embedding:0.6b"),
            base_url=os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL),
        )

    def _to_data(self, config: UserEmbeddingConfig) -> EmbeddingConfigData:
        return EmbeddingConfigData(
            id=config.id,
            user_id=config.user_id,
            provider=config.provider or "ollama",
            model_type=config.model_type or "ollama",
            model_name=config.model_name or "",
            base_url=config.base_url or DEFAULT_OLLAMA_BASE_URL,
            is_active=config.is_active,
            created_at=str(config.created_at) if config.created_at else None,
            updated_at=str(config.updated_at) if config.updated_at else None,
        )

    async def get_user_config(self, db: AsyncSession, user_id: str) -> EmbeddingConfigData:
        stmt = select(UserEmbeddingConfig).where(UserEmbeddingConfig.user_id == user_id)
        result = await db.execute(stmt)
        config = result.scalar_one_or_none()
        if config:
            return self._to_data(config)
        return self.get_system_default(user_id)

    async def save_user_config(
        self,
        db: AsyncSession,
        user_id: str,
        model_name: str,
        base_url: str | None = None,
        provider: str = "ollama",
        model_type: str = "ollama",
    ) -> EmbeddingConfigData:
        model_name = (model_name or "").strip()
        if not model_name:
            raise ValueError("embedding model_name is required")

        provider = provider.strip() or "ollama"
        model_type = model_type.strip() or "ollama"
        normalized_base_url = (base_url or DEFAULT_OLLAMA_BASE_URL).strip().rstrip("/")

        stmt = select(UserEmbeddingConfig).where(UserEmbeddingConfig.user_id == user_id)
        result = await db.execute(stmt)
        config = result.scalar_one_or_none()

        if config is None:
            config = UserEmbeddingConfig(
                id=str(uuid.uuid4()),
                user_id=user_id,
                provider=provider,
                model_type=model_type,
                model_name=model_name,
                base_url=normalized_base_url,
                is_active=True,
            )
            db.add(config)
        else:
            config.provider = provider
            config.model_type = model_type
            config.model_name = model_name
            config.base_url = normalized_base_url
            config.is_active = True

        await db.commit()
        await db.refresh(config)
        return self._to_data(config)

    async def list_ollama_embedding_models(self, base_url: str | None = None) -> dict:
        svc = get_model_config_service()
        result = await svc.list_ollama_models(base_url, purpose="embedding")
        if result["ok"] and not result["models"]:
            all_models = await svc.list_ollama_models(base_url, purpose="all")
            result = {**result, "models": all_models.get("models", [])}
        return result

    def create_embedding_model(self, config: EmbeddingConfigData):
        if config.model_type.upper() == "ALIYUN":
            from app.utils.factory import DashScopeEmbeddingsWrapper

            return DashScopeEmbeddingsWrapper(model_name=config.model_name)

        return create_ollama_embedding_model(
            model_name=config.model_name,
            base_url=config.base_url or DEFAULT_OLLAMA_BASE_URL,
        )


_embedding_config_service: EmbeddingConfigService | None = None


def get_embedding_config_service() -> EmbeddingConfigService:
    global _embedding_config_service
    if _embedding_config_service is None:
        _embedding_config_service = EmbeddingConfigService()
    return _embedding_config_service
