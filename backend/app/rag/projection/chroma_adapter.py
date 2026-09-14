"""Attempt-isolated Chroma writes and strictly non-creating collection reads."""

import asyncio
import math
import os
from pathlib import Path
from uuid import UUID

from app.rag.projection.contracts import Chunk, Hit, ProjectionPort, ProjectionUnavailable
from app.rag.projection.sources import digest
from app.utils.config import chroma_config
from app.utils.path_tool import get_project_root


class ChromaProjectionAdapter(ProjectionPort):
    def __init__(self, embedding_factory, *, persist_directory=None):
        self.embedding_factory = embedding_factory
        configured = persist_directory or os.getenv("E5_CHROMA_PERSIST_DIRECTORY")
        if not configured:
            raise ProjectionUnavailable("e5_chroma_path_required")
        path = Path(configured).resolve()
        backend = Path(get_project_root()).resolve()
        protected = [backend / "data", backend.parent / "data", backend.parent / "project_changes",
                     backend / chroma_config["persist_directory"], Path(chroma_config["persist_directory"]).resolve()]
        for old in protected:
            old = old.resolve()
            if path == old or path.is_relative_to(old) or old.is_relative_to(path):
                raise ProjectionUnavailable("e5_chroma_path_overlaps_protected")
        self.persist_directory = str(path)

    @staticmethod
    def locator(kind, generation):
        if kind not in {"knowledge", "notes"} or str(UUID(generation)) != generation:
            raise ProjectionUnavailable("chroma_locator_invalid")
        return f"e5_{kind}_{UUID(generation).hex}"

    def _client(self):
        import chromadb
        from chromadb.config import Settings
        return chromadb.PersistentClient(path=self.persist_directory, settings=Settings(anonymized_telemetry=False))

    def _collection(self, collection, owner, generation, *, create=False):
        kind = collection.split("_")[1] if collection.startswith("e5_") else ""
        if collection != self.locator(kind, generation):
            raise ProjectionUnavailable("chroma_locator_invalid")
        client = self._client()
        metadata = {"e5_owner": owner, "e5_generation": generation, "e5_kind": kind}
        if create:
            result = client.create_collection(collection, metadata=metadata, embedding_function=None)
        else:
            result = client.get_collection(collection, embedding_function=None)
        if result.metadata != metadata:
            raise ProjectionUnavailable("chroma_scope_mismatch")
        return result

    @staticmethod
    def _metadata(chunk, owner, generation):
        return {"user_id": owner, "generation": generation, "chunk_id": chunk.id, "source_id": chunk.source_id,
                "source_digest": chunk.source_digest, "index_kind": chunk.index_kind, "position": chunk.position,
                "title": chunk.title, "page": chunk.page}

    async def build(self, *, collection, owner, generation, chunks, embedding):
        def run():
            store = self._collection(collection, owner, generation, create=True)
            model = self.embedding_factory(embedding)
            for offset in range(0, len(chunks), 32):
                batch = chunks[offset:offset + 32]
                vectors = model.embed_documents([chunk.text for chunk in batch])
                if len(vectors) != len(batch) or any(
                    len(vector) != embedding["dimension"] or not all(math.isfinite(v) for v in vector)
                    for vector in vectors
                ):
                    raise ProjectionUnavailable("embedding_dimension_mismatch")
                store.add(ids=[chunk.id for chunk in batch], documents=[chunk.text for chunk in batch], embeddings=vectors,
                          metadatas=[self._metadata(chunk, owner, generation) for chunk in batch])
            return {"chunk_count": len(chunks), "ids_digest": digest(sorted(chunk.id for chunk in chunks)),
                    "dimension": embedding["dimension"], "embedding_config": embedding, "owner_id": owner,
                    "generation": generation}
        try:
            return await asyncio.to_thread(run)
        except ProjectionUnavailable:
            raise
        except Exception as error:
            raise ProjectionUnavailable("chroma_build_failed") from error

    async def validate(self, *, collection, owner, generation, chunks, receipt):
        def run():
            store = self._collection(collection, owner, generation)
            values = store.get(include=["documents", "metadatas", "embeddings"])
            actual = {identifier: i for i, identifier in enumerate(values["ids"])}
            if set(actual) != {chunk.id for chunk in chunks} or receipt["ids_digest"] != digest(sorted(actual)):
                raise ProjectionUnavailable("chroma_chunk_set_mismatch")
            for chunk in chunks:
                i = actual[chunk.id]
                vector = values["embeddings"][i]
                if (values["documents"][i] != chunk.text or values["metadatas"][i] != self._metadata(chunk, owner, generation)
                        or len(vector) != receipt["dimension"] or not all(math.isfinite(v) for v in vector)):
                    raise ProjectionUnavailable("chroma_chunk_receipt_mismatch")
        try:
            await asyncio.to_thread(run)
        except ProjectionUnavailable:
            raise
        except Exception as error:
            raise ProjectionUnavailable("chroma_validation_failed") from error

    @staticmethod
    def _chunk(identifier, text, metadata, owner, generation):
        if metadata.get("user_id") != owner or metadata.get("generation") != generation or metadata.get("chunk_id") != identifier:
            raise ProjectionUnavailable("chroma_hit_scope_mismatch")
        return Chunk(identifier, text, metadata["source_id"], metadata["source_digest"], metadata["index_kind"],
                     metadata["position"], metadata["title"], metadata["page"])

    async def chunks(self, *, collection, owner, generation):
        def run():
            values = self._collection(collection, owner, generation).get(include=["documents", "metadatas"])
            return [self._chunk(identifier, values["documents"][i], values["metadatas"][i], owner, generation)
                    for i, identifier in enumerate(values["ids"])]
        try:
            return await asyncio.to_thread(run)
        except ProjectionUnavailable:
            raise
        except Exception as error:
            raise ProjectionUnavailable("chroma_read_failed") from error

    async def query(self, *, collection, owner, generation, query, embedding, top_k):
        def run():
            store = self._collection(collection, owner, generation)
            if store.count() == 0:
                return []
            vector = self.embedding_factory(embedding).embed_query(query)
            if len(vector) != embedding["dimension"] or not all(math.isfinite(v) for v in vector):
                raise ProjectionUnavailable("embedding_dimension_mismatch")
            values = store.query(query_embeddings=[vector], n_results=min(top_k, store.count()),
                                 where={"$and": [{"user_id": owner}, {"generation": generation}]},
                                 include=["documents", "metadatas", "distances"])
            return [Hit(self._chunk(identifier, values["documents"][0][i], values["metadatas"][0][i], owner, generation),
                        1.0 / (1.0 + max(0.0, float(values["distances"][0][i]))), generation)
                    for i, identifier in enumerate(values["ids"][0])]
        try:
            return await asyncio.to_thread(run)
        except ProjectionUnavailable:
            raise
        except Exception as error:
            raise ProjectionUnavailable("chroma_query_failed") from error

    async def delete(self, *, collection, owner, generation):
        def run():
            import chromadb.errors
            try:
                self._collection(collection, owner, generation)
            except chromadb.errors.NotFoundError:
                return
            self._client().delete_collection(collection)
        try:
            await asyncio.to_thread(run)
        except ProjectionUnavailable:
            raise
        except Exception as error:
            raise ProjectionUnavailable("chroma_cleanup_failed") from error
