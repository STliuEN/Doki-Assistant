from __future__ import annotations

from sqlalchemy import JSON, BigInteger, Column, DateTime, Index, String
from sqlalchemy.sql import func

from app.models.chat_history import Base


class PendingAction(Base):
    """Durable, single use confirmation envelope owned by one user."""

    __tablename__ = "pending_actions"
    __table_args__ = (
        Index("ix_pending_actions_user_expires", "user_id", "expires_at"),
        Index("ix_pending_actions_expires", "expires_at"),
    )

    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), nullable=False, index=True)
    session_id = Column(String(64), nullable=True)
    tool_id = Column(String(255), nullable=False)
    args = Column(JSON, nullable=False)
    source = Column(String(32), nullable=False, default="local", server_default="local")
    provider_id = Column(String(128), nullable=True)
    external_name = Column(String(255), nullable=True)
    run_id = Column(String(64), nullable=False)
    registry_revision = Column(BigInteger, nullable=False)
    tool_digest = Column(String(64), nullable=False)
    provider_config_digest = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
