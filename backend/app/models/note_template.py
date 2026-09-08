from sqlalchemy import JSON, Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.models.chat_history import Base
from app.models.foundation_types import DIGEST_PATTERN, DIGEST_TYPE, UUID_PATTERN, UUID_TYPE


class NoteTemplate(Base):
    __tablename__ = "note_templates"
    __table_args__ = (
        UniqueConstraint("canonical_id", name="uq_note_templates_canonical_id"),
        Index("ix_note_templates_canonical_user", "canonical_user_id"),
        CheckConstraint(
            f"canonical_id IS NULL OR canonical_id REGEXP '{UUID_PATTERN}'",
            name="ck_note_templates_canonical_id_uuid",
        ),
        CheckConstraint(
            f"canonical_user_id IS NULL OR canonical_user_id REGEXP '{UUID_PATTERN}'",
            name="ck_note_templates_canonical_user_uuid",
        ),
        CheckConstraint(
            f"content_digest IS NULL OR content_digest REGEXP '{DIGEST_PATTERN}'",
            name="ck_note_templates_content_digest",
        ),
    )

    id = Column(String(36), primary_key=True, comment="UUID")
    user_id = Column(String(36), index=True, nullable=False, comment="用户ID")
    canonical_id = Column(UUID_TYPE, nullable=True, comment="E4 canonical template UUID")
    canonical_user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    name = Column(String(100), nullable=False, comment="模板名称")
    icon = Column(String(50), default="FileText", comment="图标名称")
    category = Column(String(50), default="", comment="默认分类")
    title = Column(String(200), default="", comment="默认标题")
    content = Column(Text, default="", comment="默认内容 Markdown")
    content_digest = Column(DIGEST_TYPE, nullable=True, comment="E4 normalized template content SHA-256")
    tags = Column(JSON, default=[], comment="默认标签")
    is_default = Column(Boolean, default=False, nullable=False, comment="系统内置模板")
    sort_order = Column(Integer, default=0, comment="排序序号")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")
