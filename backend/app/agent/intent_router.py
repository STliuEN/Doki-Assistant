"""意图预路由：从用户【已选 skill】里挑出与当前 query 相关的子集。

目的：缩小单次请求实际加载的工具集，降低工具选择幻觉与误操作风险。

策略（语义为主 + 核心关键词保底 + 模糊带 LLM + 阶梯回退）：
1. always_on 的 skill 选中即常驻，不参与收窄竞争。
2. 一小撮关键词规则专守增删改查/复习推进——这些动作语义高度纠缠，
   实测纯语义无法可靠区分，故用关键词给"强信号"兜底。
3. 其余 skill 纯靠 description 的语义相似度路由：加新 skill 只写 yaml，
   不碰本文件。相似度索引从 registry 自动构建并随 skill 变更自愈。
4. 强信号 ∪ 语义直选 取并集，解决"赢家通吃"；只剩模糊带时才焚一次 LLM。
5. 任意环节最终为空都安全回退，绝不静默丢光能力。

路由只在已选集合内做收窄，绝不引入用户未选择的能力。
"""

from __future__ import annotations

import asyncio
import json
import math
import re

from app.agent.skill_registry import skill_registry
from app.core.logger_handler import logger

# —— 阈值（全局常量，不随 skill 数变；按本地 qwen3-embedding:0.6b 校准）——
SIM_FLOOR = 0.35   # 语义相似度绝对下限，低于此不算命中
SIM_GAP = 0.10     # top1 与 top2 的最小差距，够大才算"语义直选"
MAX_SKILLS = 4     # 路由结果最多保留的 skill 数（不含 always_on）

# —— 核心关键词规则：只覆盖语义纠缠的增删改查 + 复习推进 ——
# 新增业务 skill 不需要往这里加，走语义即可。
_KEYWORD_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"删除|删掉|删了|移除|清除|清掉|归档|存档"), "memory_cleanup"),
    (re.compile(r"记一下|记下|新建|创建|添加|加待办|加入待办|提醒我|备忘|"
                r"完成|做完|搞定|改成|改名|修改|更新|编辑|延期|推迟|顺延|改期"), "memory_write"),
    (re.compile(r"今天有什么|今日(事项|安排|待办)|待办|清单|列一下|查一下|到期"), "memory_read"),
    (re.compile(r"复习|背一下|背诵|自测|出题|考我|测一下|标记已复习|复盘|记忆曲线"), "review_planner"),
]

_ROUTE_PROMPT = (
    "你是一个意图路由器。根据【用户输入】，从下列【候选能力】中选出完成该请求所必需的能力 id，"
    "只选必要的，可多选；不要选无关能力。\n"
    "【参考提示】是语义初筛认为可能相关的，仅供参考，需结合语义判断是否真的需要。\n"
    "只输出一个 JSON 数组（元素为能力 id 字符串），不要任何解释。例如：[\"memory_read\"]\n\n"
    "候选能力：\n{catalog}\n\n参考提示：{hints}\n\n用户输入：{query}\n\nJSON 数组："
)

# —— 语义索引缓存（模块级，随 skill 变更自愈）——
_skill_vectors: dict[str, list[float]] = {}
_index_signature: str | None = None


def _embed_text(skill_id: str) -> str:
    """skill 的嵌入文本：label + description（纯 description 方案）。"""
    skill = skill_registry.get(skill_id)
    if not skill:
        return skill_id
    return f"{skill.label}。{skill.description}"


def _registry_signature(skill_ids: list[str]) -> str:
    """基于 id|label|description 的内容签名；任一变化即触发索引重建。"""
    parts = []
    for sid in sorted(skill_ids):
        skill = skill_registry.get(sid)
        if skill:
            parts.append(f"{sid}|{skill.label}|{skill.description}")
    return "\n".join(parts)


async def _ensure_index(skill_ids: list[str]) -> bool:
    """惰性构建/重建语义索引；embed_model 未就绪返回 False（触发非语义回退）。"""
    global _index_signature
    from app.core.background_init import init_manager

    model = init_manager.embed_model
    if model is None:
        return False

    signature = _registry_signature(skill_ids)
    missing = [sid for sid in skill_ids if sid not in _skill_vectors]
    if signature == _index_signature and not missing:
        return True

    # 签名变化（描述被改/skill 增减）→ 全量重建；否则只补缺失项。
    targets = skill_ids if signature != _index_signature else missing
    texts = [_embed_text(sid) for sid in targets]
    try:
        vectors = await asyncio.to_thread(model.embed_documents, texts)
    except Exception as exc:
        logger.error(f"【意图路由】skill 嵌入失败，回退非语义路径: {exc}")
        return False

    if signature != _index_signature:
        _skill_vectors.clear()
    for sid, vec in zip(targets, vectors):
        _skill_vectors[sid] = vec
    _index_signature = signature
    return True


