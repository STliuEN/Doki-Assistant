from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.core.logger_handler import logger
from app.models.model_config import UserModelConfig
from app.services import session_manager as sm


async def summarize_history(
    factory,
    history: list[tuple[str, str]],
    previous_summary: str = "",
    model_config: UserModelConfig | None = None,
) -> str:
    if not history:
        return previous_summary

    transcript_parts = []
    for index, (user_msg, assistant_msg) in enumerate(history, start=1):
        transcript_parts.append(f"第 {index} 轮\n用户: {user_msg}\n助手: {assistant_msg}")
    transcript = "\n\n".join(transcript_parts)
    prompt = (
        "请把以下旧对话压缩成给后续 Agent 使用的长期上下文摘要。"
        "保留用户目标、偏好、重要约束、未完成事项、关键决策和需要继续跟进的事实。"
        "不要编造知识库、笔记或记忆中心里的事实；这些事实应由工具实时查询。"
        "用中文，控制在 800 字以内。\n\n"
        f"已有摘要:\n{previous_summary or '无'}\n\n"
        f"旧对话:\n{transcript}"
    )
    model = factory.create_chat_model(model_config=model_config)
    response = await model.ainvoke([
        SystemMessage(content="你是对话上下文压缩器，只输出摘要正文。"),
        HumanMessage(content=prompt),
    ])
    return str(response.content).strip()


def build_chat_history_messages(summary: str, history: list[tuple[str, str]]) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    if summary:
        messages.append(SystemMessage(content=f"以下是旧对话摘要，供延续上下文使用：\n{summary}"))
    for user_msg, assistant_msg in history:
        messages.append(HumanMessage(content=user_msg))
        messages.append(AIMessage(content=assistant_msg))
    return messages


async def build_query_context(
    session_id: str,
    user_id: str,
    context_settings,
    model_config: UserModelConfig | None,
    factory,
) -> dict:
    """组装普通查询的上下文：取近期历史 + 摘要（必要时实时生成并落库，失败回退裁剪）。

    返回纯数据 dict，不发 thinking 事件（事件由调用方编排）。
    """
    context = await sm.session_manager.get_context_with_summary(session_id, user_id, context_settings)
    history = context["history"]
    summary = context.get("summary", "")
    used_summary = bool(summary)
    if context.get("history_for_summary"):
        try:
            summary = await summarize_history(
                factory,
                context["history_for_summary"],
                previous_summary=summary,
                model_config=model_config,
            )
            await sm.session_manager.update_session_summary(
                session_id,
                user_id,
                summary,
                context.get("summary_boundary_id"),
                sm.session_manager.estimate_tokens(summary),
            )
            used_summary = True
        except Exception as exc:
            logger.warning(f"【上下文摘要】生成失败，回退裁剪: {exc}")
            history = await sm.session_manager.get_context(session_id, user_id, context_settings)
            summary = ""
            used_summary = False

    return {
        "chat_history": build_chat_history_messages(summary, history),
        "history": history,
        "summary": summary,
        "total_turns": context.get("total_turns", len(history)),
        "used_summary": used_summary,
    }


async def build_regenerate_context(
    session_id: str,
    user_id: str,
    payload: dict,
    context_settings,
) -> dict:
    """组装重新生成的上下文。payload 由调用方预先 get_regenerate_payload 取得。"""
    history = sm.session_manager.trim_history(payload["history"], context_settings)
    summary = ""
    if sm.session_manager.should_use_summary(payload["history"], context_settings):
        metadata = await sm.session_manager.get_session_metadata(session_id, user_id)
        summary = metadata.get("summary", "")
        history = payload["history"][-6:]

    return {
        "chat_history": build_chat_history_messages(summary, history),
        "history": history,
        "summary": summary,
    }
