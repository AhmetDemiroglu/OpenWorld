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
        if self.tools_supported:
            payload["tools"] = tools
        async with httpx.AsyncClient(timeout=90) as client:
            resp = await client.post(f"{self.base_url}/api/chat", json=payload)
            if resp.status_code == 400 and self.tools_supported:
                self.tools_supported = False
                payload.pop("tools", None)
                resp = await client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json()


class LlamaCppClient:
    def __init__(self) -> None:
        self._llm = None

    def _get_llm(self):
        if self._llm is None:
            from llama_cpp import Llama

            model_path = str(settings.llama_model_path_abs)
            self._llm = Llama(
                model_path=model_path,
                n_ctx=settings.llama_n_ctx,
                n_gpu_layers=settings.llama_n_gpu_layers,
                n_threads=settings.llama_n_threads,
                chat_format="chatml",
                verbose=False,
            )
        return self._llm

    async def chat(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        llm = self._get_llm()
        resp = llm.create_chat_completion(
            messages=messages,
            max_tokens=1024,
            temperature=0.2,
            stop=["<|im_end|>"],
        )
        content = (
            resp.get("choices", [{}])[0].get("message", {}).get("content", "")
            if isinstance(resp, dict)
            else ""
        )
        return {"message": {"role": "assistant", "content": content}}


class LLMClient:
    def __init__(self) -> None:
        backend = settings.llm_backend.strip().lower()
        if backend == "llama_cpp":
            self.impl = LlamaCppClient()
        else:
            self.impl = OllamaClient()

    async def chat(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        return await self.impl.chat(messages, tools)


def parse_tool_calls(raw_message: Dict[str, Any]) -> List[ToolCall]:
    tool_calls = raw_message.get("tool_calls") or []
    parsed: List[ToolCall] = []
    for idx, call in enumerate(tool_calls):
        fn = call.get("function", {})
        parsed.append(
            ToolCall(
                id=str(call.get("id", f"tc_{idx}")),
                name=fn.get("name", ""),
                arguments=fn.get("arguments", {}) or {},
            )
        )
    return parsed
