from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.models.chat_history import Base
from app.models.foundation_types import DIGEST_PATTERN, DIGEST_TYPE, UUID_PATTERN, UUID_TYPE


class MemoryItem(Base):
    __tablename__ = "memory_items"
    __table_args__ = (
        UniqueConstraint("canonical_id", name="uq_memory_items_canonical_id"),
        Index("ix_memory_items_canonical_user", "canonical_user_id"),
        CheckConstraint(
            f"canonical_id IS NULL OR canonical_id REGEXP '{UUID_PATTERN}'",
            name="ck_memory_items_canonical_id_uuid",
        ),
        CheckConstraint(
            f"canonical_user_id IS NULL OR canonical_user_id REGEXP '{UUID_PATTERN}'",
            name="ck_memory_items_canonical_user_uuid",
        ),
        CheckConstraint(
            f"content_digest IS NULL OR content_digest REGEXP '{DIGEST_PATTERN}'",
            name="ck_memory_items_content_digest",
        ),
    )

    id = Column(String(36), primary_key=True, comment="UUID")
    user_id = Column(String(36), index=True, nullable=False, comment="用户ID")
    canonical_id = Column(UUID_TYPE, nullable=True, comment="E4 canonical memory UUID")
    canonical_user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    content_digest = Column(DIGEST_TYPE, nullable=True, comment="E4 normalized memory content SHA-256")

    source_type = Column(String(32), default="manual", index=True, comment="manual/chat/note/translate/rag")
    source_id = Column(String(36), nullable=True, index=True, comment="来源对象ID")

    type = Column(String(32), default="memo", index=True, comment="review/todo/reminder/long_term/memo")
    title = Column(String(255), nullable=False, comment="标题")
    content = Column(Text, nullable=True, comment="内容")
    status = Column(String(32), default="active", index=True, comment="active/done/archived")
    priority = Column(String(32), default="medium", index=True, comment="low/medium/high")

    due_at = Column(DateTime(timezone=True), nullable=True, index=True, comment="到期时间")
    remind_at = Column(DateTime(timezone=True), nullable=True, index=True, comment="提醒时间")
    completed_at = Column(DateTime(timezone=True), nullable=True, comment="完成时间")
    archived_at = Column(DateTime(timezone=True), nullable=True, comment="归档时间")

    review_count = Column(Integer, default=0, comment="复习次数，仅 review 类型使用")
    interval_days = Column(Integer, default=1, comment="当前复习间隔，仅 review 类型使用")

    metadata_json = Column(Text, nullable=True, comment="扩展元数据JSON")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")
