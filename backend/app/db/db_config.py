import os

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.chat_history import Base as Base

load_dotenv()

DATABASE_SCHEMA_REVISION = "20260817_0001"

ASYNC_DATABASE_URL = (
    f"mysql+aiomysql://{os.getenv('MYSQL_USER', 'root')}:{os.getenv('MYSQL_PASSWORD', '')}"
    f"@{os.getenv('MYSQL_HOST', 'localhost')}:{os.getenv('MYSQL_PORT', '3306')}"
    f"/{os.getenv('MYSQL_DATABASE', 'chat_history')}?charset=utf8mb4"
)
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
    try:
        async with async_engine.connect() as connection:
            result = await connection.execute(text("SELECT version_num FROM alembic_version"))
            current = result.scalar_one_or_none()
    except Exception as exc:
        raise RuntimeError(
            "Database schema is not versioned; run 'alembic upgrade head' for an empty "
            "database or audit and stamp an existing database before startup"
        ) from exc

    if current != DATABASE_SCHEMA_REVISION:
        raise RuntimeError(
            f"Database schema revision {current!r} does not match required "
            f"revision {DATABASE_SCHEMA_REVISION!r}; run 'alembic upgrade head'"
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
