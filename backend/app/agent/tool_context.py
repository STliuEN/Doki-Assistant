from collections.abc import Callable
from contextvars import ContextVar


current_user_id_var: ContextVar[str | None] = ContextVar("current_user_id", default=None)
thinking_callback_var: ContextVar[Callable | None] = ContextVar("thinking_callback", default=None)
rag_retrieval_settings_var: ContextVar[object | None] = ContextVar("rag_retrieval_settings", default=None)
current_session_id_var: ContextVar[str | None] = ContextVar("current_session_id", default=None)
# 每轮运行的工具调用计数与预算，由 GuardedTool 在执行前自增并硬拦截。
# 形如 {"tool_calls": int, "max_tool_calls": int}
runtime_state_var: ContextVar[dict | None] = ContextVar("runtime_state", default=None)
# 标记本次工具调用已通过用户确认（确认续跑端点设置），GuardedTool 看到后跳过确认拦截。
confirmed_action_var: ContextVar[bool] = ContextVar("confirmed_action", default=False)


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


def set_current_session_id(session_id: str | None) -> None:
    """Set the current session id for tool execution."""
    current_session_id_var.set(session_id)


def get_current_session_id_from_context() -> str | None:
    """Read the current session id for tool execution."""
    return current_session_id_var.get()


def set_runtime_state(state: dict | None) -> None:
    """Set the per-run tool-call counter/budget shared with GuardedTool."""
    runtime_state_var.set(state)


def get_runtime_state_from_context() -> dict | None:
    """Read the per-run tool-call counter/budget."""
    return runtime_state_var.get()


def set_confirmed_action(confirmed: bool) -> None:
    """Mark whether the current tool call was already confirmed by the user."""
    confirmed_action_var.set(confirmed)


def get_confirmed_action_from_context() -> bool:
    """Read whether the current tool call was already confirmed by the user."""
    return confirmed_action_var.get()
