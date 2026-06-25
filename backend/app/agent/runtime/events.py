import json


def preview(value, limit: int = 1000) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def runtime_event(stage: str, content: str, details: dict | None = None) -> dict:
    return {
        "type": "thinking",
        "stage": stage,
        "content": content,
        "details": details or {},
    }


def chunk_text(chunk) -> str:
    """从 on_chat_model_stream 的 chunk 中提取纯文本增量。"""
    content = getattr(chunk, "content", "") or ""
    if isinstance(content, str):
        return content
    # 某些供应商返回分块列表（如 [{"type":"text","text":"..."}]）
    parts = []
    for item in content:
        if isinstance(item, dict):
            parts.append(item.get("text", "") or item.get("content", "") or "")
        else:
            parts.append(str(item))
    return "".join(parts)
