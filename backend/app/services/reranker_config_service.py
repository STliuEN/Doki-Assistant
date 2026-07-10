import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from app.core.logger_handler import logger, project_path

DEFAULT_RERANKER_CONFIG = {
    "provider": "local",
    "model_name": "Qwen/Qwen3-Reranker-4B",
    "model_path": "./models/qwen3-reranker-4b",
    "revision": "master",
    "device": "auto",
    "max_length": 8192,
    "batch_size": 1,
    "torch_dtype": "auto",
    "min_weight_mb": 50,
    "trust_remote_code": False,
}

WEIGHT_FILE_PATTERNS = (
    "model.safetensors",
    "model-*.safetensors",
    "pytorch_model.bin",
    "pytorch_model-*.bin",
)


@dataclass
class RerankerConfig:
    provider: str
    model_name: str
    model_path: str
    revision: str
    device: str
    max_length: int
    batch_size: int
    torch_dtype: str
    min_weight_mb: int
    trust_remote_code: bool
    updated_at: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class RerankerConfigService:
    """本地重排序模型配置服务。

    配置写入 backend/data/reranker_config.json，不写数据库。
    """

    def __init__(self):
        self.config_path = Path(project_path) / "data" / "reranker_config.json"

    def _resolve_path(self, path: str) -> Path:
        raw_path = Path(path).expanduser()
        if raw_path.is_absolute():
            return raw_path.resolve()
        return (Path(project_path) / raw_path).resolve()

    def _relative_path(self, path: Path) -> str:
        try:
            rel = path.resolve().relative_to(Path(project_path).resolve())
            return f"./{rel.as_posix()}"
        except ValueError:
            return str(path.resolve())

    def _from_dict(self, data: dict) -> RerankerConfig:
        merged = {**DEFAULT_RERANKER_CONFIG, **(data or {})}
        return RerankerConfig(
            provider=str(merged.get("provider") or "local"),
            model_name=str(merged.get("model_name") or DEFAULT_RERANKER_CONFIG["model_name"]),
            model_path=str(merged.get("model_path") or DEFAULT_RERANKER_CONFIG["model_path"]),
            revision=str(merged.get("revision") or "master"),
            device=str(merged.get("device") or "auto"),
            max_length=int(merged.get("max_length") or 8192),
            batch_size=int(merged.get("batch_size") or 1),
            torch_dtype=str(merged.get("torch_dtype") or "auto"),
            min_weight_mb=int(merged.get("min_weight_mb") or 50),
            trust_remote_code=bool(merged.get("trust_remote_code", False)),
            updated_at=merged.get("updated_at"),
        )

    def get_config(self) -> RerankerConfig:
        if self.config_path.exists():
            try:
                return self._from_dict(json.loads(self.config_path.read_text(encoding="utf-8")))
            except Exception as exc:
                logger.warning("读取重排序模型配置失败，使用默认配置: %s", exc)

        import os

        return self._from_dict({
            "model_path": os.getenv("RERANKER_MODEL_PATH", DEFAULT_RERANKER_CONFIG["model_path"]),
            "model_name": os.getenv("RERANKER_MODEL_NAME", DEFAULT_RERANKER_CONFIG["model_name"]),
            "revision": os.getenv("RERANKER_MODEL_REVISION", DEFAULT_RERANKER_CONFIG["revision"]),
            "device": os.getenv("RERANKER_DEVICE", DEFAULT_RERANKER_CONFIG["device"]),
            "max_length": os.getenv("RERANKER_MAX_LENGTH", DEFAULT_RERANKER_CONFIG["max_length"]),
            "batch_size": os.getenv("RERANKER_BATCH_SIZE", DEFAULT_RERANKER_CONFIG["batch_size"]),
            "torch_dtype": os.getenv("RERANKER_TORCH_DTYPE", DEFAULT_RERANKER_CONFIG["torch_dtype"]),
            "min_weight_mb": os.getenv("RERANKER_MIN_WEIGHT_MB", DEFAULT_RERANKER_CONFIG["min_weight_mb"]),
            "trust_remote_code": os.getenv("RERANKER_TRUST_REMOTE_CODE", "false").lower() == "true",
        })

    def save_config(self, payload: dict) -> RerankerConfig:
        config = self._from_dict({**self.get_config().to_dict(), **payload})
        config.updated_at = datetime.now().isoformat(timespec="seconds")
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps(config.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return config

    def _is_complete_model_dir(self, model_dir: Path) -> tuple[bool, str]:
        if not model_dir.exists() or not model_dir.is_dir():
            return False, "path_not_found"
        if not (model_dir / "config.json").exists():
            return False, "missing_config"
        weights = []
        for pattern in WEIGHT_FILE_PATTERNS:
            weights.extend([path for path in model_dir.glob(pattern) if path.is_file()])
        if not weights:
            return False, "missing_weights"
        min_bytes = self.get_config().min_weight_mb * 1024 * 1024
        if not any(path.stat().st_size >= min_bytes for path in weights):
            return False, "small_weights"
        return True, ""

    def list_local_models(self) -> list[dict]:
        models_dir = Path(project_path) / "models"
        if not models_dir.exists():
            return []

        candidates = []
        for config_path in models_dir.rglob("config.json"):
            if any(part in {".cache", "._____temp", ".lock"} for part in config_path.parts):
                continue
            model_dir = config_path.parent
            ok, reason = self._is_complete_model_dir(model_dir)
            if not ok:
                continue
            model_path = self._relative_path(model_dir)
            candidates.append({
                "model_path": model_path,
                "model_name": self._infer_model_name(model_dir),
                "label": model_dir.name,
                "complete": True,
                "reason": reason,
            })

        unique = {item["model_path"]: item for item in candidates}
        return sorted(unique.values(), key=lambda item: item["label"].lower())

    def _infer_model_name(self, model_dir: Path) -> str:
        name = model_dir.name.lower()
        if "qwen3-reranker-4b" in name:
            return "Qwen/Qwen3-Reranker-4B"
        if "qwen3-reranker-0.6b" in name or "qwen3-reranker-0-6b" in name:
            return "Qwen/Qwen3-Reranker-0.6B"
        if "bge-reranker-v2-m3" in name:
            return "BAAI/bge-reranker-v2-m3"
        return model_dir.name


_reranker_config_service: RerankerConfigService | None = None


def get_reranker_config_service() -> RerankerConfigService:
    global _reranker_config_service
    if _reranker_config_service is None:
        _reranker_config_service = RerankerConfigService()
    return _reranker_config_service
