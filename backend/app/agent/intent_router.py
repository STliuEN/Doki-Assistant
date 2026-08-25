"""意图预路由：从用户【已选 skill】里挑出与当前 query 相关的子集。

目的：缩小单次请求实际加载的工具集，降低工具选择幻觉与误操作风险。

策略（版本化路由样例 + 语义 + 模糊带 LLM + 安全回退）：
1. always_on 的 skill 选中即常驻，不参与收窄竞争。
2. 正向路由样例提供高置信直接信号，属于安装策略而不是源码业务 ID。
3. 其余 Skill 依靠 description 的语义相似度路由；相似度索引随 Registry revision 自愈。
4. 强信号 ∪ 语义直选 取并集，解决"赢家通吃"；只剩模糊带时才焚一次 LLM。
5. 任意环节最终为空只保留 always-on；不再把全部候选注入上下文。

路由只在已选集合内做收窄，绝不引入用户未选择的能力。
"""

from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from app.agent.routing_calibration import (
    DEFAULT_SIM_FLOOR,
    DEFAULT_SIM_GAP,
    RoutingCalibration,
    calibrate_thresholds,
    calibration_signature,
)
from app.agent.skill_registry import skill_registry
from app.core.logger_handler import logger
from app.skills.registry import SkillRegistrySnapshot, standard_skill_registry

# —— 默认阈值：校准不可用时的保守回退值。实际路由优先使用 embedding/skill 自适应校准值。——
SIM_FLOOR = DEFAULT_SIM_FLOOR   # 语义相似度绝对下限，低于此不算命中
SIM_GAP = DEFAULT_SIM_GAP       # top1 与 top2 的最小差距，够大才算"语义直选"
MAX_SKILLS = 4     # 路由结果最多保留的 skill 数（不含 always_on）

_ROUTE_PROMPT = (
    "你是一个意图路由器。根据【用户输入】，从下列【候选能力】中选出完成该请求所必需的能力 id，"
    "只选必要的，可多选；不要选无关能力。\n"
    "【参考提示】是语义初筛认为可能相关的，仅供参考，需结合语义判断是否真的需要。\n"
    "只输出一个 JSON 数组（元素为能力 id 字符串），不要任何解释。例如：[\"memory_read\"]\n\n"
    "候选能力：\n{catalog}\n\n参考提示：{hints}\n\n用户输入：{query}\n\nJSON 数组："
)

# —— 语义索引缓存（模块级，随 skill/embedding 变更自愈）——
_skill_vectors: dict[str, list[float]] = {}
_index_signature: str | None = None
_index_vector_dim: int | None = None
# 串行化索引重建：避免并发请求重复 embed，或交替写 _skill_vectors 造成抖动。
_index_lock = asyncio.Lock()
_routing_snapshot: ContextVar[SkillRegistrySnapshot | None] = ContextVar(
    "routing_skill_snapshot",
    default=None,
)


@contextmanager
def bind_routing_snapshot(snapshot: SkillRegistrySnapshot) -> Iterator[None]:
    """Pin every lookup made during one asynchronous routing decision."""

    token = _routing_snapshot.set(snapshot)
    try:
        yield
    finally:
        _routing_snapshot.reset(token)


def _get_skill(skill_id: str):
    return skill_registry.get(skill_id, _routing_snapshot.get())


def _all_skills():
    return skill_registry.all(_routing_snapshot.get())


def _default_skill_ids():
    return skill_registry.default_skill_ids(_routing_snapshot.get())


def _embed_text(skill_id: str) -> str:
    """skill 的嵌入文本：label + description（纯 description 方案）。"""
    skill = _get_skill(skill_id)
    if not skill:
        return skill_id
    return f"{skill.label}。{skill.description}"


