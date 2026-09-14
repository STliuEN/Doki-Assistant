"""One serialized, cached local reranker; no downloads or model-directory mutation."""

import asyncio
import hashlib
import json
import threading
from pathlib import Path

from app.rag.projection.contracts import ProjectionUnavailable
from app.rag.projection.sources import digest

MODEL_ROOT = Path(__file__).resolve().parents[3] / "models"
MODEL_NAMES = ("qwen3-reranker-4b", "qwen3-reranker-0.6b", "bge-reranker-v2-m3")
_lock = threading.Lock()
_fingerprints = {}
_loaded_key = None
_loaded_model = None


def fingerprint(model_name: str) -> dict:
    if model_name not in MODEL_NAMES:
        raise ProjectionUnavailable("reranker_model_unsupported")
    path = (MODEL_ROOT / model_name).resolve()
    if not path.is_relative_to(MODEL_ROOT.resolve()):
        raise ProjectionUnavailable("reranker_path_invalid")
    try:
        index = path / "model.safetensors.index.json"
        names = sorted(set(json.loads(index.read_text(encoding="utf-8"))["weight_map"].values())) if index.is_file() else ["model.safetensors"]
        names += ["config.json", "tokenizer.json", "tokenizer_config.json"]
        if model_name.startswith("qwen3"):
            names += ["modules.json", "1_LogitScore/config.json"]
        if index.is_file():
            names.append(index.name)
        files = [(name, (path / name).resolve()) for name in sorted(set(names))]
        if any(not item.is_relative_to(path) or not item.is_file() or item.stat().st_size == 0 for _, item in files):
            raise ValueError("Incomplete local model")
        signature = tuple((name, item.stat().st_size, item.stat().st_mtime_ns) for name, item in files)
        cached = _fingerprints.get(model_name)
        if cached and cached[0] == signature:
            return cached[1]
        manifest = []
        for name, item in files:
            with item.open("rb") as handle:
                manifest.append({"name": name, "bytes": item.stat().st_size, "sha256": hashlib.file_digest(handle, "sha256").hexdigest()})
        value = {"model": model_name, "digest": digest(manifest), "files": manifest, "max_length": 2048, "batch_size": 1, "dtype": "auto"}
        _fingerprints[model_name] = (signature, value)
        return value
    except ProjectionUnavailable:
        raise
    except Exception as error:
        raise ProjectionUnavailable("reranker_cache_incomplete") from error


async def model_fingerprint(model_name: str) -> dict:
    def run():
        with _lock:
            return fingerprint(model_name)
    return await asyncio.to_thread(run)


def _predict(query, documents, model_name, expected_digest):
    global _loaded_key, _loaded_model
    with _lock:
        config = fingerprint(model_name)
        if expected_digest and config["digest"] != expected_digest:
            raise ProjectionUnavailable("reranker_model_changed")
        key = (model_name, config["digest"])
        import torch
        if _loaded_key != key:
            from sentence_transformers import CrossEncoder
            _loaded_model = None
            _loaded_key = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            model = CrossEncoder(str(MODEL_ROOT / model_name), max_length=config["max_length"],
                device="cuda" if torch.cuda.is_available() else "cpu", local_files_only=True, trust_remote_code=False,
                model_kwargs={"torch_dtype": "auto"},
                processor_kwargs={"padding_side": "left"} if model_name.startswith("qwen3") else None)
            model.model.eval()
            _loaded_model, _loaded_key = model, key
        with torch.inference_mode():
            values = _loaded_model.predict([(query, text) for text in documents], batch_size=1, show_progress_bar=False)
        if fingerprint(model_name)["digest"] != config["digest"]:
            raise ProjectionUnavailable("reranker_model_changed")
        return [float(value) for value in values]


async def score(query: str, documents: list[str], *, model_name: str, expected_digest: str | None = None) -> list[float]:
    try:
        return await asyncio.to_thread(_predict, query, documents, model_name, expected_digest)
    except ProjectionUnavailable:
        raise
    except Exception as error:
        raise ProjectionUnavailable("reranker_unavailable") from error
