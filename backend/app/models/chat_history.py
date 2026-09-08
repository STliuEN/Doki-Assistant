from sqlalchemy import JSON, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

from app.models.foundation_types import DIGEST_PATTERN, DIGEST_TYPE, UUID_PATTERN, UUID_TYPE

Base = declarative_base()


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    __table_args__ = (
        UniqueConstraint("canonical_id", name="uq_chat_sessions_canonical_id"),
        Index("ix_chat_sessions_canonical_user", "canonical_user_id"),
        CheckConstraint(
            f"canonical_id IS NULL OR canonical_id REGEXP '{UUID_PATTERN}'",
            name="ck_chat_sessions_canonical_id_uuid",
        ),
        CheckConstraint(
            f"canonical_user_id IS NULL OR canonical_user_id REGEXP '{UUID_PATTERN}'",
            name="ck_chat_sessions_canonical_user_uuid",
        ),
    )

    id = Column(String(64), primary_key=True, index=True)
    # 通过 user_id 关联用户微服务，不做物理外键约束
    user_id = Column(String(64), index=True, nullable=False)
    canonical_id = Column(UUID_TYPE, nullable=True, comment="E4 canonical session UUID")
    canonical_user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)

    title = Column(String(255), default="新的对话")
    metadata_ = Column(JSON, name="metadata")  # metadata 是 SQL 保留字，加下划线
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 关系
    # Keep the legacy ORM write path bound to ``session_id``.  E4's
    # canonical_session_id is a shadow FK used by migration/reconciliation
    # and must not make the existing relationship ambiguous.
    messages = relationship(
        "ChatMessage",
        back_populates="session",
        foreign_keys="ChatMessage.session_id",
        cascade="all, delete-orphan",
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        UniqueConstraint("canonical_id", name="uq_chat_messages_canonical_id"),
        Index("ix_chat_messages_canonical_session", "canonical_session_id"),
        Index("ix_chat_messages_content_digest", "content_digest"),
        CheckConstraint(
            f"canonical_id IS NULL OR canonical_id REGEXP '{UUID_PATTERN}'",
            name="ck_chat_messages_canonical_id_uuid",
        ),
        CheckConstraint(
            f"canonical_session_id IS NULL OR canonical_session_id REGEXP '{UUID_PATTERN}'",
            name="ck_chat_messages_canonical_session_uuid",
        ),
        CheckConstraint(
            f"content_digest IS NULL OR content_digest REGEXP '{DIGEST_PATTERN}'",
            name="ck_chat_messages_content_digest",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), ForeignKey("chat_sessions.id"))
    canonical_session_id = Column(
        UUID_TYPE,
        ForeignKey("chat_sessions.canonical_id", ondelete="RESTRICT"),
        nullable=True,
        index=False,
    )
    canonical_id = Column(UUID_TYPE, nullable=True, comment="E4 canonical message UUID")
    content_digest = Column(DIGEST_TYPE, nullable=True, comment="E4 normalized message content SHA-256")

    # LangChain 标准字段
    role = Column(String(32), nullable=False)
    content = Column(Text, nullable=False)
    metadata_ = Column(JSON, name="metadata")

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关系
    session = relationship(
        "ChatSession",
        back_populates="messages",
        foreign_keys=[session_id],
    )
