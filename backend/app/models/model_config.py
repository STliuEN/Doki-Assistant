from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy.sql import func

from app.models.chat_history import Base


class UserModelConfig(Base):
    __tablename__ = "user_model_configs"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(64), index=True, nullable=False)
    model_type = Column(String(32), nullable=False)
    provider = Column(String(100), default="", nullable=False)
    model_name = Column(String(200), default="", nullable=False)
    base_url = Column(String(500), default="", nullable=False)
    api_key_encrypted = Column(String(2048), nullable=True)
    is_default = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
