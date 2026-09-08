from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.sql import func

from app.models.chat_history import Base
from app.models.foundation_types import DIGEST_PATTERN, DIGEST_TYPE, UUID_PATTERN, UUID_TYPE


class UserModelConfig(Base):
    __tablename__ = "user_model_configs"
    __table_args__ = (
        UniqueConstraint("canonical_id", name="uq_user_model_configs_canonical_id"),
        Index("ix_user_model_configs_canonical_user", "canonical_user_id"),
        CheckConstraint(
            f"canonical_id IS NULL OR canonical_id REGEXP '{UUID_PATTERN}'",
            name="ck_user_model_configs_canonical_id_uuid",
        ),
        CheckConstraint(
            f"canonical_user_id IS NULL OR canonical_user_id REGEXP '{UUID_PATTERN}'",
            name="ck_user_model_configs_canonical_user_uuid",
        ),
        CheckConstraint(
            f"content_digest IS NULL OR content_digest REGEXP '{DIGEST_PATTERN}'",
            name="ck_user_model_configs_content_digest",
        ),
    )

    id = Column(String(36), primary_key=True)
    user_id = Column(String(64), index=True, nullable=False)
    canonical_id = Column(UUID_TYPE, nullable=True, comment="E4 canonical model config UUID")
    canonical_user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    model_type = Column(String(32), nullable=False)
    provider = Column(String(100), default="", nullable=False)
    model_name = Column(String(200), default="", nullable=False)
    base_url = Column(String(500), default="", nullable=False)
    api_key_encrypted = Column(String(2048), nullable=True)
    api_key_key_version = Column(String(64), nullable=True, comment="Required before encrypted key migration")
    content_digest = Column(DIGEST_TYPE, nullable=True, comment="E4 config content SHA-256")
    is_default = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
