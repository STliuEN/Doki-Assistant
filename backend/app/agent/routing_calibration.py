from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
from dataclasses import dataclass, field
from typing import Any

from app.core.logger_handler import logger
from app.skills.registry import RuntimeSkill as SkillDefinition
from app.skills.registry import SkillRegistrySnapshot

DEFAULT_SIM_FLOOR = 0.35
DEFAULT_SIM_GAP = 0.10
CALIBRATION_VERSION = 3  # bump when persisted threshold semantics change
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

# —— 噪声锚定 floor ——
# 部分 embedding（如 qwen3-embedding:4b）存在"黑洞吸引子"：闲聊噪声会高分
# 落到某个 skill（如 knowledge_research）并通过 gap 判定 → 误成自信直选、绕过 LLM 兜底。
# 对策：用一组闲聊噪声实测每个 skill 的"噪声天花板"，仅对【噪声 top-1 真正落到的 skill】
# 把 floor 抬到 noise_ceil 之上。public 这类从不被噪声 top-1 命中的 skill 不受影响，召回不变。
#
# 【关键】只对"主导吸引子"锚定（噪声 top-1 占比 ≥ NOISE_DOMINANCE）：
# - 4b：100% 闲聊塌到 knowledge_research → 真黑洞，锚定（floor 抬到 0.645，噪声全进 LLM）。
# - 0.6b：闲聊四散（review 40% / public 30% / knowledge 20%…），无黑洞。
#   旧逻辑对"偶发 top-1"的 public 也锚定，把 floor 抬到 0.482，而真实 public query
#   只有 0.37~0.43 → 全被误杀。加占比门槛后 0.6b 不再误锚 public，召回恢复。
# 该门槛模型无关、自适应：黑洞模型天然过门槛，散射模型天然不过，无需为 4b/0.6b 分别写常量。
NOISE_MARGIN = 0.04          # 在噪声天花板之上再留的余量
NOISE_FLOOR_CAP = 0.65       # 噪声锚定 floor 的上限（黑洞 skill 可超过 MAX_SIM_FLOOR）
NOISE_DOMINANCE = 0.50       # 噪声 top-1 占比阈值：仅主导吸引子才锚定，挡散射误锚
_DEFAULT_NOISE = (
    "你好呀今天天气不错",
    "随便聊聊",
    "嗯嗯啊啊哦哦",
    "谢谢你帮了大忙",
    "你叫什么名字",
    "讲个笑话吧",
    "我有点累了",
    "在吗",
    "哈哈哈哈",
    "今天好开心",
)


@dataclass(frozen=True)
class RoutingCalibration:
    signature: str
    global_floor: float = DEFAULT_SIM_FLOOR
    global_gap: float = DEFAULT_SIM_GAP
    skill_floor: dict[str, float] = field(default_factory=dict)
    skill_gap: dict[str, float] = field(default_factory=dict)
    noise_ceiling: dict[str, float] = field(default_factory=dict)
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


def skills_signature(
    skill_ids: list[str],
    snapshot: SkillRegistrySnapshot | None = None,
) -> str:
    payload = []
    for sid in sorted(skill_ids):
        skill = snapshot.get(sid) if snapshot is not None else None
        if skill is None and snapshot is not None:
            continue
        if skill is None:
            # Backward-compatible signatures for callers that only have IDs.
            payload.append({"id": sid})
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


