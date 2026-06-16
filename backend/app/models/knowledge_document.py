from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import LONGBLOB
from sqlalchemy.sql import func

from app.models.chat_history import Base


class KnowledgeSourceDocument(Base):
    __tablename__ = "knowledge_source_documents"
    __table_args__ = (
        UniqueConstraint("user_id", "md5", name="uq_knowledge_source_user_md5"),
    )

    id = Column(String(36), primary_key=True)
    user_id = Column(String(64), index=True, nullable=False)
    md5 = Column(String(32), index=True, nullable=False)
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
