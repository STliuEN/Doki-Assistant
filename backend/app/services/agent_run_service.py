from dataclasses import dataclass

from fastapi import HTTPException, status
from langchain_core.tools import BaseTool
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.intent_router import route_skills
from app.agent.mcp.registry import mcp_tool_registry
from app.agent.skill_registry import resolve_skills, skill_registry
from app.models.model_config import UserModelConfig
from app.services.model_config_service import get_model_config_service
from app.utils.prompt_loader import load_prompt

CHAT_PROMPT_MODES = {
    "main_prompt": "默认助手",
    "chat_creative_prompt": "创意伙伴",
    "chat_strict_prompt": "严谨助手",
    "chat_teacher_prompt": "教学助手",
}


def build_chat_system_prompt(
    prompt_type: str,
    skill_prompts: list[str] | None = None,
    tool_names: list[str] | None = None,
    notices: list[str] | None = None,
) -> str:
    parts = [load_prompt("main_prompt")]

    if skill_prompts:
        parts.extend([
            "## 当前启用 Skills",
            "\n\n".join(skill_prompts),
            "请只依赖当前已启用 skill 的说明和已绑定工具执行任务；未启用的能力不要假装可用。",
        ])

    if tool_names:
        parts.extend([
            "## 本次可用工具",
            f"你当前只能调用以下工具：{', '.join(tool_names)}。未列出的能力一律视为不可用，不要假装拥有或提及。",
        ])

    if notices:
        parts.extend([
            "## 运行提示",
            "\n".join(f"- {item}" for item in notices),
        ])

    if prompt_type != "main_prompt":
        parts.extend([
            f"## 回答风格（当前模式：{CHAT_PROMPT_MODES[prompt_type]}）",
            load_prompt(prompt_type),
            "风格优先级：在不违反全局规则、工具调用纪律与事实准确的前提下体现以上回答风格；冲突时以全局规则为准。",
        ])

    return "\n\n".join(parts)


@dataclass
class AgentRunPlan:
    """一轮 Agent 执行前的准备结果。"""
    model_config: UserModelConfig | None
    system_prompt: str
    tools: list[BaseTool]
    notices: list[str]
    skill_ids: list[str]
    tool_ids: list[str]


async def prepare_agent_run(
    db: AsyncSession,
    user_id: str,
    *,
    query: str,
    model_config_id: str | None,
    prompt_type: str | None,
    skill_ids: list[str] | None,
    tool_ids: list[str] | None,
) -> AgentRunPlan:
    """统一的 Agent 运行准备：模型解析、prompt 校验、Skill 预路由、MCP 自愈、工具解析、prompt 构建。

    query 与 regenerate 共用本方法（regenerate 的 query 由调用方先取得后传入）。
    """
    # 1. 模型配置解析
    svc = get_model_config_service()
    if model_config_id:
        model_config = await svc.get_config(db, user_id, model_config_id)
        if model_config is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="model config not found")
    else:
        model_config = None

    # 2. prompt_type 校验
    prompt_type = prompt_type or "main_prompt"
    if prompt_type not in CHAT_PROMPT_MODES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="unsupported prompt_type")

    # 3-4. 已选 skill 作为允许集（上界）；预路由只在其中挑出与本次 query 相关的子集。
    # 显式指定 tool_ids 时视为精确控制，跳过路由。
    candidate_skill_ids = skill_ids if skill_ids is not None else skill_registry.default_skill_ids()
    if tool_ids:
        routed_skill_ids = candidate_skill_ids
    else:
        routed_skill_ids = await route_skills(query, candidate_skill_ids)

    # 5. MCP 处于错误态时在此惰性自愈（健康态零开销）；刷新后需 reload 让工具对 agent 可见。
    if await mcp_tool_registry.ensure_fresh():
        skill_registry.reload()

    # 6. 工具解析
    try:
        skill_resolution = resolve_skills(routed_skill_ids, tool_ids)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # 7. system prompt 构建
    tool_names = [tool.name for tool in skill_resolution.tools]
    system_prompt = build_chat_system_prompt(
        prompt_type, skill_resolution.skill_prompts, tool_names, skill_resolution.notices
    )

    return AgentRunPlan(
        model_config=model_config,
        system_prompt=system_prompt,
        tools=skill_resolution.tools,
        notices=skill_resolution.notices,
        skill_ids=skill_resolution.skill_ids,
        tool_ids=skill_resolution.tool_ids,
    )
