from __future__ import annotations

import ipaddress
import json
import re
from html import unescape
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations


mcp = FastMCP("Doki Public Info Lookup")

UNIVERSITY_API_URL = "https://api.52vmy.cn/api/query/daxue"
PING_API_URL = "https://test.harumoe.cn/api/other/ping"
USER_AGENT = "Doki-Assistant-MCP/1.0"
MAX_RESPONSE_BYTES = 128 * 1024
ALLOWED_LANGS = {"zh-cn", "ru-ru", "en-us", "ja-jp", "ko-kr"}
HOST_PATTERN = re.compile(r"^[A-Za-z0-9.-]+$")
TAG_PATTERN = re.compile(r"<[^>]+>")


def _request_json(url: str, params: dict[str, str | int], timeout: int = 12) -> dict:
    query = urlencode(params)
    request = Request(
        f"{url}?{query}",
        headers={
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            body = response.read(MAX_RESPONSE_BYTES).decode(charset, errors="replace")
    except HTTPError as exc:
        raise RuntimeError(f"External API returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"External API request failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("External API request timed out") from exc

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("External API returned non-JSON content") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("External API returned an unexpected JSON shape")
    return payload


def _html_to_text(value: str) -> str:
    text = re.sub(r"<\s*br\s*/?\s*>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"</\s*p\s*>", "\n", text, flags=re.IGNORECASE)
    text = TAG_PATTERN.sub("", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_university_payload(payload: dict) -> dict:
    data = payload.get("data")
    if isinstance(data, dict):
        normalized = dict(data)
        for key in ("intro", "detail"):
            value = normalized.get(key)
            if isinstance(value, str):
                normalized[key] = _html_to_text(value)
        payload = dict(payload)
        payload["data"] = normalized
    payload["_source"] = UNIVERSITY_API_URL
    return payload


def _normalize_host(value: str) -> str:
    host = (value or "").strip()
    if not host:
        raise ValueError("ip must not be empty")
    host = re.sub(r"^https?://", "", host, flags=re.IGNORECASE).split("/", 1)[0].strip()
    if "@" in host or any(char.isspace() for char in host):
        raise ValueError("ip must be a domain name or IP address, not a URL or command")
    if ":" in host and not (host.startswith("[") and host.endswith("]")):
        host = host.rsplit(":", 1)[0]
    host = host.strip("[]")
    if len(host) > 253:
        raise ValueError("ip is too long")

    try:
        parsed = ipaddress.ip_address(host)
    except ValueError:
        if host.lower() == "localhost" or host.lower().endswith(".local"):
            raise ValueError("local host names are not allowed")
        if not HOST_PATTERN.match(host):
            raise ValueError("ip contains unsupported characters")
        return host

    if (
        parsed.is_loopback
        or parsed.is_private
        or parsed.is_link_local
        or parsed.is_multicast
        or parsed.is_reserved
        or parsed.is_unspecified
    ):
        raise ValueError("private, local, reserved, or multicast IP addresses are not allowed")
    return host


def _bounded_int(value: int, *, minimum: int, maximum: int, name: str) -> int:
    number = int(value)
    if number < minimum or number > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return number


@mcp.tool(
    description="Query public information for a Chinese university by exact university name.",
    annotations=ToolAnnotations(readOnlyHint=True),
)
def query_university_info(daxue: str) -> str:
    name = (daxue or "").strip()
    if not name:
        raise ValueError("daxue must not be empty")
    if len(name) > 80:
        raise ValueError("daxue is too long")

    payload = _request_json(UNIVERSITY_API_URL, {"daxue": name}, timeout=12)
    payload = _normalize_university_payload(payload)
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool(
    description="Run an external PING/port reachability check for a public domain name or public IP address.",
    annotations=ToolAnnotations(readOnlyHint=True),
)
def ping_check(ip: str, port: int = 80, timeout: int = 10, lang: str = "zh-cn") -> str:
    host = _normalize_host(ip)
    safe_port = _bounded_int(port, minimum=1, maximum=65535, name="port")
    safe_timeout = _bounded_int(timeout, minimum=1, maximum=30, name="timeout")
    safe_lang = (lang or "zh-cn").strip().lower()
    if safe_lang not in ALLOWED_LANGS:
        raise ValueError(f"lang must be one of: {', '.join(sorted(ALLOWED_LANGS))}")

    payload = _request_json(
        PING_API_URL,
        {
            "ip": host,
            "port": safe_port,
            "timeout": safe_timeout,
            "lang": safe_lang,
        },
        timeout=safe_timeout + 5,
    )
    payload["_source"] = PING_API_URL
    return json.dumps(payload, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run("stdio")
