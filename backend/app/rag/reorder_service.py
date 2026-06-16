import asyncio
import os
import shutil
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from app.core.logger_handler import logger, project_path
from app.services.reranker_config_service import get_reranker_config_service

# 加载环境变量
load_dotenv()

DEFAULT_RERANKER_MODEL_ID = "BAAI/bge-reranker-v2-m3"
DEFAULT_RERANKER_MODEL_PATH = "./models/bge-reranker-v2-m3"
WEIGHT_FILE_PATTERNS = (
    "model.safetensors",
    "model-*.safetensors",
    "pytorch_model.bin",
    "pytorch_model-*.bin",
)


def _resolve_model_path(path: str | os.PathLike) -> Path:
    raw_path = Path(os.path.expandvars(os.path.expanduser(str(path))))
    if raw_path.is_absolute():
        return raw_path.resolve()
    return (Path(project_path) / raw_path).resolve()


def _get_configured_model_path() -> Path:
    config = get_reranker_config_service().get_config()
    return _resolve_model_path(config.model_path or os.getenv("RERANKER_MODEL_PATH", DEFAULT_RERANKER_MODEL_PATH))


def _get_modelscope_model_name() -> str:
    config = get_reranker_config_service().get_config()
    return config.model_name or os.getenv("RERANKER_MODEL_NAME", DEFAULT_RERANKER_MODEL_ID)


def _get_int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        logger.warning("环境变量 %s 不是有效整数，使用默认值 %s", name, default)
        return default


def _min_weight_bytes() -> int:
    return _get_int_env("RERANKER_MIN_WEIGHT_MB", 50) * 1024 * 1024


def _get_bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_torch_dtype(dtype_name: str):
    if not dtype_name or dtype_name.lower() == "auto":
        return None

    import torch

    dtype_map = {
        "float16": torch.float16,
        "fp16": torch.float16,
        "half": torch.float16,
        "bfloat16": torch.bfloat16,
        "bf16": torch.bfloat16,
        "float32": torch.float32,
        "fp32": torch.float32,
    }
    dtype = dtype_map.get(dtype_name.lower())
    if dtype is None:
        logger.warning("不支持的 RERANKER_TORCH_DTYPE=%s，使用模型默认 dtype", dtype_name)
    return dtype


def _iter_weight_files(model_dir: Path) -> list[Path]:
    weights: list[Path] = []
    for pattern in WEIGHT_FILE_PATTERNS:
        weights.extend([path for path in model_dir.glob(pattern) if path.is_file()])
    return weights


def _validate_model_dir(model_dir: Path) -> tuple[bool, str]:
    if not model_dir.exists():
        return False, f"路径不存在：{model_dir}"
    if not model_dir.is_dir():
        return False, f"不是目录：{model_dir}"
    if not (model_dir / "config.json").exists():
        return False, f"缺少 config.json：{model_dir}"

    weight_files = _iter_weight_files(model_dir)
    if not weight_files:
        return False, f"缺少模型权重文件（model.safetensors 或 pytorch_model.bin）：{model_dir}"

    min_bytes = _min_weight_bytes()
    valid_weights = [path for path in weight_files if path.stat().st_size >= min_bytes]
    if not valid_weights:
        sizes = ", ".join(f"{path.name}={path.stat().st_size}" for path in weight_files)
        return False, f"权重文件疑似未下载完整，当前大小：{sizes}"

    return True, ""


def _is_modelscope_work_dir(path: Path) -> bool:
    return any(part in {"._____temp", ".lock"} for part in path.parts)


def find_model_path(base_path: str | os.PathLike) -> str:
    """在配置目录或 ModelScope 缓存目录中找到真正可加载的模型目录。"""
    model_root = _resolve_model_path(base_path)

    ok, reason = _validate_model_dir(model_root)
    if ok:
        return str(model_root)

    checked_reasons = [reason]
    if model_root.exists():
        for config_path in model_root.rglob("config.json"):
            model_dir = config_path.parent
            if _is_modelscope_work_dir(model_dir):
                continue
            ok, reason = _validate_model_dir(model_dir)
            if ok:
                return str(model_dir)
            checked_reasons.append(reason)

    logger.warning("未找到完整可加载的重排序模型，检查结果：%s", "；".join(checked_reasons))
    return str(model_root)


