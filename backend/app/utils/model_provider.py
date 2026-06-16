import os

from dotenv import load_dotenv
from langchain_community.chat_models import ChatTongyi
from langchain_ollama import ChatOllama

from app.models.model_config import UserModelConfig
from app.utils.clean_openai_chat import CleanOpenAIChatModel
from app.utils.crypto_utils import decrypt_text

load_dotenv()

LOCAL_OLLAMA_CLIENT_KWARGS = {"trust_env": False}


def normalize_openai_base_url(base_url: str) -> str:
    value = (base_url or "").strip().rstrip("/")
    if not value:
        return value
    if value.endswith("/v1"):
        return value
    return f"{value}/v1"


def create_default_chat_model(streaming: bool = True):
    model_name = os.getenv("ALIYUN_MODEL_NAME", os.getenv("CHAT_MODEL_NAME", "qwen3-max"))
    api_key = os.getenv("ALIYUN_ACCESS_KEY_SECRET")
    base_url = os.getenv("ALIYUN_BASE_URL")
    return ChatTongyi(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        streaming=streaming,
        top_p=0.7,
    )


def create_ollama_chat_model(model_name: str, base_url: str | None = None, streaming: bool = True) -> ChatOllama:
    return ChatOllama(
        model=model_name,
        base_url=base_url or "http://localhost:11434",
        streaming=streaming,
        top_p=0.7,
        client_kwargs={**LOCAL_OLLAMA_CLIENT_KWARGS},
    )


def create_chat_model_from_config(config: UserModelConfig | None, streaming: bool = True):
    if config is None or config.model_type == "default":
        return create_default_chat_model(streaming=streaming)

    if config.model_type == "ollama":
        return create_ollama_chat_model(
            model_name=config.model_name,
            base_url=config.base_url,
            streaming=streaming,
        )

    if config.model_type == "openai_compatible":
        return CleanOpenAIChatModel(
            model_name=config.model_name,
            api_key=decrypt_text(config.api_key_encrypted),
            base_url=normalize_openai_base_url(config.base_url),
            streaming=streaming,
        )

    raise ValueError(f"Unsupported model_type: {config.model_type}")
