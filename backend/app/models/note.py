from sqlalchemy import JSON, Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.models.chat_history import Base
from app.models.foundation_types import DIGEST_PATTERN, DIGEST_TYPE, UUID_PATTERN, UUID_TYPE


class Note(Base):
    __tablename__ = "notes"
    __table_args__ = (
        UniqueConstraint("canonical_id", name="uq_notes_canonical_id"),
        Index("ix_notes_canonical_user", "canonical_user_id"),
        CheckConstraint(
            f"canonical_id IS NULL OR canonical_id REGEXP '{UUID_PATTERN}'",
            name="ck_notes_canonical_id_uuid",
        ),
        CheckConstraint(
            f"canonical_user_id IS NULL OR canonical_user_id REGEXP '{UUID_PATTERN}'",
            name="ck_notes_canonical_user_uuid",
        ),
        CheckConstraint(
            f"content_digest IS NULL OR content_digest REGEXP '{DIGEST_PATTERN}'",
            name="ck_notes_content_digest",
        ),
    )

    id = Column(String(36), primary_key=True, comment="UUID")
    user_id = Column(String(36), index=True, nullable=False, comment="用户ID")
    canonical_id = Column(UUID_TYPE, nullable=True, comment="E4 canonical note UUID")
    canonical_user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    title = Column(String(200), nullable=False, comment="笔记标题")
    content = Column(Text, nullable=False, comment="Markdown原文")
    content_digest = Column(DIGEST_TYPE, nullable=True, comment="E4 normalized note content SHA-256")
    tags = Column(JSON, comment='标签列表 ["AI", "FastAPI"]')
    category = Column(String(50), comment="分类 work/study/life/project")
    is_pinned = Column(Boolean, default=False, nullable=False, comment="是否置顶")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")
