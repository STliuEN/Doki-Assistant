from typing import Any
from urllib.parse import quote

from fastapi import Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.routing import APIRouter
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import rate_limit
from app.core.success_response import success_response
from app.db.db_config import get_db
from app.rag.vector_store import (
    CHROMA_PROJECTION_UNAVAILABLE_MESSAGE,
    VectorStoreService,
)
from app.router.knowledge_service import KnowledgeService, get_knowledge_service
from app.schemas.api import ApiResponse
from app.schemas.models import (
    DocumentChunksResponse,
    KnowledgeDocumentDetail,
    KnowledgeListResponse,
    MD5ListResponse,
    MD5Record,
)
from app.schemas.sse import SSE_OPENAPI_RESPONSE
from app.services.embedding_config_service import get_embedding_config_service
from app.services.reranker_config_service import get_reranker_config_service
from app.utils.auth_utils import get_current_user_id
from app.utils.knowledge_image_paths import (
    InvalidKnowledgeImagePath,
    get_image_media_type,
    resolve_knowledge_image_path,
)

knowledge_router = APIRouter(prefix="/knowledge", tags=["knowledge"])
CHROMA_PROJECTION_UNAVAILABLE_RESPONSE = {
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": ApiResponse[None],
        "description": CHROMA_PROJECTION_UNAVAILABLE_MESSAGE,
    }
}


def ensure_chroma_projection_available() -> None:
    """Fail before a streaming response or config mutation starts."""
    VectorStoreService()


class EmbeddingSwitchRequest(BaseModel):
    model_name: str
    base_url: str | None = None
    provider: str = "ollama"
    model_type: str = "ollama"


class RerankerSwitchRequest(BaseModel):
    model_name: str
    model_path: str
    provider: str = "local"
    revision: str = "master"
    device: str = "auto"
    max_length: int = 8192
    batch_size: int = 1
    torch_dtype: str = "auto"
    min_weight_mb: int = 50
    trust_remote_code: bool = False


@knowledge_router.post(
    "/add/single",
    response_model=ApiResponse[None],
    responses=CHROMA_PROJECTION_UNAVAILABLE_RESPONSE,
)
async def add_vector_single(
        file: UploadFile = File(...),
        user_id: str = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_db),
        knowledge_service: KnowledgeService = Depends(get_knowledge_service),
        _: None = Depends(rate_limit(limit=5, window=60))
):
    """上传文件，将文件保存到向量数据库，仅支持TXT和PDF"""
    filename = await knowledge_service.handle_add_vector_single(file, user_id, db)
    return success_response(message=f"文件 {filename} 已成功上传并存储到向量数据库")


@knowledge_router.post(
    "/add/multiple",
    response_model=ApiResponse[None],
    responses=CHROMA_PROJECTION_UNAVAILABLE_RESPONSE,
)
async def add_vector_multiple(
        files: list[UploadFile] = File(..., description="要上传的文件列表，仅支持PDF和TXT格式"),
        user_id: str = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_db),
        knowledge_service: KnowledgeService = Depends(get_knowledge_service),
        _: None = Depends(rate_limit(limit=3, window=60))
):
    """上传多个文件，将文件保存到向量数据库，仅支持TXT和PDF"""
    filenames = await knowledge_service.handle_add_vector_multiple(files, user_id, db)
    return success_response(message=f"文件 {filenames} 已成功上传并存储到向量数据库")


