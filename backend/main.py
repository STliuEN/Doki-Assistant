import asyncio
import os
import time
from contextlib import asynccontextmanager
from typing import Any

# The deliberate import ordering below captures E2 variables before legacy
# modules that call ``load_dotenv`` at import time.  Ruff's normal E402 rule
# does not understand this security boundary.
# ruff: noqa: E402, I001

from dotenv import load_dotenv


def _capture_e2_process_environment() -> dict[str, str]:
    """Capture E2 variables before importing modules that load dotenv."""

    names = {
        "E2_RUNNER_ENABLED",
        "E2_MIGRATION_ENABLED",
        "E2_DATABASE_URL",
        "E2_APPROVAL_TOKEN",
        "E2_PREFLIGHT_FILE",
        "JOB_LEASE_SECONDS",
        "JOB_HEARTBEAT_SECONDS",
        "JOB_POLL_SECONDS",
        "JOB_SHUTDOWN_DRAIN_SECONDS",
        "JOB_MAX_ATTEMPTS",
        "JOB_GLOBAL_BACKPRESSURE",
        "JOB_OWNER_TYPE_BACKPRESSURE",
    }
    return {name: os.environ[name] for name in names if name in os.environ}


# A number of existing modules call ``load_dotenv`` at import time.  Keeping
# this snapshot stdlib-only makes it impossible for those values to enable or
# retune E2 later in startup.
E2_PROCESS_ENVIRONMENT = _capture_e2_process_environment()

from fastapi import FastAPI, Request
from starlette.middleware.cors import CORSMiddleware

from app.core.background_init import init_manager
from app.core.environment import is_production_environment, normalize_environment
from app.core.failed_response_register import register_exception_handlers
from app.core.logger_handler import logger
from app.core.rate_limit import RateLimitMiddleware
from app.core.skill_body_limit import SkillDraftBodyLimitMiddleware
from app.core.success_response import success_response
from app.db.db_config import AsyncSessionLocal, verify_database_schema
from app.db.redis_config import close_redis, connect_redis
from app.jobs.e2_runtime import build_e2_runner
from app.jobs.runner import configure_default_runner
from app.router.chat import chat_router
from app.router.health import health_router
from app.router.knowledge_router import knowledge_router
from app.router.mcp_router import mcp_router
from app.router.memory_router import memory_router
from app.router.model_config_router import model_config_router
from app.router.note_router import note_router
from app.router.note_template_router import note_template_router
from app.router.skill_router import skill_router
from app.router.tool_router import tool_router
from app.router.translate import translate_router
from app.router.user import user_router
from app.schemas.api import ApiResponse
from app.services.database_session_manager import init_database_session_manager
from app.skills.storage import validate_skill_storage_configuration
from app.utils.auth_utils import validate_security_configuration

# Load application environment variables after the E2 process snapshot.
load_dotenv()

def _env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


def _validate_cors_origins(environment: str, origins: list[str]) -> None:
    if is_production_environment(normalize_environment(environment)) and (not origins or "*" in origins):
        raise RuntimeError("Production requires an explicit CORS_ALLOWED_ORIGINS allowlist")


async def _reconcile_skill_registry(stop_event: asyncio.Event) -> None:
    """Poll the durable revision/outbox so every API process converges."""

    from app.skills.service import skill_service

    interval = max(0.5, float(os.getenv("SKILL_REGISTRY_POLL_SECONDS", "2")))
    while not stop_event.is_set():
        try:
            async with AsyncSessionLocal() as db:
                await skill_service.consume_registry_events(db)
        except Exception as exc:
            logger.error("Standard Skill registry reconciliation failed: %s", exc, exc_info=True)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            pass