async def _ensure_index(
    skill_ids: list[str],
) -> tuple[bool, object | None, int | None, dict[str, list[float]]]:
    """惰性构建/重建语义索引；embed_model 未就绪返回 False（触发非语义回退）。"""
    global _index_signature, _index_vector_dim
    from app.core.background_init import init_manager

    model = init_manager.embed_model
    if model is None:
        return False, None, None, {}
    if not skill_ids:
        return True, model, _index_vector_dim, {}

    snapshot = _routing_snapshot.get()
    # 锁内做“判定 + 重建 + 快照”：返回值与计算出的 signature 对应，
    # 即使另一个 revision 紧接着重建模块缓存，本次请求也不会混用向量。
    async with _index_lock:
        missing = [sid for sid in skill_ids if sid not in _skill_vectors]
        vector_dim = _index_vector_dim
        signature = calibration_signature(skill_ids, model, vector_dim, snapshot)
        if signature == _index_signature and not missing:
            return (
                True,
                model,
                vector_dim,
                {sid: list(_skill_vectors[sid]) for sid in skill_ids},
            )

        # 签名变化（描述被改/skill 增减）→ 全量重建；否则只补缺失项。
        targets = skill_ids if signature != _index_signature else missing
        texts = [_embed_text(sid) for sid in targets]
        try:
            vectors = await asyncio.to_thread(model.embed_documents, texts)
        except Exception as exc:
            logger.error(f"【意图路由】skill 嵌入失败，回退非语义路径: {exc}")
            return False, model, vector_dim, {}

        if signature != _index_signature:
            _skill_vectors.clear()
        for sid, vec in zip(targets, vectors):
            _skill_vectors[sid] = vec
        if vectors:
            vector_dim = len(vectors[0])
        signature = calibration_signature(skill_ids, model, vector_dim, snapshot)
        _index_signature = signature
        _index_vector_dim = vector_dim
        return (
            True,
            model,
            vector_dim,
            {sid: list(_skill_vectors[sid]) for sid in skill_ids if sid in _skill_vectors},
        )


async def _embed_skill_vectors(skill_ids: list[str], model: object) -> dict[str, list[float]]:
    """为给定 skill 计算向量但不动模块级索引——供预热对"非当前索引集合"补算用。

    复用已建好的 _skill_vectors，仅 embed 缺失项，避免预热反复 clear/重建全量索引。
    """
    snapshot = _routing_snapshot.get()
    async with _index_lock:
        vector_dim = _index_vector_dim
        signature = calibration_signature(skill_ids, model, vector_dim, snapshot)
        if signature == _index_signature:
            vectors = {
                sid: list(_skill_vectors[sid])
                for sid in skill_ids
                if sid in _skill_vectors
            }
        else:
            vectors = {}
        missing = [sid for sid in skill_ids if sid not in vectors]
        if missing:
            embedded = await asyncio.to_thread(
                model.embed_documents,
                [_embed_text(sid) for sid in missing],
            )
            vectors.update(zip(missing, embedded))
        return vectors


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
    """Use token overlap from versioned positive examples as strong signals."""

    normalized_query = "".join(query.casefold().split())
    query_ngrams = {
        normalized_query[index : index + size]
        for size in (2, 3, 4)
        for index in range(max(0, len(normalized_query) - size + 1))
    }
    hits: list[str] = []
    for skill_id in candidate_set:
        skill = _get_skill(skill_id)
        if skill is None:
            continue
        examples = skill.routing_examples.get("positive", ())
        score = 0
        longest_overlap = 0
        for example in examples:
            normalized = "".join(example.casefold().split())
            if not normalized:
                continue
            if normalized in normalized_query or normalized_query in normalized:
                score += 6
                longest_overlap = max(longest_overlap, min(len(normalized), len(normalized_query)))
                continue
            for size in (4, 3, 2):
                overlaps = sum(
                    1
                    for index in range(max(0, len(normalized) - size + 1))
                    if normalized[index : index + size] in query_ngrams
                )
                if overlaps:
                    longest_overlap = max(longest_overlap, size)
                    score += overlaps
        if score >= 2 and longest_overlap >= 4:
            hits.append(skill_id)
    return hits


