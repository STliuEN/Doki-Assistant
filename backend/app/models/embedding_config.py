from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.sql import func

from app.models.chat_history import Base
from app.models.foundation_types import DIGEST_PATTERN, DIGEST_TYPE, UUID_PATTERN, UUID_TYPE


class UserEmbeddingConfig(Base):
    __tablename__ = "user_embedding_configs"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_embedding_config_user_id"),
        UniqueConstraint("canonical_id", name="uq_user_embedding_configs_canonical_id"),
        Index("ix_user_embedding_configs_canonical_user", "canonical_user_id"),
        CheckConstraint(
            f"canonical_id IS NULL OR canonical_id REGEXP '{UUID_PATTERN}'",
            name="ck_user_embedding_configs_canonical_id_uuid",
        ),
        CheckConstraint(
            f"canonical_user_id IS NULL OR canonical_user_id REGEXP '{UUID_PATTERN}'",
            name="ck_user_embedding_configs_canonical_user_uuid",
        ),
        CheckConstraint(
            f"content_digest IS NULL OR content_digest REGEXP '{DIGEST_PATTERN}'",
            name="ck_user_embedding_configs_content_digest",
        ),
    )

    id = Column(String(36), primary_key=True)
    user_id = Column(String(64), index=True, nullable=False)
    canonical_id = Column(UUID_TYPE, nullable=True, comment="E4 canonical embedding config UUID")
    canonical_user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    provider = Column(String(100), default="ollama", nullable=False)
    model_type = Column(String(32), default="ollama", nullable=False)
    model_name = Column(String(200), nullable=False)
    base_url = Column(String(500), default="", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    content_digest = Column(DIGEST_TYPE, nullable=True, comment="E4 config content SHA-256")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