@knowledge_router.post(
    "/add/multiple/stream",
    response_class=StreamingResponse,
    responses={**SSE_OPENAPI_RESPONSE, **CHROMA_PROJECTION_UNAVAILABLE_RESPONSE},
)
async def add_vector_multiple_stream(
        files: list[UploadFile] = File(..., description="要上传的文件列表，仅支持PDF、TXT、MD、PPTX、DOCX格式"),
        user_id: str = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_db),
        knowledge_service: KnowledgeService = Depends(get_knowledge_service),
        _: None = Depends(rate_limit(limit=3, window=60)),
        _projection: None = Depends(ensure_chroma_projection_available),
):
    """上传多个文件，流式返回处理进度，仅支持TXT、PDF、MD、PPTX、DOCX"""
    return StreamingResponse(
        knowledge_service.handle_add_vector_multiple_stream(files, user_id, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@knowledge_router.delete(
    "/clean",
    response_model=ApiResponse[None],
    responses=CHROMA_PROJECTION_UNAVAILABLE_RESPONSE,
)
async def clean_user_vectors(
        user_id: str = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_db),
        knowledge_service: KnowledgeService = Depends(get_knowledge_service)
):
    """删除用户上传的所有向量"""
    await knowledge_service.clean_user_upload(user_id, db)
    return success_response(message="已成功删除用户上传的所有向量")


@knowledge_router.delete(
    "/md5/clear",
    response_model=ApiResponse[None],
    responses=CHROMA_PROJECTION_UNAVAILABLE_RESPONSE,
)
async def clear_user_md5(
        delete_documents: bool = True,
        user_id: str = Depends(get_current_user_id),
        knowledge_service: KnowledgeService = Depends(get_knowledge_service)
):
    """
    清空用户的MD5记录
    :param delete_documents: 是否同时删除知识库文档（默认True）
    """
    await knowledge_service.handle_clear_user_md5(user_id, delete_documents)
    if delete_documents:
        return success_response(message="已成功清空用户的MD5记录和知识库文档")
    else:
        return success_response(message="已成功清空用户的MD5记录（保留知识库文档）")


@knowledge_router.delete(
    "/md5/delete/{md5_value}",
    response_model=ApiResponse[None],
    responses=CHROMA_PROJECTION_UNAVAILABLE_RESPONSE,
)
async def delete_single_md5(
        md5_value: str,
        delete_documents: bool = True,
        user_id: str = Depends(get_current_user_id),
        knowledge_service: KnowledgeService = Depends(get_knowledge_service)
):
    """
    删除单个MD5记录及其对应的知识库内容
    :param md5_value: 要删除的MD5值
    :param delete_documents: 是否同时删除知识库文档（默认True）
    """
    success = await knowledge_service.handle_delete_single_md5(user_id, md5_value, delete_documents)
    if success:
        if delete_documents:
            return success_response(message=f"已成功删除MD5记录 {md5_value} 及其对应的知识库文档")
        else:
            return success_response(message=f"已成功删除MD5记录 {md5_value}（保留知识库文档）")
    else:
        raise HTTPException(status_code=404, detail=f"MD5记录 {md5_value} 不存在")


@knowledge_router.delete(
    "/delete/filename",
    response_model=ApiResponse[None],
    responses=CHROMA_PROJECTION_UNAVAILABLE_RESPONSE,
)
async def delete_by_filename(
        filename: str,
        delete_documents: bool = True,
        user_id: str = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_db),
        knowledge_service: KnowledgeService = Depends(get_knowledge_service)
):
    """
    通过文件名删除MD5记录及其对应的知识库文档
    :param filename: 要删除的文件名
    :param delete_documents: 是否同时删除知识库文档（默认True）
    """
    success = await knowledge_service.handle_delete_by_filename(user_id, filename, delete_documents, db)
    if success:
        if delete_documents:
            return success_response(message=f"已成功删除文件 {filename} 的MD5记录及其对应的知识库文档")
        else:
            return success_response(message=f"已成功删除文件 {filename} 的MD5记录（保留知识库文档）")
    else:
        raise HTTPException(status_code=404, detail=f"文件 {filename} 不存在")


@knowledge_router.get(
    "/md5/list",
    response_model=ApiResponse[MD5ListResponse],
    responses=CHROMA_PROJECTION_UNAVAILABLE_RESPONSE,
)
async def get_all_md5_records(
        user_id: str = Depends(get_current_user_id),
        knowledge_service: KnowledgeService = Depends(get_knowledge_service),
        _: None = Depends(rate_limit(limit=10, window=60))
):
    """获取用户的所有MD5记录"""
    records = await knowledge_service.handle_get_all_md5_records(user_id)
    return success_response(data=MD5ListResponse(
        records=records,
        total_count=len(records)
    ))