def _semantic_score(
    query_vec: list[float], routable: list[str], vectors: dict[str, list[float]]
) -> list[tuple[str, float]]:
    """对 routable 候选按相似度降序打分（仅含已建索引的项）。

    vectors 是调用方在 _ensure_index 之后取的快照，避免与并发重建争用模块级索引。
    """
    scored = [
        (sid, _cosine(query_vec, vectors[sid]))
        for sid in routable
        if sid in vectors
    ]
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored


def _above_floor(scored: list[tuple[str, float]], calibration: RoutingCalibration | None) -> list[tuple[str, float]]:
    above: list[tuple[str, float]] = []
    for sid, score in scored:
        floor = calibration.floor_for(sid) if calibration else SIM_FLOOR
        if score >= floor:
            above.append((sid, score))
    return above


async def warmup_routing() -> None:
    """启动预热：embed_model 就绪后预建语义索引并预加载/计算阈值。

    切换 embedding 模型（改 .env 重启）时，若该模型曾校准过，启动即命中磁盘缓存、
    在首个请求前就备好对应阈值；未校准过则现算一次并落盘，下次重启即命中。

    实现：先用"默认集"建好模块级索引（运行时最常命中的就是它），其余集合所需的
    向量用 _embed_skill_vectors 在不动模块索引的前提下补算，避免反复 clear/重建。
    """
    if _routing_snapshot.get() is None:
        with bind_routing_snapshot(standard_skill_registry.snapshot):
            await warmup_routing()
        return
    try:
        full_routable = [s.id for s in _all_skills() if s.routable]
        default_routable = [
            sid
            for sid in _default_skill_ids()
            if (skill := _get_skill(sid)) and skill.routable and not skill.always_on
        ]
        # 默认集放最后建模块索引：让运行时常见请求直接命中、无需重建。
        skill_sets = [s for s in (full_routable, default_routable) if s]
        if not skill_sets:
            return

        primary = skill_sets[-1]
        index_ready, embed_model, vector_dim, primary_vectors = await _ensure_index(primary)
        if not index_ready or embed_model is None:
            return

        warmed: set[tuple[str, ...]] = set()
        for routable in skill_sets:
            key = tuple(sorted(routable))
            if key in warmed:
                continue
            warmed.add(key)
            # 复用已建索引，仅为该集合补算缺失向量（不触碰模块级 _skill_vectors）。
            vectors = (
                primary_vectors
                if tuple(routable) == tuple(primary)
                else await _embed_skill_vectors(routable, embed_model)
            )
            await calibrate_thresholds(
                model=embed_model,
                skill_ids=routable,
                skill_vectors=vectors,
                vector_dim=vector_dim,
                snapshot=_routing_snapshot.get(),
            )
        logger.info("✅ 意图路由预热完成（语义索引 + 阈值已就绪）")
    except Exception as exc:
        logger.warning(f"【意图路由】预热失败（将在首个请求时惰性构建）: {exc}")


def _has_direct_gap(top_id: str, top_sc: float, second: float, calibration: RoutingCalibration | None) -> bool:
    if calibration and top_id in calibration.unstable_skill_ids:
        return False
    gap = calibration.gap_for(top_id) if calibration else SIM_GAP
    return top_sc - second >= gap


