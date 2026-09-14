"""No database, model provider or Chroma imports in the RAG port."""

from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProjectionUnavailable(RuntimeError):
    def __init__(self, code: str = "projection_unavailable", *, job_id: str | None = None):
        self.code = code
        self.job_id = job_id
        super().__init__(code)

    def as_dict(self):
        return {"status": "degraded", "degraded_reason": self.code, "job_id": self.job_id}


class IndexConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: int = Field(default=1, ge=1, le=1)
    splitter: str = Field(default="recursive", pattern="^recursive$")
    chunk_size: int = Field(default=1000, ge=128, le=8000)
    chunk_overlap: int = Field(default=150, ge=0, le=2000)
    parser_version: str = Field(default="e5-v1", pattern="^e5-v1$")

    @model_validator(mode="after")
    def overlap_is_smaller(self):
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return self


class QueryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: int = Field(default=1, ge=1, le=1)
    top_k: int = Field(default=10, ge=1, le=50)
    hyde: bool = False
    bm25: bool = True
    notes: bool = True
    rerank: bool = True
    hyde_model: str = Field(default="qwen3:0.6b", min_length=1, max_length=128)
    hyde_model_digest: str | None = Field(default=None, pattern="^[a-f0-9]{64}$")
    reranker_model: str = Field(default="qwen3-reranker-4b", pattern="^(qwen3-reranker-(4b|0\\.6b)|bge-reranker-v2-m3)$")
    reranker_model_digest: str | None = Field(default=None, pattern="^[a-f0-9]{64}$")
    source_ids: list[str] = Field(default_factory=list, max_length=200)


@dataclass(frozen=True)
class Chunk:
    id: str
    text: str
    source_id: str
    source_digest: str
    index_kind: str
    position: int
    title: str = ""
    page: int = 0


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float
    generation: str


@dataclass
class RetrievalResult:
    documents: list[str] = field(default_factory=list)
    scores: list[float] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    generation: dict[str, str] = field(default_factory=dict)
    status: str = "ready"
    degraded_reason: str | None = None
    hits: list[Hit] = field(default_factory=list)

    def as_dict(self):
        return {name: getattr(self, name) for name in (
            "documents", "scores", "source_ids", "generation", "status", "degraded_reason"
        )}


class ProjectionPort(Protocol):
    async def chunks(self, *, collection: str, owner: str, generation: str) -> list[Chunk]: ...
    async def build(self, *, collection: str, owner: str, generation: str, chunks: list[Chunk], embedding: dict) -> dict: ...
    async def validate(self, *, collection: str, owner: str, generation: str, chunks: list[Chunk], receipt: dict) -> None: ...
    async def query(self, *, collection: str, owner: str, generation: str, query: str, embedding: dict, top_k: int) -> list[Hit]: ...
    async def delete(self, *, collection: str, owner: str, generation: str) -> None: ...