async def _embed_query(query: str) -> list[float] | None:
    from app.core.background_init import init_manager

    model = init_manager.embed_model
    if model is None:
        return None
    try:
        return await asyncio.to_thread(model.embed_query, query[:500])
    except Exception as exc:
        logger.error(f"【意图路由】query 嵌入失败: {exc}")
        return None


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _keyword_strong(query: str, candidate_set: set[str]) -> list[str]:
    """关键词强信号：命中即入选（仅限候选集内）。"""
    hits: list[str] = []
    for pattern, skill_id in _KEYWORD_RULES:
        if skill_id in candidate_set and skill_id not in hits and pattern.search(query):
            hits.append(skill_id)
    return hits


def _semantic_score(query_vec: list[float], routable: list[str]) -> list[tuple[str, float]]:
    """对 routable 候选按相似度降序打分（仅含已建索引的项）。"""
    scored = [
        (sid, _cosine(query_vec, _skill_vectors[sid]))
        for sid in routable
        if sid in _skill_vectors
    ]
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored


async def _llm_route(query: str, candidates: list[str], hints: list[str]) -> list[str]:
    from langchain_core.messages import HumanMessage

    from app.core.background_init import init_manager

    if init_manager.chat_model is None:
        return []
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


def _finalize(selected: list[str], always_on: list[str], candidates: list[str]) -> list[str]:
    """截断到 MAX_SKILLS，并入 always_on，按候选集原始顺序稳定输出。"""
    capped = list(dict.fromkeys(selected))[:MAX_SKILLS]
    keep = set(capped) | set(always_on)
    return [sid for sid in candidates if sid in keep]


async def route_skills(query: str, candidate_skill_ids: list[str]) -> list[str]:
    """从已选 skill 集合中挑出与 query 相关的子集。

    流程：always_on 常驻 → 关键词强信号 ∪ 语义直选 → 仅模糊带则 LLM 仲裁
    → topN 截断 → 阶梯回退。结果始终是候选集合的子集。
    """
    candidates = list(dict.fromkeys(candidate_skill_ids))
    if len(candidates) <= 1 or not (query or "").strip():
        return candidates
    candidate_set = set(candidates)

    always_on = [
        sid for sid in candidates
        if (skill := skill_registry.get(sid)) and skill.always_on
    ]
    # 参与收窄竞争的候选：排除 always_on 与显式 routable=False。
    routable = [
        sid for sid in candidates
        if sid not in always_on
        and (skill := skill_registry.get(sid)) and skill.routable
    ]
    non_routable = [sid for sid in candidates if sid not in always_on and sid not in routable]

    strong = _keyword_strong(query, candidate_set)

    # 语义打分（embed 就绪时）。
    semantic_hit: list[str] = []
    ambiguous: list[str] = []
    index_ready = await _ensure_index(routable)
    query_vec = await _embed_query(query) if index_ready else None
    if query_vec is not None:
        scored = _semantic_score(query_vec, routable)
        above = [(sid, sc) for sid, sc in scored if sc >= SIM_FLOOR]
        if above:
            top_id, top_sc = above[0]
            second = above[1][1] if len(above) > 1 else 0.0
            if top_sc - second >= SIM_GAP:
                # 与次高拉开足够差距 → 语义直选 top1，其余高分入模糊带。
                semantic_hit = [top_id]
                ambiguous = [sid for sid, _ in above[1:4]]
            else:
                # 高分挤作一团 → 全部入模糊带，交 LLM 仲裁。
                ambiguous = [sid for sid, _ in above[:4]]


    union = list(dict.fromkeys(strong + semantic_hit + non_routable))
    if union:
        result = _finalize(union, always_on, candidates)
        logger.info(f"【意图路由】命中 {result} | kw={strong} sem={semantic_hit} | query={query[:40]}")
        return result

    # 无强信号、无语义直选：把模糊带作先验交 LLM 仲裁。
    if ambiguous or (not index_ready and len(routable) > 1):
        hints = ambiguous or routable
        try:
            routed = [s for s in await _llm_route(query, candidates, hints) if s in candidate_set]
            if routed:
                result = _finalize(routed, always_on, candidates)
                logger.info(f"【意图路由】LLM 仲裁 {result} | hints={hints} | query={query[:40]}")
                return result
        except Exception as exc:
            logger.error(f"【意图路由】LLM 兜底失败: {exc}")
        # LLM 无果：退到模糊带（相似度 topN），仍优于全集。
        if ambiguous:
            result = _finalize(ambiguous, always_on, candidates)
            logger.info(f"【意图路由】回退模糊带 {result} | query={query[:40]}")
            return result

    # 完全无信号：安全回退原候选集，不静默丢能力。
    logger.info(f"【意图路由】无信号，回退全部已选 | query={query[:40]}")
    return candidates



