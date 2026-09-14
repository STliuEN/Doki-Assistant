"""Owner-bound SQL source/media links for the E6/E7 joint runtime."""

from sqlalchemy import Column, ForeignKeyConstraint, Integer, String, UniqueConstraint

from app.models.chat_history import Base
from app.models.foundation_types import UUID_TYPE, binary_string


class SourceMedia(Base):
    __tablename__ = "source_media"
    __table_args__ = (
        ForeignKeyConstraint(["source_id", "user_id"],
                             ["knowledge_source_documents.canonical_id", "knowledge_source_documents.canonical_user_id"],
                             ondelete="CASCADE", name="fk_source_media_source_owner"),
        ForeignKeyConstraint(["media_id", "user_id"], ["media_assets.id", "media_assets.canonical_user_id"],
                             ondelete="RESTRICT", name="fk_source_media_asset_owner"),
        UniqueConstraint("source_id", "filename", name="uq_source_media_filename"),
    )
    source_id = Column(UUID_TYPE, primary_key=True)
    media_id = Column(UUID_TYPE, primary_key=True)
    filename = Column(binary_string(255), primary_key=True)
    user_id = Column(UUID_TYPE, nullable=False)
    source_digest = Column(String(64), nullable=False)
    page = Column(Integer, nullable=False, default=0)
