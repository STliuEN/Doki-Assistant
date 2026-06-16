import hashlib
import os
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_document import KnowledgeSourceDocument


@dataclass
class KnowledgeFileInput:
    filename: str
    content: bytes
    mime_type: str
    file_index: int


class KnowledgeDocumentService:
    def _file_ext(self, filename: str) -> str:
        return os.path.splitext(filename or "")[1].lower().lstrip(".")

    def _md5(self, content: bytes) -> str:
        return hashlib.md5(content).hexdigest()

    def _to_dict(self, doc: KnowledgeSourceDocument) -> dict:
        return {
            "id": doc.id,
            "user_id": doc.user_id,
            "md5": doc.md5,
            "filename": doc.filename,
            "original_filename": doc.original_filename,
            "file_ext": doc.file_ext,
            "mime_type": doc.mime_type,
            "file_size": doc.file_size,
            "status": doc.status,
            "chunk_count": doc.chunk_count,
            "embedding_type": doc.embedding_type,
            "embedding_provider": doc.embedding_provider,
            "embedding_model": doc.embedding_model,
            "embedding_base_url": doc.embedding_base_url,
            "error_message": doc.error_message,
            "created_at": str(doc.created_at) if doc.created_at else None,
            "updated_at": str(doc.updated_at) if doc.updated_at else None,
            "preview": "",
        }

    async def upsert_source(
        self,
        db: AsyncSession,
        user_id: str,
        file_input: KnowledgeFileInput,
        embedding_config: dict,
    ) -> tuple[KnowledgeSourceDocument, bool]:
        md5_hex = self._md5(file_input.content)
        stmt = select(KnowledgeSourceDocument).where(
            KnowledgeSourceDocument.user_id == user_id,
            KnowledgeSourceDocument.md5 == md5_hex,
        )
        result = await db.execute(stmt)
        doc = result.scalar_one_or_none()
        created = doc is None

        if doc is None:
            doc = KnowledgeSourceDocument(
                id=str(uuid.uuid4()),
                user_id=user_id,
                md5=md5_hex,
                filename=file_input.filename,
                original_filename=file_input.filename,
                file_ext=self._file_ext(file_input.filename),
                mime_type=file_input.mime_type or "",
                file_size=len(file_input.content),
                content_blob=file_input.content,
            )
            db.add(doc)
        else:
            doc.filename = file_input.filename
            doc.original_filename = file_input.filename
            doc.file_ext = self._file_ext(file_input.filename)
            doc.mime_type = file_input.mime_type or ""
            doc.file_size = len(file_input.content)
            doc.content_blob = file_input.content

        doc.status = "queued"
        doc.chunk_count = 0
        doc.embedding_type = embedding_config.get("model_type", "")
        doc.embedding_provider = embedding_config.get("provider", "")
        doc.embedding_model = embedding_config.get("model_name", "")
        doc.embedding_base_url = embedding_config.get("base_url", "")
        doc.error_message = None

        await db.commit()
        await db.refresh(doc)
        return doc, created

    async def mark_indexed(
        self,
        db: AsyncSession,
        document_id: str,
        user_id: str,
        chunk_count: int,
        embedding_config: dict,
    ) -> None:
        doc = await self.get_source(db, user_id, document_id)
        if not doc:
            return
        doc.status = "indexed"
        doc.chunk_count = chunk_count
        doc.embedding_type = embedding_config.get("model_type", "")
        doc.embedding_provider = embedding_config.get("provider", "")
        doc.embedding_model = embedding_config.get("model_name", "")
        doc.embedding_base_url = embedding_config.get("base_url", "")
        doc.error_message = None
        await db.commit()

    async def mark_failed(
        self,
        db: AsyncSession,
        document_id: str,
        user_id: str,
        error_message: str,
    ) -> None:
        doc = await self.get_source(db, user_id, document_id)
        if not doc:
            return
        doc.status = "failed"
        doc.error_message = error_message[:4000]
        await db.commit()

    async def get_source(self, db: AsyncSession, user_id: str, document_id: str) -> KnowledgeSourceDocument | None:
        stmt = select(KnowledgeSourceDocument).where(
            KnowledgeSourceDocument.id == document_id,
            KnowledgeSourceDocument.user_id == user_id,
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_source_by_filename(self, db: AsyncSession, user_id: str, filename: str) -> KnowledgeSourceDocument | None:
        stmt = select(KnowledgeSourceDocument).where(
            KnowledgeSourceDocument.user_id == user_id,
            KnowledgeSourceDocument.original_filename == filename,
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_sources(self, db: AsyncSession, user_id: str) -> list[dict]:
        stmt = (
            select(KnowledgeSourceDocument)
            .where(KnowledgeSourceDocument.user_id == user_id)
            .order_by(KnowledgeSourceDocument.created_at.desc())
        )
        result = await db.execute(stmt)
        return [self._to_dict(doc) for doc in result.scalars().all()]

    async def iter_sources(self, db: AsyncSession, user_id: str) -> list[KnowledgeSourceDocument]:
        stmt = (
            select(KnowledgeSourceDocument)
            .where(KnowledgeSourceDocument.user_id == user_id)
            .order_by(KnowledgeSourceDocument.created_at.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def delete_by_filename(self, db: AsyncSession, user_id: str, filename: str) -> KnowledgeSourceDocument | None:
        doc = await self.get_source_by_filename(db, user_id, filename)
        if not doc:
            return None
        await db.delete(doc)
        await db.commit()
        return doc

    async def delete_all(self, db: AsyncSession, user_id: str) -> int:
        docs = await self.iter_sources(db, user_id)
        count = len(docs)
        for doc in docs:
            await db.delete(doc)
        await db.commit()
        return count


_knowledge_document_service: KnowledgeDocumentService | None = None


def get_knowledge_document_service() -> KnowledgeDocumentService:
    global _knowledge_document_service
    if _knowledge_document_service is None:
        _knowledge_document_service = KnowledgeDocumentService()
    return _knowledge_document_service
