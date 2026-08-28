import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.db.e2_guard import load_guard_from_environment, verify_database_fingerprint
from app.models import (
    chat_history,
    embedding_config,
    identity_domain,
    job_domain,
    knowledge_document,
    memory_item,
    model_config,
    note,
    note_template,
    projection_domain,
    skill_domain,
)
from app.models.chat_history import Base

_MODELS = (
    chat_history,
    embedding_config,
    knowledge_document,
    memory_item,
    model_config,
    note,
    note_template,
    identity_domain,
    job_domain,
    projection_domain,
    skill_domain,
)

config = context.config
guard = load_guard_from_environment("migrate")
config.set_main_option("sqlalchemy.url", guard.database_url.replace("%", "%%"))
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=guard.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    verify_database_fingerprint(connection, guard)
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
