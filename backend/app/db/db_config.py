import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.e3_process_environment import E3_PROCESS_ENVIRONMENT
from app.db import schema_revision
from app.db.e3_guard import load_guard_from_environment, parse_e3_target, verify_database_fingerprint
from app.models.chat_history import Base as Base

E2_DATABASE_SCHEMA_REVISION = schema_revision.E2_DATABASE_SCHEMA_REVISION
E3_DATABASE_SCHEMA_REVISION = schema_revision.E3_DATABASE_SCHEMA_REVISION
DATABASE_SCHEMA_REVISION = schema_revision.DATABASE_SCHEMA_REVISION


def _database_url_from_environment() -> str:
    if os.getenv("ENV", "dev").strip().casefold() in {"test", "testing"}:
        return (
            f"mysql+aiomysql://{os.getenv('MYSQL_USER', 'pytest')}:{os.getenv('MYSQL_PASSWORD', 'pytest')}"
            f"@{os.getenv('MYSQL_HOST', '127.0.0.1')}:{os.getenv('MYSQL_PORT', '1')}"
            f"/{os.getenv('MYSQL_DATABASE', 'doki_pytest')}?charset=utf8mb4"
        )
    database_url = E3_PROCESS_ENVIRONMENT.get("E3_DATABASE_URL", "")
    parse_e3_target(database_url)
    return database_url


ASYNC_DATABASE_URL = _database_url_from_environment()
# Compatibility for modules or local scripts that used the historical typo.
ASYNC_DATABSE_URL = ASYNC_DATABASE_URL

async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def verify_database_schema() -> None:
    """Fail startup unless the database has the reviewed Alembic revision."""
    guard = None
    if os.getenv("ENV", "dev").strip().casefold() not in {"test", "testing"}:
        guard = load_guard_from_environment("runtime", environ=E3_PROCESS_ENVIRONMENT)
        if guard.database_url != ASYNC_DATABASE_URL:
            raise RuntimeError("E3 runtime guard database URL does not match the configured engine")
    try:
        async with async_engine.connect() as connection:
            if guard is not None:
                await connection.run_sync(lambda sync: verify_database_fingerprint(sync, guard))
            result = await connection.execute(text("SELECT version_num FROM alembic_version"))
            revisions = tuple(result.scalars())
    except Exception as exc:
        raise RuntimeError(
            "Database schema is not versioned; run 'alembic upgrade head' for an empty "
            "database or audit and stamp an existing database before startup"
        ) from exc

    if revisions != (E3_DATABASE_SCHEMA_REVISION,):
        raise RuntimeError(
            f"Database schema revisions {revisions!r} do not match required revision {E3_DATABASE_SCHEMA_REVISION!r}; run 'alembic upgrade head'"
        )


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_mysql_connection() -> bool:
    try:
        async with async_engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        print(f"MySQL connection failed: {exc}")
        return False
