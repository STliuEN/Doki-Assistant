import asyncio
import re
from collections.abc import AsyncGenerator
from typing import Any

from langchain_core.messages import HumanMessage

from app.core.logger_handler import logger
from app.models.model_config import UserModelConfig
from app.schemas.sse import encode_sse
from app.utils.model_provider import create_chat_model_from_config
from app.utils.prompt_loader import load_prompt


def _sse_event(payload: dict[str, Any]) -> str:
    return encode_sse(payload)


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        return "".join(parts)
    return str(content)


def _strip_thinking(text: str) -> str:
    value = re.sub(r"<think>.*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL)
    value = value.replace("<think>", "").replace("</think>", "")
    blocked_markers = ("思考过程", "推理", "判断依据", "thinking", "reasoning")
    lines = [
        line for line in value.splitlines()
        if not any(marker in line.lower() for marker in blocked_markers)
    ]
    return "\n".join(lines).strip()


def _format_prompt(
    language_a: str,
    language_b: str,
    text: str,
    fast_mode: bool,
    custom_instruction: str | None = None,
) -> str:
    template = load_prompt("bidirectional_translate_prompt")
    mode_instruction = (
        "快速实时翻译模式。禁止输出思考过程，禁止输出 <think>、</think>、推理说明或判断依据。只输出简洁译文。"
        if fast_mode
        else "整篇翻译模式。可以进行必要的内部思考来保证整段内容一致，但最终只输出译文。"
    )
    body = template.format(
        language_a=language_a.strip(),
        language_b=language_b.strip(),
        mode_instruction=mode_instruction,
        text=text.strip(),
    )
    extra = (custom_instruction or "").strip()
    if extra:
        body = f"用户额外翻译要求：{extra}\n\n{body}"
    if fast_mode:
        return "/no_think\n" + body
    return body


async def stream_dialogue_translation(
    language_a: str,
    language_b: str,
    text: str,
    model_config: UserModelConfig | None = None,
    fast_mode: bool = True,
    custom_instruction: str | None = None,
) -> AsyncGenerator[str, None]:
    yield _sse_event({"type": "response", "content": ""})

    try:
        prompt = _format_prompt(
            language_a,
            language_b,
            text,
            fast_mode=fast_mode,
            custom_instruction=custom_instruction,
        )
        model = create_chat_model_from_config(model_config, streaming=True)

        has_streamed_content = False
        async for chunk in model.astream([HumanMessage(content=prompt)]):
            content = _strip_thinking(_content_to_text(getattr(chunk, "content", chunk)))
            if not content:
                continue

            has_streamed_content = True
            yield _sse_event({"type": "response", "content": content})

        if not has_streamed_content:
            response = await model.ainvoke([HumanMessage(content=prompt)])
            content = _strip_thinking(_content_to_text(getattr(response, "content", response)))
            for index in range(0, len(content), 15):
                yield _sse_event({"type": "response", "content": content[index:index + 15]})
                await asyncio.sleep(0.02)

        yield _sse_event({"type": "done"})
    except Exception as exc:
        logger.error(f"双语实时翻译失败: {exc}", exc_info=True)
        yield _sse_event({"type": "error", "content": f"翻译失败: {exc}"})
        yield _sse_event({"type": "done"})
