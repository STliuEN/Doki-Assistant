from __future__ import annotations

import asyncio
import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any

from app.agent.skill_registry import SkillDefinition, skill_registry
from app.core.logger_handler import logger

DEFAULT_SIM_FLOOR = 0.35
DEFAULT_SIM_GAP = 0.10
# floor 是"宽松下界"，不是主判据：真正的判别器是 gap。
# floor 必须 per-skill（不同 skill 相似度量纲差异大：public≈0.35 vs knowledge≈0.81），
# 且封顶，避免高分 skill 把阈值抬高、误杀低量纲 skill（如 public_info_lookup）。
MIN_SIM_FLOOR = 0.18   # floor 下限，给低量纲 skill 留召回空间
MAX_SIM_FLOOR = 0.42   # floor 上限：floor 只是宽松下界，判别权交给 gap。
                       # 封顶避免高分 skill（knowledge≈0.8）floor 抬太高误杀真实 query。
FLOOR_MARGIN = 0.27    # 关键余量：实测【curated 正例】系统性高估【真实简短 query】~0.2~0.25
                       # （如 public 正例"查询武汉大学公开资料"≈0.61，但真实"武汉大学哪年建校"≈0.37）。
                       # floor 必须落在 skill 自身正例基线之下 ~0.27，才不会误杀真实 query。
MIN_SIM_GAP = 0.03
MAX_SIM_GAP = 0.18     # gap 上限，避免高分 skill 把直选门槛抬到不可达
GAP_FACTOR = 0.60      # 对 skill 自身 gap 中位数的保守折扣
UNSTABLE_GAP = 0.04    # gap 中位数低于此 → 标记 unstable（强制走模糊带/LLM）


@dataclass(frozen=True)
class RoutingCalibration:
    signature: str
    global_floor: float = DEFAULT_SIM_FLOOR
    global_gap: float = DEFAULT_SIM_GAP
    skill_floor: dict[str, float] = field(default_factory=dict)
    skill_gap: dict[str, float] = field(default_factory=dict)
    unstable_skill_ids: frozenset[str] = field(default_factory=frozenset)

    def floor_for(self, skill_id: str) -> float:
        return self.skill_floor.get(skill_id, self.global_floor)

    def gap_for(self, skill_id: str) -> float:
        return self.skill_gap.get(skill_id, self.global_gap)


