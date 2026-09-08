from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import LONGBLOB
from sqlalchemy.sql import func

from app.models.chat_history import Base
from app.models.foundation_types import DIGEST_PATTERN, DIGEST_TYPE, UUID_PATTERN, UUID_TYPE


class KnowledgeSourceDocument(Base):
    __tablename__ = "knowledge_source_documents"
    __table_args__ = (
        UniqueConstraint("user_id", "md5", name="uq_knowledge_source_user_md5"),
        UniqueConstraint("canonical_id", name="uq_knowledge_source_canonical_id"),
        Index("ix_knowledge_source_canonical_user", "canonical_user_id"),
        CheckConstraint(
            f"canonical_id IS NULL OR canonical_id REGEXP '{UUID_PATTERN}'",
            name="ck_knowledge_source_canonical_id_uuid",
        ),
        CheckConstraint(
            f"canonical_user_id IS NULL OR canonical_user_id REGEXP '{UUID_PATTERN}'",
            name="ck_knowledge_source_canonical_user_uuid",
        ),
        CheckConstraint(
            f"content_digest IS NULL OR content_digest REGEXP '{DIGEST_PATTERN}'",
            name="ck_knowledge_source_content_digest",
        ),
        CheckConstraint(
            f"artifact_digest IS NULL OR artifact_digest REGEXP '{DIGEST_PATTERN}'",
            name="ck_knowledge_source_artifact_digest",
        ),
    )

    id = Column(String(36), primary_key=True)
    user_id = Column(String(64), index=True, nullable=False)
    canonical_id = Column(UUID_TYPE, nullable=True, comment="E4 canonical document UUID")
    canonical_user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    md5 = Column(String(32), index=True, nullable=False)
    content_digest = Column(DIGEST_TYPE, nullable=True, comment="E4 normalized document content SHA-256")
    artifact_digest = Column(DIGEST_TYPE, nullable=True, comment="E4 original artifact SHA-256")
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_ext = Column(String(32), default="", nullable=False)
    mime_type = Column(String(255), default="", nullable=False)
    file_size = Column(Integer, default=0, nullable=False)
    content_blob = Column(LONGBLOB, nullable=False)
    status = Column(String(32), default="queued", nullable=False)
    chunk_count = Column(Integer, default=0, nullable=False)
    embedding_type = Column(String(32), default="", nullable=False)
    embedding_provider = Column(String(100), default="", nullable=False)
    embedding_model = Column(String(200), default="", nullable=False)
    embedding_base_url = Column(String(500), default="", nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
