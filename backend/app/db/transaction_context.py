"""Small helpers for request-scoped SQL transactions.

The FastAPI ``get_db`` dependency owns the request commit.  Services can use
this module to distinguish that managed transaction from an explicitly owned
background session and to register work that is safe only after commit.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

MANAGED_TRANSACTION_KEY = "e4_managed_transaction"
UOW_TRANSACTION_KEY = "e4_uow_transaction"
POST_COMMIT_CALLBACKS_KEY = "e4_post_commit_callbacks"

PostCommitCallback = Callable[[], Awaitable[None]]


def mark_managed_transaction(session: Any) -> None:
    """Mark a session as being owned by the request dependency."""

    session.info[MANAGED_TRANSACTION_KEY] = True


def mark_uow_transaction(session: Any) -> None:
    """Mark a session as being owned by :class:`SqlUnitOfWork`."""

    session.info[UOW_TRANSACTION_KEY] = True


def is_managed_transaction(session: Any) -> bool:
    """Return whether the request dependency owns the session commit."""

    return bool(getattr(session, "info", {}).get(MANAGED_TRANSACTION_KEY, False))


def is_uow_transaction(session: Any) -> bool:
    """Return whether a caller-owned UoW controls the session commit."""

    return bool(getattr(session, "info", {}).get(UOW_TRANSACTION_KEY, False))


def register_post_commit(session: Any, callback: PostCommitCallback) -> None:
    """Register an async callback to run only after a successful commit."""

    callbacks = session.info.setdefault(POST_COMMIT_CALLBACKS_KEY, [])
    callbacks.append(callback)


def take_post_commit_callbacks(session: Any) -> tuple[PostCommitCallback, ...]:
    """Remove and return callbacks queued on a session."""

    callbacks = session.info.pop(POST_COMMIT_CALLBACKS_KEY, ())
    return tuple(callbacks)


def clear_post_commit_callbacks(session: Any) -> None:
    """Discard callbacks when the owning transaction rolls back."""

    session.info.pop(POST_COMMIT_CALLBACKS_KEY, None)


async def run_post_commit_callbacks(session: Any) -> None:
    """Run callbacks after a durable commit without changing its outcome."""

    for callback in take_post_commit_callbacks(session):
        try:
            await callback()
        except asyncio.CancelledError:
            # Cancellation after SQL commit is a projection failure, not a
            # rollback signal. The durable outbox/reconciler remains the
            # recovery path for the cancelled callback.
            logging.getLogger(__name__).warning("post-commit callback was cancelled")
        except Exception:
            logging.getLogger(__name__).exception("post-commit callback failed")


async def commit_with_post_commit(session: Any) -> None:
    """Commit an explicitly owned session and then run its callbacks."""

    await session.commit()
    await run_post_commit_callbacks(session)


async def persist_service_write(session: Any, callback: PostCommitCallback | None = None) -> None:
    """Flush a service mutation and commit only for legacy standalone sessions.

    Request dependencies and explicit UoWs own their commit.  Older direct
    service callers create a plain ``AsyncSession`` and historically expected
    persistence before the session closes, so that compatibility path commits
    here while still allowing a post-commit callback.
    """

    await session.flush()
    from app.db.business_authority import uses_business_authority

    if callback is not None and not uses_business_authority(session):
        register_post_commit(session, callback)
    if not is_managed_transaction(session) and not is_uow_transaction(session):
        await session.commit()
        await run_post_commit_callbacks(session)


__all__ = [
    "MANAGED_TRANSACTION_KEY",
    "UOW_TRANSACTION_KEY",
    "POST_COMMIT_CALLBACKS_KEY",
    "PostCommitCallback",
    "clear_post_commit_callbacks",
    "commit_with_post_commit",
    "is_managed_transaction",
    "is_uow_transaction",
    "mark_managed_transaction",
    "register_post_commit",
    "run_post_commit_callbacks",
    "persist_service_write",
    "take_post_commit_callbacks",
]
