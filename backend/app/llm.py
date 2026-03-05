from __future__ import annotations

from typing import Any, Dict, List

import httpx

from .config import settings
from .models import ToolCall


class OllamaClient:
    def __init__(self) -> None:
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.tools_supported = True

    async def chat(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": settings.ollama_model,
            "messages": messages,
            "stream": False,
        }
        if self.tools_supported and tools:
            payload["tools"] = tools
        request_timeout = max(30.0, float(getattr(settings, "ollama_request_timeout_sec", 600.0)))
        connect_timeout = max(5.0, min(float(getattr(settings, "ollama_connect_timeout_sec", 20.0)), request_timeout))
        timeout = httpx.Timeout(request_timeout, connect=connect_timeout)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{self.base_url}/api/chat", json=payload)
            if resp.status_code == 400 and self.tools_supported:
                self.tools_supported = False
                payload.pop("tools", None)
                resp = await client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json()


class LLMClient:
    def __init__(self) -> None:
        self.impl = OllamaClient()

    async def chat(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        return await self.impl.chat(messages, tools)


def parse_tool_calls(raw_message: Dict[str, Any]) -> List[ToolCall]:
    tool_calls = raw_message.get("tool_calls") or []
    parsed: List[ToolCall] = []
    for idx, call in enumerate(tool_calls):
        fn = call.get("function", {})
        raw_arguments = fn.get("arguments", {}) or {}
        if isinstance(raw_arguments, str):
            try:
                raw_arguments = __import__("json").loads(raw_arguments)
            except Exception:
                raw_arguments = {}
        if not isinstance(raw_arguments, dict):
            raw_arguments = {}
        parsed.append(
            ToolCall(
                id=str(call.get("id", f"tc_{idx}")),
                name=fn.get("name", ""),
                arguments=raw_arguments,
            )
        )
    return parsed
