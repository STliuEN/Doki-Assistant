"""Embedding identity includes immutable provider digest and actual vector width."""

import httpx

from app.rag.projection.contracts import ProjectionUnavailable
from app.rag.projection.sources import digest
from app.services.embedding_config_service import EmbeddingConfigData, get_embedding_config_service


def embedding_dict(config):
    return {name: getattr(config, name) for name in ("provider", "model_type", "model_name", "base_url")}


def embedding_fingerprint(config):
    return digest(config)


def embedding_model(value):
    return get_embedding_config_service().create_embedding_model(
        EmbeddingConfigData(id="e5", user_id="e5", **{name: value[name] for name in ("provider", "model_type", "model_name", "base_url")}))


async def model_snapshot(config):
    if config["provider"].lower() != "ollama" or config["model_type"].lower() != "ollama":
        raise ProjectionUnavailable("embedding_revision_provider_unsupported")
    try:
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            base = config["base_url"].rstrip("/")
            response = await client.get(base + "/api/tags")
            response.raise_for_status()
            name = config["model_name"]
            model = next(item for item in response.json()["models"] if item["name"] in {name, name + ":latest"})
            response = await client.post(base + "/api/show", json={"model": name})
            response.raise_for_status()
            info = response.json()["model_info"]
            widths = {value for key, value in info.items() if key.endswith(".embedding_length")}
            if len(widths) != 1 or not model.get("digest"):
                raise ValueError("Missing embedding model identity")
            width = int(widths.pop())
            if width <= 0:
                raise ValueError("Invalid embedding dimension")
            return {**config, "model_digest": model["digest"], "dimension": width,
                    "normalization": "provider_default", "preprocessing": "e5-text-v1"}
    except Exception as error:
        raise ProjectionUnavailable("embedding_identity_unavailable") from error