ENVIRONMENT = normalize_environment()
IS_PRODUCTION = is_production_environment(ENVIRONMENT)
DEFAULT_BROWSER_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
CORS_ALLOWED_ORIGINS = _env_list(
    "CORS_ALLOWED_ORIGINS",
    "" if IS_PRODUCTION else DEFAULT_BROWSER_ORIGINS,
)
_validate_cors_origins(ENVIRONMENT, CORS_ALLOWED_ORIGINS)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Initialize runtime dependencies and release them on shutdown."""
    e2_runtime = None
    validate_security_configuration()
    validate_skill_storage_configuration(ENVIRONMENT)

    await verify_database_schema()
    logger.info("Database schema revision verified")

    from app.skills.seed import install_standard_skill_seeds
    from app.skills.service import skill_service

    async with AsyncSessionLocal() as skill_db:
        installed = await install_standard_skill_seeds(skill_db)
        snapshot = await skill_service.reconcile_registry(skill_db, force=True)
    logger.info(
        "Standard Skill registry initialized: installed=%s revision=%s skills=%s",
        installed,
        snapshot.revision,
        len(snapshot.skills),
    )
    await init_database_session_manager()
    logger.info("数据库会话管理器初始化完成")

    await connect_redis()
    logger.info("Redis连接初始化完成")

    await init_manager.start()
    logger.info("部分资源正在初始化（模型加载、ChromaDB初始化等将在后台继续加载）")

    try:
        from app.agent.mcp.registry import mcp_tool_registry
        from app.agent.skill_registry import skill_registry

        tools = await mcp_tool_registry.refresh()
        skill_registry.reload()
        logger.info(f"MCP 工具发现完成，已加载 {len(tools)} 个工具")
    except Exception as exc:
        logger.warning(f"MCP 工具发现失败，将仅使用本地工具: {exc}")

    skill_registry_stop = asyncio.Event()
    skill_registry_task = asyncio.create_task(
        _reconcile_skill_registry(skill_registry_stop),
        name="standard-skill-registry-reconciler",
    )
    try:
        e2_runtime = build_e2_runner(environ=E2_PROCESS_ENVIRONMENT)
        if e2_runtime is not None:
            configure_default_runner(e2_runtime.runner)
            await e2_runtime.start()
            logger.info("E2 SQL runner lifecycle initialized: enabled=true")
        else:
            configure_default_runner(None)
            logger.info("E2 SQL runner lifecycle initialized: enabled=false")
    except BaseException:
        # A rejected E2 preflight must not leave the already-started
        # reconciler (or an engine created before runner.start failed) alive.
        if e2_runtime is not None:
            await e2_runtime.runner.stop()
            await e2_runtime.engine.dispose()
        configure_default_runner(None)
        skill_registry_stop.set()
        await skill_registry_task
        raise
    try:
        yield
    finally:
        if e2_runtime is not None:
            await e2_runtime.runner.stop()
            await e2_runtime.engine.dispose()
        configure_default_runner(None)
        from app.agent.mcp.provider import mcp_provider
        from app.db.db_config import async_engine

        skill_registry_stop.set()
        await skill_registry_task
        await mcp_provider.close()
        await close_redis()
        logger.info("Redis连接已关闭")
        await async_engine.dispose()
        logger.info("数据库引擎已关闭")


app = FastAPI(lifespan=lifespan)
app.add_middleware(SkillDraftBodyLimitMiddleware)

JSON_ENVELOPE_RESPONSES = {
    200: {
        "model": ApiResponse[Any],
        "description": "Successful response using the canonical API envelope",
    }
}

# 集成限流中间件（暂时注释掉，以免在调试阶段干扰正常请求）
# RateLimitMiddleware 基于令牌桶实现，每 60 秒允许 100 个请求
# 正式部署时可根据接口负载调整限流策略
# 所有限流（包括路由上的 Depends(rate_limit(...))）通过 RATE_LIMIT_ENABLED=false 一键关闭
if os.getenv("RATE_LIMIT_ENABLED", "true" if IS_PRODUCTION else "false").lower() == "true":
    app.add_middleware(
        RateLimitMiddleware,
        limit=int(os.getenv("GLOBAL_RATE_LIMIT_REQUESTS", "300")),
        window=int(os.getenv("GLOBAL_RATE_LIMIT_WINDOW_SECONDS", "60")),
    )

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(round(process_time, 4))
    return response

# 集成API路由
app.include_router(chat_router)
app.include_router(knowledge_router)
app.include_router(health_router, responses=JSON_ENVELOPE_RESPONSES)
app.include_router(user_router, responses=JSON_ENVELOPE_RESPONSES)
app.include_router(note_router)
app.include_router(note_template_router, responses=JSON_ENVELOPE_RESPONSES)
app.include_router(memory_router, responses=JSON_ENVELOPE_RESPONSES)
app.include_router(mcp_router, responses=JSON_ENVELOPE_RESPONSES)
app.include_router(skill_router, responses=JSON_ENVELOPE_RESPONSES)
app.include_router(tool_router, responses=JSON_ENVELOPE_RESPONSES)
app.include_router(model_config_router, responses=JSON_ENVELOPE_RESPONSES)
app.include_router(translate_router)




app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Idempotency-Key"],
)

# 注册异常处理函数
register_exception_handlers(app)

@app.get("/", response_model=ApiResponse[dict[str, str]])
async def root():
    return success_response(data={"message": "Hello World"})


@app.get("/hello/{name}", response_model=ApiResponse[dict[str, str]])
async def say_hello(name: str):
    return success_response(data={"message": f"Hello {name}"})
