"""LLM client layer.

Supports Ollama (local) and OpenAI-compatible cloud APIs.
Active provider is read from providers.json on each request.
Response is normalized to Ollama format so agent.py needs no changes.
"""
from __future__ import annotations

import json as _json
import logging
from typing import Any, Dict, List, Optional

import httpx

from .config import settings
from .models import ToolCall

logger = logging.getLogger(__name__)


class OllamaClient:
    """Local Ollama API client."""

    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.tools_supported = True

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        *,
        think: bool | None = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        payload["think"] = bool(settings.ollama_think if think is None else think)
        payload["options"] = {
            "temperature": float(getattr(settings, "ollama_temperature", 0.2)),
            "num_predict": int(getattr(settings, "ollama_num_predict", 2048)),
            "num_ctx": int(getattr(settings, "ollama_num_ctx", 16384)),
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


class OpenAICompatibleClient:
    """OpenAI-compatible API client (Groq, OpenRouter, Qwen, Z.AI, Gemini, etc.)

    Normalizes response to Ollama format: {"message": {"role": ..., "content": ..., "tool_calls": [...]}}
    """

    def __init__(self, base_url: str, model: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key

    def _prepare_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Transform messages for OpenAI format.

        OpenAI requires assistant messages to include tool_calls when
        followed by tool-role messages. Ollama-style storage omits this,
        so we reconstruct it from the subsequent tool messages.
        """
        result: List[Dict[str, Any]] = []
        n = len(messages)

        for i, msg in enumerate(messages):
            new_msg = dict(msg)
            role = msg.get("role")

            if role == "assistant":
                # Look ahead: gather tool messages that follow
                tool_calls = []
                for j in range(i + 1, n):
                    if messages[j].get("role") == "tool":
                        tc_id = messages[j].get("tool_call_id", f"tc_{j}")
                        tc_name = messages[j].get("name", "unknown")
                        tool_calls.append({
                            "id": tc_id,
                            "type": "function",
                            "function": {
                                "name": tc_name,
                                "arguments": "{}",
                            },
                        })
                    else:
                        break
                if tool_calls:
                    new_msg["tool_calls"] = tool_calls
                    # OpenAI: content can be null when tool_calls present
                    if not new_msg.get("content"):
                        new_msg["content"] = None

            result.append(new_msg)

        return result

    def _normalize_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize OpenAI response to Ollama format for agent.py compatibility."""
        choices = data.get("choices", [])
        if not choices:
            return {"message": {"role": "assistant", "content": ""}}

        oai_message = choices[0].get("message", {})
        normalized: Dict[str, Any] = {
            "role": oai_message.get("role", "assistant"),
            "content": oai_message.get("content") or "",
        }

        # Convert OpenAI tool_calls to Ollama format
        oai_tool_calls = oai_message.get("tool_calls")
        if oai_tool_calls:
            ollama_calls = []
            for tc in oai_tool_calls:
                fn = tc.get("function", {})
                args = fn.get("arguments", "{}")
                if isinstance(args, str):
                    try:
                        args = _json.loads(args)
                    except Exception:
                        args = {}
                ollama_calls.append({
                    "id": tc.get("id", ""),
                    "function": {
                        "name": fn.get("name", ""),
                        "arguments": args,
                    },
                })
            normalized["tool_calls"] = ollama_calls

        return {"message": normalized}

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        *,
        think: bool | None = None,
    ) -> Dict[str, Any]:
        prepared = self._prepare_messages(messages)

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": prepared,
            "temperature": float(getattr(settings, "ollama_temperature", 0.2)),
            "max_tokens": int(getattr(settings, "ollama_num_predict", 2048)),
        }
        if tools:
            payload["tools"] = tools

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        request_timeout = max(30.0, float(getattr(settings, "ollama_request_timeout_sec", 600.0)))
        timeout = httpx.Timeout(request_timeout, connect=20.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            return self._normalize_response(resp.json())


class CodexCLIClient:
    """Codex CLI subprocess wrapper.

    Runs `codex exec` with the prompt on stdin.
    Tool calling is NOT supported — returns text-only responses.
    """

    def __init__(self, model: str) -> None:
        self.model = model

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        *,
        think: bool | None = None,
    ) -> Dict[str, Any]:
        import asyncio
        import subprocess
        import sys

        # Codex CLI is a code-focused tool — send only a brief context + last user message.
        # Including the full system prompt causes failures.
        system_brief = ""
        last_user = ""
        last_assistant = ""
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content") or ""
            if role == "system":
                # Take only first 300 chars of system prompt
                system_brief = content[:300]
            elif role == "user":
                last_user = content
            elif role == "assistant" and content:
                last_assistant = content

        prompt_parts = []
        if system_brief:
            prompt_parts.append(f"[Context] {system_brief}")
        if last_assistant:
            prompt_parts.append(f"[Previous reply] {last_assistant[:200]}")
        prompt_parts.append(last_user)
        prompt = "\n\n".join(prompt_parts)

        command = ["codex", "exec"]
        if self.model:
            command.extend(["-m", self.model])
        command.extend(["--skip-git-repo-check", "-"])

        timeout = int(getattr(settings, "ollama_request_timeout_sec", 600))
        is_win = sys.platform == "win32"

        def _run():
            result = subprocess.run(
                command,
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                shell=is_win,
            )
            if result.returncode != 0:
                err = result.stderr.strip() or "Codex CLI hatasi"
                # Truncate error — don't dump entire prompt back
                return f"Codex hatasi: {err[:300]}"
            return result.stdout.strip() or "Codex yanit vermedi."

        loop = asyncio.get_running_loop()
        output = await loop.run_in_executor(None, _run)

        return {"message": {"role": "assistant", "content": output}}


class LLMClient:
    """Main LLM client that routes to active provider."""

    def __init__(self) -> None:
        self._cached_provider_id: Optional[str] = None
        self._impl: Optional[Any] = None

    def _get_impl(self) -> Any:
        """Get or create the appropriate client for the active provider."""
        from .providers import get_active_provider

        provider = get_active_provider()
        provider_id = provider["id"]

        # Reuse cached client if provider hasn't changed
        if self._impl is not None and self._cached_provider_id == provider_id:
            return self._impl

        ptype = provider.get("type", "ollama")

        if ptype == "ollama":
            self._impl = OllamaClient(
                base_url=provider.get("base_url", settings.ollama_base_url),
                model=provider.get("model", settings.ollama_model),
            )
        elif ptype == "codex_cli":
            self._impl = CodexCLIClient(
                model=provider.get("model", "codex-mini-latest"),
            )
        else:
            self._impl = OpenAICompatibleClient(
                base_url=provider["base_url"],
                model=provider["model"],
                api_key=provider.get("api_key", ""),
            )

        self._cached_provider_id = provider_id
        logger.info(f"LLM client switched to provider: {provider['name']} ({provider['model']})")
        return self._impl

    def invalidate_cache(self) -> None:
        """Force re-creation of client on next request."""
        self._cached_provider_id = None
        self._impl = None

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        *,
        think: bool | None = None,
    ) -> Dict[str, Any]:
        impl = self._get_impl()
        return await impl.chat(messages, tools, think=think)


def parse_tool_calls(raw_message: Dict[str, Any]) -> List[ToolCall]:
    tool_calls = raw_message.get("tool_calls") or []
    parsed: List[ToolCall] = []
    for idx, call in enumerate(tool_calls):
        fn = call.get("function", {})
        raw_arguments = fn.get("arguments", {}) or {}
        if isinstance(raw_arguments, str):
            try:
                raw_arguments = _json.loads(raw_arguments)
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
