"""Reproduce a complete owner corpus from canonical SQL bytes and notes."""

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree

from sqlalchemy import select

from app.db.business_owner import business_owner_filter
from app.models.knowledge_document import KnowledgeSourceDocument
from app.models.note import Note
from app.rag.projection.contracts import Chunk, IndexConfig, ProjectionUnavailable


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class Source:
    id: str
    kind: str
    title: str
    content: bytes
    extension: str

    @property
    def content_digest(self):
        return digest({"id": self.id, "kind": self.kind, "title": self.title, "extension": self.extension,
                       "bytes": hashlib.sha256(self.content).hexdigest()})


async def read_sources(session, owner: str) -> list[Source]:
    sources = []
    for row in (await session.scalars(select(KnowledgeSourceDocument).where(business_owner_filter(KnowledgeSourceDocument, owner)))).all():
        if row.status == "excluded":
            continue
        if not row.canonical_id or row.canonical_user_id != owner:
            raise ProjectionUnavailable("source_identity_invalid")
        if row.artifact_digest and hashlib.sha256(row.content_blob).hexdigest() != row.artifact_digest:
            raise ProjectionUnavailable("source_digest_mismatch")
        sources.append(Source(row.canonical_id, "knowledge", row.original_filename, row.content_blob, row.file_ext.lower().lstrip(".")))
    for row in (await session.scalars(select(Note).where(business_owner_filter(Note, owner)))).all():
        if not row.canonical_id or row.canonical_user_id != owner:
            raise ProjectionUnavailable("source_identity_invalid")
        sources.append(Source(row.canonical_id, "notes", row.title or "", (row.content or "").encode(), "txt"))
    return sorted(sources, key=lambda source: (source.kind, source.id))


def source_manifest(sources: list[Source]) -> list[dict]:
    return [{"id": item.id, "kind": item.kind, "digest": item.content_digest} for item in sources]


def parse(source: Source) -> list[tuple[int, str]]:
    try:
        if source.extension in {"txt", "md", "markdown", ""}:
            return [(0, source.content.decode("utf-8-sig"))]
        if source.extension == "pdf":
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(source.content), strict=True)
            if reader.is_encrypted:
                raise ValueError("encrypted PDF")
            return [(index + 1, page.extract_text() or "") for index, page in enumerate(reader.pages)]
        if source.extension in {"docx", "pptx"}:
            with zipfile.ZipFile(io.BytesIO(source.content)) as archive:
                names = ["word/document.xml"] if source.extension == "docx" else sorted(
                    (name for name in archive.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml")),
                    key=lambda name: int(name.rsplit("slide", 1)[1].split(".")[0]),
                )
                if sum(archive.getinfo(name).file_size for name in names) > 64 * 1024 * 1024:
                    raise ValueError("expanded document exceeds limit")
                return [(i + 1, "\n".join(node.text or "" for node in ElementTree.fromstring(archive.read(name)).iter()
                                         if node.tag.endswith("}t"))) for i, name in enumerate(names)]
        raise ValueError("unsupported source type")
    except Exception as error:
        raise ProjectionUnavailable("source_parse_failed") from error


def split_sources(sources: list[Source], config: IndexConfig) -> dict[str, list[Chunk]]:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    splitter = RecursiveCharacterTextSplitter(chunk_size=config.chunk_size, chunk_overlap=config.chunk_overlap)
    chunks = {"knowledge": [], "notes": []}
    for source in sources:
        position = 0
        for page, text in parse(source):
            for fragment in splitter.split_text(text):
                chunk_id = digest({"source": source.id, "digest": source.content_digest, "config": config.model_dump(), "position": position})
                chunks[source.kind].append(Chunk(chunk_id, fragment, source.id, source.content_digest, source.kind, position, source.title, page))
                position += 1
        if position == 0 and source.content.strip():
            raise ProjectionUnavailable("source_has_no_extractable_text")
    return chunks