async def _llm_route(query: str, candidates: list[str], hints: list[str]) -> list[str]:
    from langchain_core.messages import HumanMessage

    from app.core.background_init import init_manager

    if init_manager.chat_model is None:
        return []
    lines = []
    for skill_id in candidates:
        skill = _get_skill(skill_id)
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
    if _routing_snapshot.get() is None:
        with bind_routing_snapshot(standard_skill_registry.snapshot):
            return await route_skills(query, candidate_skill_ids)

    candidates = list(dict.fromkeys(candidate_skill_ids))
    if len(candidates) <= 1:
        return candidates
    candidate_set = set(candidates)

    always_on = [
        sid for sid in candidates
        if (skill := _get_skill(sid)) and skill.always_on
    ]
    if not (query or "").strip():
        return always_on
    # 参与收窄竞争的候选：排除 always_on 与显式 routable=False。
    routable = [
        sid for sid in candidates
        if sid not in always_on
        and (skill := _get_skill(sid)) and skill.routable
    ]
    non_routable = [sid for sid in candidates if sid not in always_on and sid not in routable]

    strong = _keyword_strong(query, candidate_set)

    # 语义打分（embed 就绪时）。
    semantic_hit: list[str] = []
    ambiguous: list[str] = []
    noise_suppressed = False
    index_ready, embed_model, vector_dim, vectors_snapshot = await _ensure_index(routable)
    query_vec = await _embed_query(query) if index_ready else None
    calibration: RoutingCalibration | None = None
    if index_ready and embed_model is not None:
        calibration = await calibrate_thresholds(
            model=embed_model,
            skill_ids=routable,
            skill_vectors=vectors_snapshot,
            vector_dim=vector_dim,
            snapshot=_routing_snapshot.get(),
        )
    if query_vec is not None:
        scored = _semantic_score(query_vec, routable, vectors_snapshot)
        above = _above_floor(scored, calibration)
        if above:
            top_id, top_sc = above[0]
            raw_top_id = scored[0][0] if scored else None
            raw_second = scored[1][1] if len(scored) > 1 else 0.0
            if top_id == raw_top_id and _has_direct_gap(top_id, top_sc, raw_second, calibration):
                # 与次高拉开足够差距 → 语义直选 top1，其余高分入模糊带。
                semantic_hit = [top_id]
                ambiguous = [sid for sid, _ in above[1:4]]
            else:
                # raw_top_id != top_id 已蕴含"原始 top1 被自身 floor 挡掉"
                # （否则 above[0] 就会等于 scored[0]），无需再比一次分数。
                # 仅当被挡掉的 top1 是噪声吸引子时标记噪声抑制。
                noise_suppressed = (
                    calibration is not None
                    and raw_top_id is not None
                    and raw_top_id != top_id
                    and raw_top_id in calibration.noise_ceiling
                )
                # 高分挤作一团，或原始 top1 被 floor 挡掉后剩下的候选不再允许顺位直选。
                ambiguous = [sid for sid, _ in above[:4]]
        elif scored and calibration is not None:
            # 没有任何候选过 floor：若 top1 是噪声吸引子，视为噪声抑制。
            raw_top_id = scored[0][0]
            noise_suppressed = raw_top_id in calibration.noise_ceiling


    union = list(dict.fromkeys(strong + semantic_hit + non_routable))
    if union:
        result = _finalize(union, always_on, candidates)
        logger.info(f"【意图路由】命中 {result} | kw={strong} sem={semantic_hit} | query={query[:40]}")
        return result

    # 无强信号、无语义直选：把模糊带作先验交 LLM 仲裁。
    if ambiguous or noise_suppressed or (not index_ready and len(routable) > 1):
        # 噪声抑制场景不传递顺位候选 hints，避免 knowledge 黑洞被挡下后又把闲聊偏向第二名。
        hints = [] if noise_suppressed else (ambiguous or routable)
        llm_completed = False
        try:
            routed = [s for s in await _llm_route(query, candidates, hints) if s in candidate_set]
            llm_completed = True
            if routed:
                result = _finalize(routed, always_on, candidates)
                logger.info(f"【意图路由】LLM 仲裁 {result} | hints={hints} | query={query[:40]}")
                return result
        except Exception as exc:
            logger.error(f"【意图路由】LLM 兜底失败: {exc}")
        if noise_suppressed and llm_completed:
            result = _finalize([], always_on, candidates)
            logger.info(f"【意图路由】噪声抑制后 LLM 判空 {result} | hints={hints} | query={query[:40]}")
            return result
        # LLM 无果：退到模糊带（相似度 topN），仍优于全集。
        if ambiguous:
            result = _finalize(ambiguous, always_on, candidates)
            logger.info(f"【意图路由】回退模糊带 {result} | query={query[:40]}")
            return result

    # 完全无信号：仅保留受信 always-on，不把全部候选注入上下文。
    result = _finalize([], always_on, candidates)
    logger.info(f"【意图路由】无信号，仅保留常驻能力 {result} | query={query[:40]}")
    return result
