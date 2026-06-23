"""意图预路由：从用户【已选 skill】里挑出与当前 query 相关的子集。

目的：缩小单次请求实际加载的工具集，降低工具选择幻觉与误操作风险。

策略（软打分，规则与 LLM 融合，而非互斥短路）：
1. 规则按权重对候选 skill 累加分数——多个信号叠加，不再"赢家通吃"。
2. 高分项（≥ STRONG_SCORE）直接入选；信号模糊时把规则分作为先验
   交给一次廉价 LLM 仲裁，让其在已选集合内确认/增删。
3. always-on 白名单（低风险只读上下文）永不被裁。
4. 最终对结果做 top-N 截断，既收窄又留召回余量。
5. 任何环节最终为空时安全回退到原候选集，绝不静默丢光能力。

路由只在已选集合内做收窄，绝不引入用户未选择的能力。
"""

from __future__ import annotations

import json
import re

from app.agent.skill_registry import skill_registry
from app.core.logger_handler import logger

# 这些能力是低风险、只读的常驻上下文，永远不应被路由裁掉
# （否则"现在几点""我是谁"这类会因误路由而答不上来）。
# 仅当它们本就在候选集合内时才保留。
ALWAYS_ON: frozenset[str] = frozenset({"system_context"})

# 命中后直接入选的分数线；低于此线只作为先验交给 LLM 仲裁。
STRONG_SCORE = 2.0
# 路由结果最多保留的 skill 数（不含 always-on），留召回余量又避免一次塞太多工具。
MAX_SKILLS = 4

# (正则, skill_id, 权重) 规则表。命中即给该 skill 累加权重，可叠加。
# 权重约定：
#   2.0  专属/高区分度信号，单独命中即可入选；
#   1.0  通用动词/弱信号，需与其他信号叠加或经 LLM 确认。
_RULES: list[tuple[re.Pattern[str], str, float]] = [
    # —— 专属高信号 ——
    (re.compile(r"mcp|连通性?测试|smoke\s*test|冒烟", re.IGNORECASE), "mcp_smoke_test", 2.0),
    (re.compile(r"删除|删掉|删了|移除|清除|清掉|归档|存档"), "memory_cleanup", 2.0),
    (re.compile(r"复习|背一下|背诵|自测|出题|考我|测一下|标记已复习|复盘|记忆曲线"), "review_planner", 2.0),
    (re.compile(r"写成笔记|存成笔记|保存笔记|创建笔记|记成笔记|记到笔记"), "note_writer", 2.0),
    (re.compile(r"知识库|根据资料|根据文档|上传的(文档|资料|文件)"), "knowledge_research", 2.0),
    (re.compile(r"大学|高校|院校|公网\s*ip|域名|ping|端口|连通检测"), "public_info_lookup", 2.0),
    (re.compile(r"提醒我|加待办|加入待办|备忘"), "memory_write", 2.0),
    (re.compile(r"今天有什么|今日(事项|安排|待办)|到期|安排了什么"), "memory_read", 2.0),
    # —— 通用弱信号（需叠加或 LLM 仲裁） ——
    (re.compile(r"记一下|记录|安排|新建|创建|添加|完成|做完|搞定|改成|改名|修改|更新|编辑|延期|推迟|顺延|改期"), "memory_write", 1.0),
    (re.compile(r"待办|有哪些|看看|查一下|列一下|清单|详情"), "memory_read", 1.0),
    (re.compile(r"笔记|我写过|找一下.*记录"), "note_research", 1.0),
    (re.compile(r"文档|资料"), "knowledge_research", 1.0),
    (re.compile(r"几点|现在时间|今天几号|日期|星期几|我是谁|我的\s*id|用户名"), "system_context", 1.0),
]

