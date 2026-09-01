"""Standard Skill package lifecycle API."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import Depends, File, Header, HTTPException, UploadFile, status
from fastapi.responses import Response
from fastapi.routing import APIRouter
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.skill_registry import skill_registry
from app.core.success_response import success_response
from app.db.db_config import get_db
from app.schemas.api import ApiResponse
from app.skills.package import SkillPackageError
from app.skills.schema import (
    SkillActivateRequest,
    SkillArchiveRequest,
    SkillCatalogResponse,
    SkillDetailResponse,
    SkillDraftCreate,
    SkillDraftUpdate,
    SkillImportApproveRequest,
    SkillImportResponse,
    SkillPublishRequest,
    SkillRollbackRequest,
    SkillSettingsUpdate,
    SkillVersionsResponse,
)
from app.skills.service import (
    SKILL_REGISTRY_STALE_MESSAGE,
    SkillConflictError,
    SkillNotFoundError,
    SkillRegistryStaleError,
    skill_service,
)
from app.utils.auth_utils import get_current_user_id, is_admin_user, require_skill_admin, security

SKILL_MUTATION_ERROR_RESPONSES = {
    status.HTTP_400_BAD_REQUEST: {
        "model": ApiResponse[None],
        "description": "Skill package or lifecycle request is invalid",
    },
    status.HTTP_404_NOT_FOUND: {
        "model": ApiResponse[None],
        "description": "Skill or version was not found",
    },
    status.HTTP_409_CONFLICT: {
        "model": ApiResponse[None],
        "description": "Idempotency key, digest, or reviewed revision conflict",
    },
}

SKILL_IMPORT_ERROR_RESPONSES = {
    **SKILL_MUTATION_ERROR_RESPONSES,
    status.HTTP_413_CONTENT_TOO_LARGE: {
        "model": ApiResponse[None],
        "description": "Skill ZIP or multipart request exceeds the configured limit",
    },
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {
        "model": ApiResponse[None],
        "description": "Skill import requires application/zip or application/x-zip-compressed",
    },
}

skill_router = APIRouter(
    prefix="/skills",
    tags=["skills"],
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ApiResponse[None],
            "description": SKILL_REGISTRY_STALE_MESSAGE,
        }
    },
)


def _raise_service_error(exc: Exception) -> None:
    if isinstance(exc, SkillNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="skill not found") from exc
    if isinstance(exc, SkillConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if isinstance(exc, SkillPackageError):
        if exc.code == "storage_unavailable":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": exc.code, "message": exc.detail, "path": exc.path},
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "message": exc.detail, "path": exc.path},
        ) from exc
    if isinstance(exc, SkillRegistryStaleError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=SKILL_REGISTRY_STALE_MESSAGE,
        ) from exc
    raise exc


def _validate_tool_ids(tool_ids: list[str]) -> None:
    known = skill_registry.tool_registry.ids()
    invalid = [tool_id for tool_id in dict.fromkeys(tool_ids) if tool_id not in known]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown or unavailable tools: {', '.join(invalid)}",
        )


@skill_router.get("/catalog", response_model=ApiResponse[SkillCatalogResponse])
async def get_skills_catalog(
    user_id: str = Depends(get_current_user_id),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    can_manage = await is_admin_user(user_id, credentials)
    data = await skill_service.catalog(
        db,
        can_manage=can_manage,
        tools=skill_registry.tool_registry.public_catalog(include_private=can_manage),
    )
    return success_response(data=data)


@skill_router.post(
    "/drafts",
    response_model=ApiResponse[SkillDetailResponse],
    status_code=status.HTTP_201_CREATED,
    responses=SKILL_MUTATION_ERROR_RESPONSES,
)
async def create_skill_draft(
    payload: SkillDraftCreate,
    actor_id: str = Depends(require_skill_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        data = await skill_service.create_draft(db, payload, actor_id)
    except (SkillNotFoundError, SkillConflictError, SkillPackageError) as exc:
        _raise_service_error(exc)
    return success_response(message="skill draft created", data=data)


@skill_router.post(
    "/imports",
    response_model=ApiResponse[SkillImportResponse],
    status_code=status.HTTP_202_ACCEPTED,
    responses=SKILL_IMPORT_ERROR_RESPONSES,
)
async def import_skill_package(
    file: UploadFile = File(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=128),
    actor_id: str = Depends(require_skill_admin),
    db: AsyncSession = Depends(get_db),
):
    media_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    if media_type not in {"application/zip", "application/x-zip-compressed"}:
        await file.close()
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Skill imports require an application/zip file",
        )
    limit = skill_service.storage.limits.max_archive_bytes
    archive = await file.read(limit + 1)
    await file.close()
    if len(archive) > limit:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Skill package exceeds upload limit")
    try:
        data = await skill_service.import_archive(
            db,
            archive,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
        )
    except SkillConflictError as exc:
        _raise_service_error(exc)
    return success_response(message="skill package inspected", data=data)


@skill_router.get("/imports/{import_id}", response_model=ApiResponse[SkillImportResponse])
async def get_skill_import(
    import_id: str,
    actor_id: str = Depends(require_skill_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        data = await skill_service.get_import(db, import_id, actor_id)
    except SkillNotFoundError as exc:
        _raise_service_error(exc)
    return success_response(data=data)


@skill_router.post(
    "/imports/{import_id}/approve",
    response_model=ApiResponse[SkillDetailResponse],
    responses=SKILL_MUTATION_ERROR_RESPONSES,
)
async def approve_skill_import(
    import_id: str,
    payload: SkillImportApproveRequest,
    actor_id: str = Depends(require_skill_admin),
    db: AsyncSession = Depends(get_db),
):
    _validate_tool_ids(payload.tools)
    try:
        data = await skill_service.approve_import(
            db,
            import_id,
            actor_id=actor_id,
            **payload.model_dump(),
        )
    except (SkillNotFoundError, SkillConflictError, SkillPackageError) as exc:
        _raise_service_error(exc)
    return success_response(message="skill package installed", data=data)


@skill_router.get("/{skill_id}", response_model=ApiResponse[SkillDetailResponse])
async def get_skill_detail(
    skill_id: str,
    user_id: str = Depends(get_current_user_id),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    can_manage = await is_admin_user(user_id, credentials)
    try:
        data = await skill_service.get_detail(db, skill_id, can_manage=can_manage)
    except SkillNotFoundError as exc:
        _raise_service_error(exc)
    if not can_manage and (not data["enabled"] or data["visibility"] != "public"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="skill not found")
    return success_response(data=data)


@skill_router.put(
    "/{skill_id}/draft",
    response_model=ApiResponse[SkillDetailResponse],
    responses=SKILL_MUTATION_ERROR_RESPONSES,
)
async def save_skill_draft(
    skill_id: str,
    payload: SkillDraftUpdate,
    actor_id: str = Depends(require_skill_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        data = await skill_service.save_draft(db, skill_id, payload, actor_id)
    except (SkillNotFoundError, SkillConflictError, SkillPackageError) as exc:
        _raise_service_error(exc)
    return success_response(message="skill draft saved as a new version", data=data)


@skill_router.post(
    "/{skill_id}/publish",
    response_model=ApiResponse[SkillDetailResponse],
    responses=SKILL_MUTATION_ERROR_RESPONSES,
)
async def publish_skill_draft(
    skill_id: str,
    payload: SkillPublishRequest,
    actor_id: str = Depends(require_skill_admin),
    db: AsyncSession = Depends(get_db),
):
    _validate_tool_ids(payload.tools)
    try:
        data = await skill_service.publish_draft(db, skill_id, actor_id=actor_id, **payload.model_dump())
    except (SkillNotFoundError, SkillConflictError, SkillPackageError) as exc:
        _raise_service_error(exc)
    return success_response(message="skill version published", data=data)


@skill_router.patch(
    "/{skill_id}/settings",
    response_model=ApiResponse[SkillDetailResponse],
    responses=SKILL_MUTATION_ERROR_RESPONSES,
)
async def update_skill_settings(
    skill_id: str,
    payload: SkillSettingsUpdate,
    actor_id: str = Depends(require_skill_admin),
    db: AsyncSession = Depends(get_db),
):
    patch = payload.model_dump(exclude={"expected_revision"}, exclude_unset=True)
    if patch.get("tools") is not None:
        _validate_tool_ids(patch["tools"])
    try:
        data = await skill_service.update_settings(
            db,
            skill_id,
            actor_id=actor_id,
            expected_revision=payload.expected_revision,
            patch=patch,
        )
    except (SkillNotFoundError, SkillConflictError, SkillPackageError) as exc:
        _raise_service_error(exc)
    return success_response(message="skill settings updated", data=data)


@skill_router.get("/{skill_id}/versions", response_model=ApiResponse[SkillVersionsResponse])
async def get_skill_versions(
    skill_id: str,
    _: str = Depends(require_skill_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        data = await skill_service.list_versions(db, skill_id)
    except SkillNotFoundError as exc:
        _raise_service_error(exc)
    return success_response(data=data)


@skill_router.post(
    "/{skill_id}/versions/{version_id}/activate",
    response_model=ApiResponse[SkillDetailResponse],
    responses=SKILL_MUTATION_ERROR_RESPONSES,
)
async def activate_skill_version(
    skill_id: str,
    version_id: str,
    payload: SkillActivateRequest,
    actor_id: str = Depends(require_skill_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        data = await skill_service.activate_version(
            db,
            skill_id,
            version_id,
            actor_id=actor_id,
            expected_revision=payload.expected_revision,
        )
    except (SkillNotFoundError, SkillConflictError, SkillPackageError) as exc:
        _raise_service_error(exc)
    return success_response(message="skill version activated", data=data)


@skill_router.post(
    "/{skill_id}/rollback",
    response_model=ApiResponse[SkillDetailResponse],
    responses=SKILL_MUTATION_ERROR_RESPONSES,
)
async def rollback_skill(
    skill_id: str,
    payload: SkillRollbackRequest,
    actor_id: str = Depends(require_skill_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        data = await skill_service.rollback(
            db,
            skill_id,
            actor_id=actor_id,
            expected_revision=payload.expected_revision,
            version_id=payload.version_id,
        )
    except (SkillNotFoundError, SkillConflictError, SkillPackageError) as exc:
        _raise_service_error(exc)
    return success_response(message="skill rolled back", data=data)


@skill_router.get("/{skill_id}/versions/{version_id}/export")
async def export_skill_version(
    skill_id: str,
    version_id: str,
    _: str = Depends(require_skill_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        archive, filename = await skill_service.export_version(db, skill_id, version_id)
    except SkillNotFoundError as exc:
        _raise_service_error(exc)
    return Response(
        content=archive,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@skill_router.get("/{skill_id}/resources", response_model=ApiResponse[list[dict]])
async def list_skill_resources(
    skill_id: str,
    _: str = Depends(require_skill_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        resources = await skill_service.list_resources(db, skill_id)
    except SkillNotFoundError as exc:
        _raise_service_error(exc)
    return success_response(data=resources)


@skill_router.get("/{skill_id}/resources/{resource_path:path}")
async def read_skill_resource(
    skill_id: str,
    resource_path: str,
    _: str = Depends(require_skill_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        content, media_type = await skill_service.read_resource(db, skill_id, resource_path)
    except (SkillNotFoundError, SkillPackageError) as exc:
        _raise_service_error(exc)
    return Response(content=content, media_type=media_type)


@skill_router.delete(
    "/{skill_id}",
    response_model=ApiResponse[None],
    responses=SKILL_MUTATION_ERROR_RESPONSES,
)
async def archive_skill(
    skill_id: str,
    payload: SkillArchiveRequest,
    actor_id: str = Depends(require_skill_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        await skill_service.archive(
            db,
            skill_id,
            actor_id,
            expected_revision=payload.expected_revision,
        )
    except (SkillNotFoundError, SkillConflictError) as exc:
        _raise_service_error(exc)
    return success_response(message="skill disabled and archived")
