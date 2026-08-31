from __future__ import annotations

from types import TracebackType
from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class AsyncSessionFactory(Protocol):
    def __call__(self) -> AsyncSession: ...


class UnitOfWorkError(RuntimeError):
    pass


class SqlUnitOfWork:
    """Caller-owned SQL transaction that never commits on context exit."""

    def __init__(self, session_factory: AsyncSessionFactory) -> None:
        self._session_factory = session_factory
        self.session: AsyncSession | None = None
        self._committed = False
        self._closed = False

    async def __aenter__(self) -> SqlUnitOfWork:
        if self.session is not None:
            raise UnitOfWorkError("unit of work cannot be entered twice")
        self.session = self._session_factory()
        await self.session.begin()
        # SQLite defers the physical transaction until the first write.  A
        # nested savepoint before that point becomes the outer transaction and
        # cannot be rolled back by the UoW.  Start it explicitly for local
        # contract tests; MySQL already opens the transaction through begin().
        bind = self.session.get_bind()
        if getattr(getattr(bind, "dialect", None), "name", None) == "sqlite":
            await self.session.execute(text("BEGIN"))
        return self

    def require_session(self) -> AsyncSession:
        if self.session is None or self._closed:
            raise UnitOfWorkError("unit of work is not active")
        return self.session

    async def commit(self) -> None:
        session = self.require_session()
        if self._committed:
            raise UnitOfWorkError("unit of work was already committed")
        await session.commit()
        self._committed = True

    async def rollback(self) -> None:
        session = self.require_session()
        await session.rollback()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc, traceback
        if self.session is None:
            return
        try:
            if not self._committed:
                await self.session.rollback()
        finally:
            await self.session.close()
            self._closed = True


async def run_in_uow(session_factory: AsyncSessionFactory, operation) -> Any:
    async with SqlUnitOfWork(session_factory) as uow:
        result = await operation(uow.require_session())
        await uow.commit()
        return result