@knowledge_router.get(
    "/md5/{md5_value}",
    response_model=ApiResponse[MD5Record],
    responses=CHROMA_PROJECTION_UNAVAILABLE_RESPONSE,
)
async def get_md5_info(
        md5_value: str,
        user_id: str = Depends(get_current_user_id),
        knowledge_service: KnowledgeService = Depends(get_knowledge_service),
        _: None = Depends(rate_limit(limit=10, window=60))
):
    """
    获取MD5对应的文档信息
    :param md5_value: MD5值
    """
    md5_info = await knowledge_service.handle_get_md5_info(user_id, md5_value)
    if md5_info:
        return success_response(data=md5_info)
    else:
        raise HTTPException(status_code=404, detail=f"MD5记录 {md5_value} 不存在")


@knowledge_router.get("/list", response_model=ApiResponse[KnowledgeListResponse])
async def get_user_knowledge_list(
        user_id: str = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_db),
        knowledge_service: KnowledgeService = Depends(get_knowledge_service),
        _: None = Depends(rate_limit(limit=10, window=60))
):
    """获取用户的知识库文档列表"""
    documents = await knowledge_service.handle_get_user_knowledge(user_id, db)
    return success_response(data=KnowledgeListResponse(
        documents=documents,
        total_count=len(documents)
    ))


@knowledge_router.get("/embedding/current", response_model=ApiResponse[Any])
async def get_current_embedding_config(
        user_id: str = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_db),
):
    svc = get_embedding_config_service()
    config = await svc.get_user_config(db, user_id)
    return success_response(data=config.to_dict())


@knowledge_router.get("/embedding/ollama/models", response_model=ApiResponse[Any])
async def list_embedding_ollama_models(
        base_url: str = "http://localhost:11434",
        user_id: str = Depends(get_current_user_id),
        _: None = Depends(rate_limit(limit=20, window=60)),
):
    svc = get_embedding_config_service()
    result = await svc.list_ollama_embedding_models(base_url)
    return success_response(message="embedding models fetched", data={**result, "user_id": user_id})


@knowledge_router.post(
    "/embedding/switch",
    response_model=ApiResponse[Any],
    responses=CHROMA_PROJECTION_UNAVAILABLE_RESPONSE,
)
async def switch_embedding_and_rebuild(
        payload: EmbeddingSwitchRequest,
        user_id: str = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_db),
        knowledge_service: KnowledgeService = Depends(get_knowledge_service),
        _: None = Depends(rate_limit(limit=5, window=60)),
        _projection: None = Depends(ensure_chroma_projection_available),
):
    svc = get_embedding_config_service()
    config = await svc.save_user_config(
        db,
        user_id,
        model_name=payload.model_name,
        base_url=payload.base_url,
        provider=payload.provider,
        model_type=payload.model_type,
    )
    result = await knowledge_service.rebuild_all_user_indexes(user_id, db)
    return success_response(message="embedding switched and indexes rebuilt", data={**result, "embedding": config.to_dict()})


@knowledge_router.get("/reranker/current", response_model=ApiResponse[Any])
async def get_current_reranker_config(
        user_id: str = Depends(get_current_user_id),
):
    svc = get_reranker_config_service()
    return success_response(data={**svc.get_config().to_dict(), "user_id": user_id})


@knowledge_router.get("/reranker/local-models", response_model=ApiResponse[Any])
async def list_local_reranker_models(
        user_id: str = Depends(get_current_user_id),
        _: None = Depends(rate_limit(limit=20, window=60)),
):
    svc = get_reranker_config_service()
    return success_response(data={"models": svc.list_local_models(), "user_id": user_id})


