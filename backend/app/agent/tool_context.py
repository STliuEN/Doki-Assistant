from collections.abc import Callable
from contextvars import ContextVar


current_user_id_var: ContextVar[str | None] = ContextVar("current_user_id", default=None)
thinking_callback_var: ContextVar[Callable | None] = ContextVar("thinking_callback", default=None)
rag_retrieval_settings_var: ContextVar[object | None] = ContextVar("rag_retrieval_settings", default=None)


def set_current_user_id(user_id: str) -> None:
    """Set the current user id for tool execution."""
    current_user_id_var.set(user_id)


def get_current_user_id_from_context() -> str | None:
    """Read the current user id for tool execution."""
    return current_user_id_var.get()


def set_thinking_callback(callback: Callable | None) -> None:
    """Set the callback used by tools to report thinking progress."""
    thinking_callback_var.set(callback)


def get_thinking_callback_from_context() -> Callable | None:
    """Read the current thinking callback."""
    return thinking_callback_var.get()


def set_rag_retrieval_settings(settings: object | None) -> None:
    """Set RAG retrieval settings for tool execution."""
    rag_retrieval_settings_var.set(settings)


def get_rag_retrieval_settings_from_context() -> object | None:
    """Read RAG retrieval settings for tool execution."""
    return rag_retrieval_settings_var.get()