_calibration_cache: dict[str, RoutingCalibration] = {}
_calibration_lock = asyncio.Lock()


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * percentile
    lower = math.floor(pos)
    upper = math.ceil(pos)
    if lower == upper:
        return ordered[lower]
    weight = pos - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def embedding_identity(model: Any, vector_dim: int | None = None) -> str:
    provider = type(model).__module__ + "." + type(model).__name__
    model_name = (
        getattr(model, "model", None)
        or getattr(model, "model_name", None)
        or getattr(model, "model_id", None)
        or ""
    )
    base_url = getattr(model, "base_url", None) or getattr(model, "url", None) or ""
    payload = {
        "provider": str(provider),
        "model": str(model_name),
        "base_url": str(base_url),
        "vector_dim": vector_dim,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def skills_signature(skill_ids: list[str]) -> str:
    payload = []
    for sid in sorted(skill_ids):
        skill = skill_registry.get(sid)
        if not skill:
            continue
        payload.append({
            "id": skill.id,
            "label": skill.label,
            "description": skill.description,
            "routable": skill.routable,
            "routing_examples": {
                key: list(value)
                for key, value in sorted(skill.routing_examples.items())
            },
        })
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def calibration_signature(skill_ids: list[str], model: Any, vector_dim: int | None = None) -> str:
    payload = {
        "embedding": embedding_identity(model, vector_dim),
        "skills": skills_signature(skill_ids),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _fallback_positive_examples(skill: SkillDefinition) -> list[str]:
    return [
        skill.label,
        skill.description,
        f"{skill.label}：{skill.description}",
    ]


def _positive_examples(skill: SkillDefinition) -> list[str]:
    configured = list(skill.routing_examples.get("positive", ()))
    return configured or _fallback_positive_examples(skill)


async def calibrate_thresholds(
    *,
    model: Any,
    skill_ids: list[str],
    skill_vectors: dict[str, list[float]],
    vector_dim: int | None = None,
) -> RoutingCalibration:
    signature = calibration_signature(skill_ids, model, vector_dim)
    if signature in _calibration_cache:
        return _calibration_cache[signature]

    async with _calibration_lock:
        if signature in _calibration_cache:
            return _calibration_cache[signature]

        routable_skills = [
            skill
            for sid in skill_ids
            if (skill := skill_registry.get(sid)) and skill.routable and sid in skill_vectors
        ]
        if len(routable_skills) <= 1:
            result = RoutingCalibration(signature=signature)
            _calibration_cache[signature] = result
            return result

        examples: list[tuple[str, str]] = []
        for skill in routable_skills:
            examples.extend((skill.id, text) for text in _positive_examples(skill))
        if not examples:
            result = RoutingCalibration(signature=signature)
            _calibration_cache[signature] = result
            return result

        try:
            query_vectors = await asyncio.to_thread(model.embed_documents, [text for _, text in examples])
        except Exception as exc:
            logger.error(f"【意图路由】阈值校准失败，使用默认阈值: {exc}")
            result = RoutingCalibration(signature=signature)
            _calibration_cache[signature] = result
            return result

        gaps: list[float] = []
        scores_by_skill: dict[str, list[float]] = {}
        gaps_by_skill: dict[str, list[float]] = {}
        unstable: set[str] = set()

        for (target_id, _text), query_vec in zip(examples, query_vectors):
            scored = [
                (sid, _cosine(query_vec, skill_vectors[sid]))
                for sid in skill_ids
                if sid in skill_vectors
            ]
            scored.sort(key=lambda item: item[1], reverse=True)
            target_score = next((score for sid, score in scored if sid == target_id), 0.0)
            best_negative = next((score for sid, score in scored if sid != target_id), 0.0)
            gap = target_score - best_negative
            gaps.append(gap)
            scores_by_skill.setdefault(target_id, []).append(target_score)
            gaps_by_skill.setdefault(target_id, []).append(gap)

        # floor 是宽松下界：取各 skill 正例低分位的中位数再减余量并封顶。
        # 不能直接用全局 p10——高量纲 skill（knowledge≈0.81）会把阈值抬高、
        # 误杀低量纲 skill（public≈0.35）。故 floor 主要在 per-skill 上生效，
        # 全局值仅作未知 skill 的兜底。
        per_skill_floor_bases = [
            _percentile(scores, 0.25)
            for scores in scores_by_skill.values()
            if scores
        ]
        global_floor = _clamp(
            _percentile(sorted(per_skill_floor_bases), 0.50) - FLOOR_MARGIN,
            MIN_SIM_FLOOR,
            MAX_SIM_FLOOR,
        )
        # gap 是主判据，且是差值、对同源膨胀天然抵消：取全局 gap 中位数的保守折扣。
        global_gap = _clamp(_percentile(gaps, 0.50) * GAP_FACTOR, MIN_SIM_GAP, MAX_SIM_GAP)

        skill_floor: dict[str, float] = {}
        skill_gap: dict[str, float] = {}
        for skill in routable_skills:
            skill_scores = scores_by_skill.get(skill.id, [])
            skill_gaps = gaps_by_skill.get(skill.id, [])
            if skill_scores:
                # 该 skill 自身正例的低分位减余量——贴合各自量纲，给真实 query 留召回空间。
                skill_floor[skill.id] = _clamp(
                    _percentile(skill_scores, 0.25) - FLOOR_MARGIN,
                    MIN_SIM_FLOOR,
                    MAX_SIM_FLOOR,
                )
            if skill_gaps:
                median_gap = _percentile(skill_gaps, 0.50)
                # gap 中位数过小 → 与其他 skill 语义高度纠缠，永不语义直选（强制模糊带/LLM）。
                if median_gap < UNSTABLE_GAP:
                    unstable.add(skill.id)
                skill_gap[skill.id] = _clamp(median_gap * GAP_FACTOR, MIN_SIM_GAP, MAX_SIM_GAP)

        result = RoutingCalibration(
            signature=signature,
            global_floor=global_floor,
            global_gap=global_gap,
            skill_floor=skill_floor,
            skill_gap=skill_gap,
            unstable_skill_ids=frozenset(unstable),
        )
        _calibration_cache[signature] = result
        logger.info(
            "【意图路由】阈值校准完成 "
            f"floor={global_floor:.3f} gap={global_gap:.3f} unstable={sorted(unstable)}"
        )
        return result


def clear_calibration_cache() -> None:
    _calibration_cache.clear()