@knowledge_router.post("/reranker/switch", response_model=ApiResponse[Any])
async def switch_reranker(
        payload: RerankerSwitchRequest,
        user_id: str = Depends(get_current_user_id),
        _: None = Depends(rate_limit(limit=10, window=60)),
):
    svc = get_reranker_config_service()
    config = svc.save_config(payload.model_dump())
    try:
        from app.core.background_init import init_manager
        if init_manager.reorder_service is not None:
            init_manager.reorder_service.reload_config()
    except Exception:
        pass
    return success_response(message="reranker switched", data={**config.to_dict(), "user_id": user_id})


@knowledge_router.get(
    "/detail",
    response_model=ApiResponse[KnowledgeDocumentDetail],
    responses=CHROMA_PROJECTION_UNAVAILABLE_RESPONSE,
)
async def get_document_detail(
        filename: str,
        user_id: str = Depends(get_current_user_id),
        knowledge_service: KnowledgeService = Depends(get_knowledge_service),
        _: None = Depends(rate_limit(limit=10, window=60))
):
    """获取文档详情内容"""
    document = await knowledge_service.handle_get_document_detail(user_id, filename)
    return success_response(data=document)


@knowledge_router.get(
    "/chunks",
    response_model=ApiResponse[DocumentChunksResponse],
    responses=CHROMA_PROJECTION_UNAVAILABLE_RESPONSE,
)
async def get_document_chunks(
        filename: str,
        user_id: str = Depends(get_current_user_id),
        knowledge_service: KnowledgeService = Depends(get_knowledge_service),
        _: None = Depends(rate_limit(limit=10, window=60))
):
    """获取文档切片信息"""
    chunks = await knowledge_service.handle_get_document_chunks(user_id, filename)
    return success_response(data=chunks)


@knowledge_router.get("/source")
async def download_source_file(
        filename: str,
        user_id: str = Depends(get_current_user_id),
        db: AsyncSession = Depends(get_db),
        knowledge_service: KnowledgeService = Depends(get_knowledge_service),
        _: None = Depends(rate_limit(limit=10, window=60))
):
    source_doc = await knowledge_service.handle_get_source_file(user_id, filename, db)
    safe_filename = source_doc.original_filename.replace('"', '')
    encoded_filename = quote(safe_filename.encode("utf-8"))
    return Response(
        content=source_doc.content_blob,
        media_type=source_doc.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
    )


# 图片服务端点：提供 PDF 中提取的原始图片的访问入口。
# 图片本身存储在服务器文件系统中，不直接对外暴露路径，而是通过此 API 做鉴权后返回。
# 这对安全性很重要——用户必须持有有效 JWT token 才能访问自己的图片。
@knowledge_router.get("/image/{md5}/{filename}")
async def serve_knowledge_image(
        md5: str,
        filename: str,
        user_id: str = Depends(get_current_user_id),
):
    """
    返回PDF中提取的原始图片（需JWT鉴权）
    图片存储在 data/extracted_images/{user_id}/{md5}/{filename}
    """
    try:
        image_path = resolve_knowledge_image_path(user_id, md5, filename, must_exist=True)
        media_type = get_image_media_type(filename)
    except InvalidKnowledgeImagePath as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="图片不存在")

    return FileResponse(image_path, media_type=media_type)


# 批量图片获取接口：一次性拿到某个文档的所有图片，前端缓存后按需展示。
# 使用 base64 编码嵌入 JSON 中，减少前端的 HTTP 请求次数（尤其适合移动端）。
@knowledge_router.get("/images/all/{md5}", response_model=ApiResponse[Any])
async def serve_batch_images(
        md5: str,
        user_id: str = Depends(get_current_user_id),
        knowledge_service: KnowledgeService = Depends(get_knowledge_service),
        _: None = Depends(rate_limit(limit=10, window=60))
):
    """返回指定PDF的所有图片（单次请求，JSON + base64）"""
    result = await knowledge_service.handle_get_batch_images(user_id, md5)
    return success_response(data=result)