_ROUTE_PROMPT = (
    "你是一个意图路由器。根据【用户输入】，从下列【候选能力】中选出完成该请求所必需的能力 id，"
    "只选必要的，可多选；不要选无关能力。\n"
    "【规则提示】中的能力是关键词初筛认为可能相关的，仅供参考，你需要结合语义判断是否真的需要。\n"
    "只输出一个 JSON 数组（元素为能力 id 字符串），不要任何解释。例如：[\"memory_read\"]\n\n"
    "候选能力：\n{catalog}\n\n规则提示：{hints}\n\n用户输入：{query}\n\nJSON 数组："
)


def _score_route(query: str, candidate_set: set[str]) -> dict[str, float]:
    """对候选集合内的 skill 按规则累加权重，返回 {skill_id: score}（仅含命中项）。"""
    scores: dict[str, float] = {}
    for pattern, skill_id, weight in _RULES:
        if skill_id in candidate_set and pattern.search(query):
            scores[skill_id] = scores.get(skill_id, 0.0) + weight
    return scores


def _cap(skill_ids: list[str], candidates: list[str]) -> list[str]:
    """截断到 MAX_SKILLS，再并入 always-on（保持候选集中的稳定顺序）。"""
    capped = skill_ids[:MAX_SKILLS]
    always = [sid for sid in candidates if sid in ALWAYS_ON]
    ordered = list(dict.fromkeys(capped + always))
    # 按候选集合原始顺序稳定输出
    return [sid for sid in candidates if sid in ordered]


async def _llm_route(query: str, candidates: list[str], hints: list[str]) -> list[str]:
    from langchain_core.messages import HumanMessage

    from app.core.background_init import init_manager

    lines = []
    for skill_id in candidates:
        skill = skill_registry.get(skill_id)
        if skill:
            lines.append(f"- {skill_id}: {skill.label} —— {skill.description}")
    if not lines:
        return []

    hint_text = "、".join(hints) if hints else "（无）"
    prompt = _ROUTE_PROMPT.format(catalog="\n".join(lines), hints=hint_text, query=query[:500])
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
    """从已选 skill 集合中挑出与 query 相关的子集。

    流程：规则打分 → 高分直选 / 模糊则 LLM 仲裁（带规则先验）→ top-N 截断
    → 并入 always-on → 任意环节为空则安全回退原候选集。
    """
    candidates = list(dict.fromkeys(candidate_skill_ids))
    if len(candidates) <= 1 or not (query or "").strip():
        return candidates
    candidate_set = set(candidates)

    scores = _score_route(query, candidate_set)
    strong = [sid for sid, sc in scores.items() if sc >= STRONG_SCORE]
    # 按得分降序排列规则命中项，得分相同时保持候选集顺序
    ranked = sorted(scores, key=lambda sid: (-scores[sid], candidates.index(sid)))

    # 有强信号：直接采用强信号项（叠加 always-on、截断），不再额外花 LLM。
    if strong:
        result = _cap([sid for sid in ranked if sid in strong], candidates)
        logger.info(f"【意图路由】规则强命中 {result} | scores={scores} | query={query[:40]}")
        return result

    # 无强信号：把规则弱命中作为先验，交给 LLM 在候选集内仲裁。
    try:
        routed = [sid for sid in await _llm_route(query, candidates, ranked) if sid in candidate_set]
        routed = list(dict.fromkeys(routed))
        if routed:
            result = _cap(routed, candidates)
            logger.info(f"【意图路由】LLM 仲裁 {result} | hints={ranked} | query={query[:40]}")
            return result
    except Exception as exc:
        logger.error(f"【意图路由】LLM 兜底失败: {exc}")

    # LLM 无果但规则有弱命中：退而采用弱命中项，仍优于回退全集。
    if ranked:
        result = _cap(ranked, candidates)
        logger.info(f"【意图路由】回退规则弱命中 {result} | scores={scores} | query={query[:40]}")
        return result

    # 完全无信号：安全回退原候选集，不静默丢能力。
    logger.info(f"【意图路由】无信号，回退全部已选 | query={query[:40]}")
    return candidates
