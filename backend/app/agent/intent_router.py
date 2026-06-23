"""意图预路由：从用户【已选 skill】里挑出与当前 query 相关的子集。

目的：缩小单次请求实际加载的工具集，降低工具选择幻觉与误操作风险。
策略：规则优先（零延迟、零成本），未命中再用一次廉价 LLM 兜底；
都失败时安全回退为全部已选 skill。

路由只在已选集合内做收窄，绝不引入用户未选择的能力。
"""

from __future__ import annotations

import json
import re

from app.agent.skill_registry import skill_registry
from app.core.logger_handler import logger

# 关键词 → skill_id 规则。命中任意条即走快速路径；按 query 出现的信号叠加匹配。
_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"mcp|工具连通|连通测试|连通性测试|smoke\s*test|冒烟", re.IGNORECASE), "mcp_smoke_test"),
    (re.compile(r"删除|删掉|删了|移除|清除|清掉|归档|存档"), "memory_cleanup"),
    (re.compile(r"复习|背一下|背诵|自测|出题|考我|测一下|标记已复习|复盘|记忆曲线"), "review_planner"),
    (
        re.compile(
            r"记一下|记录|提醒我|备忘|加待办|加入|新建|创建|添加|安排|"
            r"完成|做完|搞定|改成|改名|修改|更新|编辑|延期|推迟|顺延|改期"
        ),
        "memory_write",
    ),
    (re.compile(r"今天有什么|今日|待办|有哪些|看看|查一下|列一下|清单|详情|到期|安排了什么"), "memory_read"),
    (re.compile(r"写成笔记|存成笔记|保存笔记|创建笔记|记成笔记"), "note_writer"),
    (re.compile(r"笔记|我写过|找一下.*记录"), "note_research"),
    (re.compile(r"知识库|文档|资料|根据资料|上传的"), "knowledge_research"),
    (re.compile(r"几点|现在时间|今天几号|日期|星期几|我是谁|我的\s*id|用户名"), "system_context"),
]

_ROUTE_PROMPT = (
    "你是一个意图路由器。根据【用户输入】，从下列【候选能力】中选出完成该请求所必需的能力 id，"
    "只选必要的，可多选；不要选无关能力。\n"
    "只输出一个 JSON 数组（元素为能力 id 字符串），不要任何解释。例如：[\"memory_read\"]\n\n"
    "候选能力：\n{catalog}\n\n用户输入：{query}\n\nJSON 数组："
)


def _rule_route(query: str, candidate_set: set[str]) -> list[str]:
    matched: list[str] = []
    for pattern, skill_id in _RULES:
        if skill_id in candidate_set and skill_id not in matched and pattern.search(query):
            matched.append(skill_id)
    return matched


async def _llm_route(query: str, candidates: list[str]) -> list[str]:
    from langchain_core.messages import HumanMessage

    from app.core.background_init import init_manager

    lines = []
    for skill_id in candidates:
        skill = skill_registry.get(skill_id)
        if skill:
            lines.append(f"- {skill_id}: {skill.label} —— {skill.description}")
    if not lines:
        return []

    prompt = _ROUTE_PROMPT.format(catalog="\n".join(lines), query=query[:500])
    response = await init_manager.chat_model.ainvoke([HumanMessage(content=prompt)])
    raw = (response.content or "").strip()

    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.lower().startswith("json"):
            raw = raw[4:]
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end == -1 or end < start:
        return []
    data = json.loads(raw[start : end + 1])
    return [str(item) for item in data] if isinstance(data, list) else []


async def route_skills(query: str, candidate_skill_ids: list[str]) -> list[str]:
    """从已选 skill 集合中挑出与 query 相关的子集；不收窄非记忆类时按原集合返回。"""
    candidates = list(dict.fromkeys(candidate_skill_ids))
    if len(candidates) <= 1 or not (query or "").strip():
        return candidates
    candidate_set = set(candidates)

    matched = _rule_route(query, candidate_set)
    if matched:
        logger.info(f"【意图路由】规则命中 {matched} | query={query[:40]}")
        return matched

    try:
        routed = [sid for sid in await _llm_route(query, candidates) if sid in candidate_set]
        routed = list(dict.fromkeys(routed))
        if routed:
            logger.info(f"【意图路由】LLM 选择 {routed} | query={query[:40]}")
            return routed
    except Exception as exc:
        logger.error(f"【意图路由】LLM 兜底失败，回退全部已选: {exc}")

    return candidates