def _cleanup_incomplete_modelscope_dirs(model_root: Path) -> None:
    for child_name in ("._____temp", ".lock"):
        child = model_root / child_name
        if not child.exists():
            continue
        try:
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
            logger.info("已清理未完成的 ModelScope 下载目录：%s", child)
        except Exception as exc:
            logger.warning("清理 ModelScope 临时目录失败：%s, error=%s", child, exc)


def check_and_download_reranker_model() -> str:
    """检查并下载重排序模型，返回可被 CrossEncoder 加载的模型目录。"""
    from modelscope import snapshot_download
    from tqdm import tqdm

    local_model_path = _get_configured_model_path()
    modelscope_model_name = _get_modelscope_model_name()
    config = get_reranker_config_service().get_config()
    revision = config.revision or os.getenv("RERANKER_MODEL_REVISION", "master")

    try:
        actual_model_path = Path(find_model_path(local_model_path))
        ok, reason = _validate_model_dir(actual_model_path)
        if ok:
            logger.info("检测到完整本地重排序模型：%s", actual_model_path)
            return str(actual_model_path)

        logger.warning("本地重排序模型不完整：%s", reason)
        logger.info("开始从 ModelScope 下载重排序模型：%s", modelscope_model_name)

        local_model_path.mkdir(parents=True, exist_ok=True)
        _cleanup_incomplete_modelscope_dirs(local_model_path)

        with tqdm(total=100, desc='下载模型', leave=True, bar_format='{l_bar}{bar}| {n_fmt}%') as pbar:
            pbar.update(10)
            downloaded_path = snapshot_download(
                model_id=modelscope_model_name,
                local_dir=str(local_model_path),
                revision=revision,
            )
            pbar.update(90)

        candidate_paths = [Path(downloaded_path), Path(find_model_path(local_model_path))]
        for candidate_path in candidate_paths:
            ok, reason = _validate_model_dir(candidate_path)
            if ok:
                logger.info("重排序模型下载完成：%s", candidate_path)
                return str(candidate_path)

        raise RuntimeError(f"下载完成但模型仍不可加载：{reason}")

    except Exception as e:
        logger.error("重排序模型检查失败: %s", str(e))
        raise RuntimeError(f"重排序模型检查失败: {str(e)}")


def _select_device() -> str:
    configured_device = get_reranker_config_service().get_config().device.lower()
    if configured_device and configured_device != "auto":
        return configured_device

    import torch

    if not torch.cuda.is_available():
        return "cpu"

    try:
        major, minor = torch.cuda.get_device_capability(0)
        device_arch = f"sm_{major}{minor}"
        supported_arches = set(torch.cuda.get_arch_list())
        if supported_arches and device_arch not in supported_arches:
            logger.warning(
                "当前 PyTorch CUDA 构建不支持显卡架构 %s，重排序模型将回退到 CPU。"
                "如需 GPU 推理，请安装支持该架构的 PyTorch。",
                device_arch,
            )
            return "cpu"
        torch.empty(1, device="cuda")
        return "cuda"
    except Exception as exc:
        logger.warning("CUDA 设备初始化失败，重排序模型回退到 CPU：%s", exc)
        return "cpu"
