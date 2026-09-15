import os

from fastapi import HTTPException
from fastapi.routing import APIRouter

from app.core.success_response import success_response
from app.db.db_config import check_mysql_connection
from app.db.redis_config import check_redis_connection
from app.jobs.runner import get_default_runner_status
from app.skills.storage import skill_package_storage

health_router = APIRouter(prefix="/health")


async def sql_skill_storage_ready():
    from sqlalchemy import select

    from app.db.db_config import AsyncSessionLocal
    from app.models.skill_domain import SkillInstallation, SkillVersion
    from app.skills.sql_storage import SqlSkillPackageStorage

    try:
        async with AsyncSessionLocal() as db:
            versions = await db.scalars(select(SkillVersion).join(
                SkillInstallation, SkillInstallation.active_version_id == SkillVersion.id))
            for version in versions:
                await SqlSkillPackageStorage(db).load_archive(version.storage_key, expected_digest=version.package_digest)
        return True
    except Exception:
        return False

@health_router.get("/live", tags=["健康检查"], summary="健康检查")
async def get_health_application_status():
    """健康检查-存活"""
    return success_response(
        message="health application status",
        data={
            "status": "ok"
        }
    )

@health_router.get("/ready", tags=["健康检查"], summary="健康检查")
async def get_health_readiness():
    """健康检查-就绪"""
    # 检查mysql连接
    mysql_status = await check_mysql_connection()
    # 检查redis连接
    redis_status = await check_redis_connection()
    sql_mode = any(os.getenv(name, "false").lower() in {"1", "true", "yes", "on"}
                   for name in ("E6E7_ENABLED", "E8_ENABLED"))
    skill_storage_status = await sql_skill_storage_ready() if sql_mode else skill_package_storage.check_health()
    try:
        if os.getenv("E5_RAG_ENABLED", "false").lower() == "true":
            # E5 has no global projection: authenticated reads validate each
            # owner's SQL generation and Chroma receipt independently.
            chroma_projection = {"status": "owner_scoped", "authority": "sql_generation", "status_endpoint": "/rag/status"}
        else:
            from app.rag.vector_store import VectorStoreService

            chroma_projection = VectorStoreService.projection_health()
    except Exception as exc:
        chroma_projection = {
            "status": "unknown",
            "persist_directory": None,
            "checked_at": None,
            "error_type": type(exc).__name__,
            "error_message": str(exc)[:500],
        }
    # Redis accelerates optional cache/rate limiting. SQL and Skill storage remain the business readiness contract.
    core_ready = mysql_status and skill_storage_status
    if core_ready:
        return success_response(
            message="health readiness status",
            data={
                "status": "ok" if chroma_projection["status"] in {"ready", "owner_scoped"} else "degraded",
                "dependencies": {
                    "mysql": "ready",
                    "redis": "ready" if redis_status else "degraded_optional",
                    "skill_storage": "ready",
                    "chroma_projection": chroma_projection,
                },
            }
        )
    else:
        raise HTTPException(status_code=503, detail="MySQL、Redis 或 Skill Storage 连接失败")



@health_router.get("/runner", tags=["健康检查"], summary="E2 SQL runner status")
async def get_health_runner_status():
    """Expose runner liveness separately from API dependency readiness."""
    return success_response(
        message="E2 SQL runner status",
        data=get_default_runner_status(),
    )