def calibration_signature(
    skill_ids: list[str],
    model: Any,
    vector_dim: int | None = None,
    snapshot: SkillRegistrySnapshot | None = None,
) -> str:
    payload = {
        "calibration_version": CALIBRATION_VERSION,
        "embedding": embedding_identity(model, vector_dim),
        "skills": skills_signature(skill_ids, snapshot),
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


def _noise_pool(routable_skills: list[SkillDefinition]) -> list[str]:
    """噪声样本池：默认闲聊 + 各 skill 声明的 negative 示例（去重）。"""
    pool: list[str] = list(_DEFAULT_NOISE)
    for skill in routable_skills:
        pool.extend(skill.routing_examples.get("negative", ()))
    return list(dict.fromkeys(pool))


def _calibration_dir() -> str:
    from app.utils.path_tool import get_data_path

    path = os.path.join(get_data_path(), "routing_calibration")
    os.makedirs(path, exist_ok=True)
    return path


def _calibration_path(signature: str) -> str:
    return os.path.join(_calibration_dir(), f"{signature}.json")


MAX_PERSISTED_CALIBRATIONS = 12  # 磁盘上保留的校准文件上限（按修改时间淘汰最旧的）


def _prune_persisted(keep_signature: str) -> None:
    """淘汰陈旧校准文件：换 embedding / 改 description 都会产生新 signature 文件，
    旧文件不再命中却会无界堆积。按修改时间保留最近 MAX_PERSISTED_CALIBRATIONS 个。"""
    try:
        directory = _calibration_dir()
        files = [
            os.path.join(directory, name)
            for name in os.listdir(directory)
            if name.endswith(".json")
        ]
        if len(files) <= MAX_PERSISTED_CALIBRATIONS:
            return
        keep_path = _calibration_path(keep_signature)
        files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        for stale in files[MAX_PERSISTED_CALIBRATIONS:]:
            if os.path.abspath(stale) == os.path.abspath(keep_path):
                continue  # 永不删刚写入的当前文件
            try:
                os.remove(stale)
            except OSError:
                pass
    except Exception as exc:
        logger.warning(f"【意图路由】清理陈旧阈值文件失败（忽略）: {exc}")


def _load_persisted(signature: str) -> "RoutingCalibration | None":
    """从磁盘读取该 signature 的已调好阈值；不存在/损坏返回 None。"""
    path = _calibration_path(signature)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if data.get("signature") != signature:
            return None
        if int(data.get("calibration_version", 0)) != CALIBRATION_VERSION:
            return None
        return RoutingCalibration(
            signature=signature,
            global_floor=float(data["global_floor"]),
            global_gap=float(data["global_gap"]),
            skill_floor={str(k): float(v) for k, v in data.get("skill_floor", {}).items()},
            skill_gap={str(k): float(v) for k, v in data.get("skill_gap", {}).items()},
            noise_ceiling={str(k): float(v) for k, v in data.get("noise_ceiling", {}).items()},
            unstable_skill_ids=frozenset(data.get("unstable_skill_ids", [])),
        )
    except Exception as exc:
        logger.warning(f"【意图路由】读取持久化阈值失败，将重算: {exc}")
        return None


def _persist(calibration: "RoutingCalibration") -> None:
    """把调好的阈值落盘（按 signature 命名，随 embedding/skill 变更自动失效）。"""
    try:
        payload = {
            "calibration_version": CALIBRATION_VERSION,
            "signature": calibration.signature,
            "global_floor": calibration.global_floor,
            "global_gap": calibration.global_gap,
            "skill_floor": calibration.skill_floor,
            "skill_gap": calibration.skill_gap,
            "noise_ceiling": calibration.noise_ceiling,
            "unstable_skill_ids": sorted(calibration.unstable_skill_ids),
        }
        with open(_calibration_path(calibration.signature), "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        _prune_persisted(calibration.signature)
    except Exception as exc:
        logger.warning(f"【意图路由】持久化阈值失败（不影响本次运行）: {exc}")


async def calibrate_thresholds(
    *,
    model: Any,
    skill_ids: list[str],
    skill_vectors: dict[str, list[float]],
    vector_dim: int | None = None,
    snapshot: SkillRegistrySnapshot | None = None,
) -> RoutingCalibration:
    signature = calibration_signature(skill_ids, model, vector_dim, snapshot)
    if signature in _calibration_cache:
        return _calibration_cache[signature]

    async with _calibration_lock:
        if signature in _calibration_cache:
            return _calibration_cache[signature]

        # 优先复用磁盘上已调好的阈值（embedding/skill 不变即命中）：
        # 启动预热与运行时切换都靠它做到"换模型即换好阈值"、零冷启动。
        persisted = _load_persisted(signature)
        if persisted is not None:
            _calibration_cache[signature] = persisted
            logger.info(
                "【意图路由】命中持久化阈值 "
                f"floor={persisted.global_floor:.3f} gap={persisted.global_gap:.3f} "
                f"unstable={sorted(persisted.unstable_skill_ids)}"
            )
            return persisted

        routable_skills = [
            skill
            for sid in skill_ids
            if snapshot is not None
            and (skill := snapshot.get(sid))
            and skill.routable
            and sid in skill_vectors
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

        # —— 噪声锚定 floor：仅对"主导噪声吸引子"抬高 floor ——
        # 这能修好 4b 上 knowledge_research 这类黑洞吸引子（100% 闲聊塌到它），
        # 又不动 0.6b 的 public（噪声只偶发 30% top-1 命中，达不到主导门槛）。
        noise_pool = _noise_pool(routable_skills)
        noise_ceiling: dict[str, float] = {}
        if noise_pool:
            try:
                noise_vectors = await asyncio.to_thread(model.embed_documents, noise_pool)
            except Exception as exc:
                logger.warning(f"【意图路由】噪声嵌入失败，跳过噪声锚定: {exc}")
                noise_vectors = []
            # 统计每条噪声的 top-1 落点：天花板分数 + 命中次数（判主导用）。
            noise_top1_counts: dict[str, int] = {}
            for nvec in noise_vectors:
                scored = sorted(
                    ((sid, _cosine(nvec, skill_vectors[sid])) for sid in skill_ids if sid in skill_vectors),
                    key=lambda item: item[1],
                    reverse=True,
                )
                if scored:
                    top_id, top_score = scored[0]
                    noise_ceiling[top_id] = max(noise_ceiling.get(top_id, 0.0), top_score)
                    noise_top1_counts[top_id] = noise_top1_counts.get(top_id, 0) + 1
            total_noise = len(noise_vectors)
            for sid, ceiling in noise_ceiling.items():
                # 只锚定"主导吸引子"：闲聊 top-1 占比 ≥ NOISE_DOMINANCE 才算黑洞。
                # 散射命中（如 0.6b public 30%）不锚定，避免把 floor 抬过真实 query、误杀召回。
                dominance = noise_top1_counts.get(sid, 0) / total_noise if total_noise else 0.0
                if dominance < NOISE_DOMINANCE:
                    continue
                raised = _clamp(ceiling + NOISE_MARGIN, MIN_SIM_FLOOR, NOISE_FLOOR_CAP)
                skill_floor[sid] = max(skill_floor.get(sid, global_floor), raised)
                if raised > global_floor:
                    logger.info(
                        f"【意图路由】噪声锚定抬高 floor: {sid} -> {skill_floor[sid]:.3f} "
                        f"(噪声 top-1 占比 {dominance:.0%})"
                    )
            # 仅保留真正锚定的 skill 的 noise_ceiling，供路由层判"噪声抑制"用；
            # 未达主导门槛的散射命中不应触发噪声抑制语义。
            noise_ceiling = {
                sid: c
                for sid, c in noise_ceiling.items()
                if total_noise and noise_top1_counts.get(sid, 0) / total_noise >= NOISE_DOMINANCE
            }

        result = RoutingCalibration(
            signature=signature,
            global_floor=global_floor,
            global_gap=global_gap,
            skill_floor=skill_floor,
            skill_gap=skill_gap,
            noise_ceiling=noise_ceiling,
            unstable_skill_ids=frozenset(unstable),
        )
        _calibration_cache[signature] = result
        _persist(result)
        logger.info(
            "【意图路由】阈值校准完成 "
            f"floor={global_floor:.3f} gap={global_gap:.3f} unstable={sorted(unstable)}"
        )
        return result


def clear_calibration_cache() -> None:
    _calibration_cache.clear()
