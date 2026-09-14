"""SQL original detail and verified active chunks for the existing knowledge UI."""

import asyncio

from fastapi import HTTPException

from app.rag.projection.chroma_adapter import ChromaProjectionAdapter
from app.rag.projection.embedding import embedding_model
from app.rag.projection.snapshot import assert_current, read_snapshot, reader_factory
from app.rag.projection.sources import parse, read_sources, split_sources


def find_source(sources, filename):
    values = [source for source in sources if source.kind == "knowledge" and source.title == filename]
    if not values:
        raise HTTPException(404, "Document not found")
    if len(values) != 1:
        raise HTTPException(409, "Ambiguous document filename")
    return values[0]


async def detail(db, owner, filename):
    factory = reader_factory(db)
    async with factory() as reader:
        source = find_source(await read_sources(reader, owner), filename)
        from app.services.sql_media import source_images
        images = await source_images(reader, owner, source_id=source.id)
    pages = await asyncio.to_thread(parse, source)
    # Original reading remains available while the derived index is rebuilding.
    return {"id": source.id, "filename": filename, "user_id": owner, "content": "\n\n".join(text for _, text in pages),
            "chunk_count": 0, "chunks": [], "images": [row["url"] for row in images]}


async def chunks(db, owner, filename):
    factory = reader_factory(db)
    snapshot = await read_snapshot(factory, owner)
    source = find_source(snapshot.sources, filename)
    from app.services.sql_media import source_images
    async with factory() as reader:
        images = await source_images(reader, owner, source_id=source.id)
    expected = await asyncio.to_thread(split_sources, snapshot.sources, snapshot.index)
    adapter = ChromaProjectionAdapter(embedding_model)
    for kind, artifact in snapshot.artifacts.items():
        await adapter.validate(collection=artifact["collection"], owner=owner, generation=artifact["generation"],
                               chunks=expected[kind], receipt=artifact["receipt"])
    result = [{"chunk_id": chunk.id, "index": chunk.position, "content": chunk.text,
               "images": [row["url"] for row in images if row["page"] in (0, chunk.page)],
               "metadata": {"source_id": chunk.source_id, "page": chunk.page, "generation": snapshot.artifacts["knowledge"]["generation"]}}
              for chunk in expected["knowledge"] if chunk.source_id == source.id]
    await assert_current(factory, owner, snapshot)
    return {"filename": filename, "total_chunks": len(result), "chunks": result}
