import json
from typing import Any

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field


class CleanOpenAIChatModel(BaseChatModel):
    """OpenAI-compatible chat model that avoids OpenAI SDK default headers."""

    model_name: str
    api_key: str
    base_url: str
    streaming: bool = False
    temperature: float | None = None
    top_p: float | None = None
    timeout: float = 60.0
    verify_ssl: bool = True
    bound_tools: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "clean-openai-chat"

    def bind_tools(
        self,
        tools: list[dict[str, Any] | type | BaseTool | Any],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ):
        converted = [convert_to_openai_tool(tool) for tool in tools]
        return self.model_copy(update={"bound_tools": converted})

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        payload = self._build_payload(messages, stop=stop, **kwargs)
        data = self._post_sync(payload)
        return self._data_to_chat_result(data)

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        payload = self._build_payload(messages, stop=stop, **kwargs)
        data = await self._post_async(payload)
        return self._data_to_chat_result(data)

    async def _post_async(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        async with httpx.AsyncClient(timeout=self.timeout, verify=self.verify_ssl) as client:
            response = await client.post(url, headers=self._headers(), json=payload)
        if response.status_code >= 400:
            raise RuntimeError(f"{response.status_code} {response.text}")
        return response.json()

    def _post_sync(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        with httpx.Client(timeout=self.timeout, verify=self.verify_ssl) as client:
            response = client.post(url, headers=self._headers(), json=payload)
        if response.status_code >= 400:
            raise RuntimeError(f"{response.status_code} {response.text}")
        return response.json()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
        }

    @staticmethod
    def _data_to_chat_result(data: dict[str, Any]) -> ChatResult:
        choice = data.get("choices", [{}])[0]
        message = choice.get("message") or {}
        additional_kwargs: dict[str, Any] = {}
        if message.get("tool_calls"):
            additional_kwargs["tool_calls"] = message["tool_calls"]

        ai_message = AIMessage(
            content=message.get("content") or "",
            additional_kwargs=additional_kwargs,
            response_metadata={
                "id": data.get("id"),
                "model": data.get("model"),
                "finish_reason": choice.get("finish_reason"),
                "usage": data.get("usage"),
            },
        )
        return ChatResult(generations=[ChatGeneration(message=ai_message)])

    def _build_payload(self, messages: list[BaseMessage], stop: list[str] | None = None, **kwargs: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [self._message_to_dict(message) for message in messages],
            "stream": False,
        }
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        if self.top_p is not None:
            payload["top_p"] = self.top_p
        if stop:
            payload["stop"] = stop
        if self.bound_tools:
            payload["tools"] = self.bound_tools
        return payload

    @staticmethod
    def _message_to_dict(message: BaseMessage) -> dict[str, Any]:
        if message.type == "human":
            return {"role": "user", "content": message.content}
        if message.type == "ai":
            data: dict[str, Any] = {"role": "assistant", "content": message.content or ""}
            tool_calls = message.additional_kwargs.get("tool_calls")
            if tool_calls:
                data["tool_calls"] = tool_calls
                if not message.content:
                    data["content"] = None
            return data
        if message.type == "system":
            return {"role": "system", "content": message.content}
        if message.type == "tool":
            return {
                "role": "tool",
                "content": message.content,
                "tool_call_id": getattr(message, "tool_call_id", None),
            }

        role = getattr(message, "role", None) or message.type
        data = {"role": role, "content": message.content}
        if message.additional_kwargs:
            data.update(json.loads(json.dumps(message.additional_kwargs, default=str)))
        return data