class ReorderService:
    """文档重排序服务"""

    def __init__(self):
        self._model = None
        self._model_lock = asyncio.Lock()
        self.reload_config()

    def reload_config(self):
        config = get_reranker_config_service().get_config()
        self.LOCAL_MODEL_PATH = _resolve_model_path(config.model_path)
        self.MODELSCOPE_MODEL_NAME = config.model_name
        self.device = _select_device()
        self.max_length = config.max_length or _get_int_env("RERANKER_MAX_LENGTH", 8192)
        self.batch_size = config.batch_size or _get_int_env("RERANKER_BATCH_SIZE", 1)
        self.torch_dtype = _resolve_torch_dtype(config.torch_dtype or os.getenv("RERANKER_TORCH_DTYPE", "auto"))
        self.trust_remote_code = bool(config.trust_remote_code)
        self._model = None

    def _load_model(self):
        from sentence_transformers import CrossEncoder

        actual_model_path = check_and_download_reranker_model()
        model_kwargs = {}
        if self.torch_dtype is not None:
            model_kwargs["torch_dtype"] = self.torch_dtype

        tokenizer_kwargs = {}
        if "qwen3-reranker" in actual_model_path.lower() or "qwen3-reranker" in self.MODELSCOPE_MODEL_NAME.lower():
            tokenizer_kwargs["padding_side"] = "left"

        logger.info(
            "加载重排序模型：%s, device=%s, max_length=%s, dtype=%s",
            actual_model_path,
            self.device,
            self.max_length,
            self.torch_dtype or "model-default",
        )
        model = CrossEncoder(
            actual_model_path,
            max_length=self.max_length,
            device=self.device,
            local_files_only=True,
            trust_remote_code=self.trust_remote_code,
            model_kwargs=model_kwargs or None,
            tokenizer_kwargs=tokenizer_kwargs or None,
        )
        if hasattr(model, "model"):
            model.model.eval()
        elif hasattr(model, "eval"):
            model.eval()
        logger.info("重排序模型加载成功，使用设备：%s", self.device)
        return model

    async def warmup(self) -> None:
        """启动阶段预热模型，便于提前暴露本地模型缺失或依赖不兼容问题。"""
        await self._get_model()

    async def _get_model(self):
        """懒加载模型实例"""
        if self._model is None:
            async with self._model_lock:
                if self._model is None:
                    self._model = await asyncio.to_thread(self._load_model)
        return self._model

    @property
    async def model(self):
        """获取模型实例（懒加载）"""
        return await self._get_model()

    async def reorder_documents(self, query: str, documents: list[str], thinking_callback=None) -> dict[str, Any]:
        """
        对文档进行重排序
        :param query: 查询语句
        :param documents: 文档列表
        :param thinking_callback: 思考过程回调函数
        :return: 包含重排序结果的字典，格式为：
                 {"success": bool, "documents": List[Dict], "error": str}
        """
        try:
            if not documents:
                return {
                    "success": True,
                    "documents": [],
                    "error": ""
                }

            if thinking_callback:
                await thinking_callback({
                    "type": "thinking",
                    "stage": "reorder",
                    "content": f"正在计算 {len(documents)} 个文档的相关性分数..."
                })

            # 构造查询+文档对
            pairs = [(query, doc) for doc in documents]

            # 使用模型进行批量预测（batch_size=1避免padding令牌报错）
            model = await self.model
            # 禁用梯度计算，提高推理性能
            import torch
            with torch.no_grad():
                scores = model.predict(pairs, batch_size=self.batch_size)

            # 构建结果列表
            scored_documents = []
            for doc, score in zip(documents, scores):
                scored_documents.append({
                    "document": doc,
                    "similarity": float(score)
                })
                logger.info(f"【重排序服务】文档相似度分数: {score:.4f}")

            if thinking_callback:
                score_details = []
                for i, (doc, score) in enumerate(zip(documents, scores), 1):
                    score_details.append({
                        "index": i,
                        "score": round(float(score), 4),
                        "preview": doc[:100] + "..." if len(doc) > 100 else doc
                    })
                await thinking_callback({
                    "type": "thinking",
                    "stage": "reorder",
                    "content": f"已计算完成 {len(documents)} 个文档的相关性分数，按分数降序排序",
                    "details": {
                        "scores": score_details
                    }
                })

            # 按相似度分数降序排序
            sorted_docs = sorted(scored_documents, key=lambda x: x["similarity"], reverse=True)
            logger.info(f"【重排序服务】文档重排序成功，返回 {len(sorted_docs)} 个文档")

            return {
                "success": True,
                "documents": sorted_docs,
                "error": ""
            }
        except Exception as e:
            error_msg = str(e)
            logger.error(f"【重排序服务】重排序失败: {error_msg}")
            return {
                "success": False,
                "documents": [],
                "error": error_msg
            }

    @staticmethod
    async def format_reorder_result(sorted_docs: list[dict]) -> str:
        """
        格式化重排序结果
        :param sorted_docs: 重排序后的文档列表
        :return: 格式化后的字符串
        """
        formatted_result = "重排序后的文档列表：\n"
        for i, doc in enumerate(sorted_docs, 1):
            formatted_result += f"{i}. 相似度: {doc.get('similarity', 0):.4f}\n"
            formatted_result += f"   内容: {doc.get('document', '')}\n\n"
        return formatted_result


# 全局重排序服务实例
reorder_service = ReorderService()
