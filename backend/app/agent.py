from __future__ import annotations

import json
from typing import Dict, List, Tuple

from .config import settings
from .llm import LLMClient, parse_tool_calls
from .memory import SessionStore
from .models import ChatMessage
from .policy import contains_forbidden_financial_intent, is_forbidden_tool_payload
from .system_prompt import build_system_prompt
from .tools.registry import execute_tool, get_tool_specs, serialize_tool_result


class AgentService:
    def __init__(self, store: SessionStore) -> None:
        self.store = store
        self.llm = LLMClient()

    async def run(self, session_id: str, user_message: str) -> Tuple[str, int, List[str]]:
        messages = self.store.load(session_id)
        if not messages:
            messages.append(ChatMessage(role="system", content=build_system_prompt()))

        if contains_forbidden_financial_intent(user_message):
            refusal = (
                "Finansal islem taleplerini yerine getirmem yasak: kredi karti, odeme, para transferi "
                "ve satin alma islemleri yapmam."
            )
            messages.append(ChatMessage(role="user", content=user_message))
            messages.append(ChatMessage(role="assistant", content=refusal))
            self.store.save(session_id, messages)
            return refusal, 0, []

        messages.append(ChatMessage(role="user", content=user_message))

        used_tools: List[str] = []
        steps = 0

        while steps < settings.ollama_max_steps:
            steps += 1
            payload_messages = [m.model_dump(exclude_none=True) for m in messages]
            raw = await self.llm.chat(payload_messages, get_tool_specs())
            raw_message: Dict = raw.get("message", {})
            assistant_text = raw_message.get("content", "") or ""
            tool_calls = parse_tool_calls(raw_message)
            if not tool_calls:
                parsed_text_tool = self._parse_text_tool_call(assistant_text)
                if parsed_text_tool is not None:
                    tool_calls = [parsed_text_tool]

            messages.append(ChatMessage(role="assistant", content=assistant_text))
            if not tool_calls:
                self.store.save(session_id, messages)
                return assistant_text.strip() or "(no content)", steps, used_tools

            for call in tool_calls:
                args = call.arguments
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                try:
                    if is_forbidden_tool_payload({"name": call.name, "arguments": args}):
                        raise ValueError("Financial operation policy blocked this action.")
                    result = execute_tool(call.name, args)
                    used_tools.append(call.name)
                    tool_text = serialize_tool_result(result)
                except Exception as exc:  # noqa: BLE001
                    tool_text = json.dumps({"error": str(exc)}, ensure_ascii=False)
                messages.append(
                    ChatMessage(
                        role="tool",
                        name=call.name,
                        tool_call_id=call.id,
                        content=tool_text,
                    )
                )

        fallback = "Maksimum adim sinirina ulastim. Gorevi daha kucuk parcalara bolebiliriz."
        messages.append(ChatMessage(role="assistant", content=fallback))
        self.store.save(session_id, messages)
        return fallback, steps, used_tools

    def _parse_text_tool_call(self, content: str):
        text = (content or "").strip()
        if not text:
            return None
        if not (text.startswith("{") and text.endswith("}")):
            return None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        name = data.get("tool")
        arguments = data.get("arguments", {})
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return None
        return type("TextToolCall", (), {"id": "text_tool_call", "name": name, "arguments": arguments})()
