"""E5 companion tables; existing generation heads remain the active pointers."""

from sqlalchemy import JSON, BigInteger, CheckConstraint, Column, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from app.models.chat_history import Base
from app.models.foundation_types import DIGEST_TYPE, UTC_DATETIME, UUID_TYPE


class RagUserState(Base):
    __tablename__ = "rag_user_states"
    __table_args__ = (
        CheckConstraint("status IN ('building','ready','failed')", name="ck_rag_user_states_status"),
        CheckConstraint("revision > 0 AND query_revision > 0", name="ck_rag_user_states_revisions"),
    )
    user_id = Column(UUID_TYPE, ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True)
    status = Column(String(16), nullable=False, default="building")
    revision = Column(BigInteger, nullable=False, default=1)
    query_revision = Column(BigInteger, nullable=False, default=1)
    index_config = Column(JSON, nullable=False)
    query_config = Column(JSON, nullable=False)
    job_id = Column(UUID_TYPE, ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=True)
    source_digest = Column(DIGEST_TYPE, nullable=True)
    error_code = Column(String(64), nullable=True)
    updated_at = Column(UTC_DATETIME, nullable=False, server_default=func.now(), onupdate=func.now())


class RagArtifact(Base):
    __tablename__ = "rag_artifacts"
    __table_args__ = (UniqueConstraint("collection_name", name="uq_rag_artifact_collection"),)
    generation_id = Column(UUID_TYPE, ForeignKey("rag_generations.id", ondelete="RESTRICT"), primary_key=True)
    collection_name = Column(String(128), nullable=False)
    job_id = Column(UUID_TYPE, ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False)
    fencing_token = Column(BigInteger, nullable=False)
    manifest = Column(JSON, nullable=False)
    manifest_digest = Column(DIGEST_TYPE, nullable=False)
    embedding_config = Column(JSON, nullable=False)
    receipt = Column(JSON, nullable=True)
    chunk_count = Column(Integer, nullable=False)
    cleanup_status = Column(String(16), nullable=False, default="retained")
