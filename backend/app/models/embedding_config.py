from sqlalchemy import Boolean, Column, DateTime, String, UniqueConstraint
from sqlalchemy.sql import func

from app.models.chat_history import Base


class UserEmbeddingConfig(Base):
    __tablename__ = "user_embedding_configs"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_embedding_config_user_id"),
    )

    id = Column(String(36), primary_key=True)
    user_id = Column(String(64), index=True, nullable=False)
    provider = Column(String(100), default="ollama", nullable=False)
    model_type = Column(String(32), default="ollama", nullable=False)
    model_name = Column(String(200), nullable=False)
    base_url = Column(String(500), default="", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
