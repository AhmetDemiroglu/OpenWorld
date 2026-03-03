from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

from .config import settings
from .llm import LLMClient, parse_tool_calls
from .memory import SessionStore
from .models import ChatMessage

# Media dosya uzantıları
_MEDIA_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp",  # image
    ".wav", ".mp3", ".ogg", ".m4a", ".flac",           # audio
    ".mp4", ".avi", ".mkv", ".mov", ".webm",           # video
}
from .policy import (
    contains_forbidden_financial_intent,
    is_forbidden_tool_payload,
    is_high_impact_tool,
    is_untrusted_content_tool,
    user_explicitly_authorized_tool,
)
from .system_prompt import build_system_prompt
from .tools.registry import execute_tool, get_tool_specs, get_relevant_tools, serialize_tool_result


class AgentService:
    def __init__(self, store: SessionStore) -> None:
        self.store = store
        self.llm = LLMClient()

    async def run(self, session_id: str, user_message: str) -> Tuple[str, int, List[str], List[str]]:
        """Agent döngüsünü çalıştır.

        Returns:
            (reply, steps, used_tools, media_files)
            media_files: Tool'lar tarafından üretilen medya dosyalarının tam yolları.
        """
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
            return refusal, 0, [], []

        messages.append(ChatMessage(role="user", content=user_message))

        # Kullanıcı mesajına göre sadece ilgili tool'ları seç
        relevant_tools = get_relevant_tools(user_message)

        used_tools: List[str] = []
        media_files: List[str] = []
        steps = 0
        untrusted_content_seen = False

        while steps < settings.ollama_max_steps:
            steps += 1
            payload_messages = [m.model_dump(exclude_none=True) for m in messages]
            raw = await self.llm.chat(payload_messages, relevant_tools)
            raw_message: Dict = raw.get("message", {})
            assistant_text = raw_message.get("content", "") or ""
            tool_calls = parse_tool_calls(raw_message)
            if not tool_calls:
                parsed_text_tools = self._parse_text_tool_calls(assistant_text)
                if parsed_text_tools:
                    tool_calls = parsed_text_tools

            # Tool call JSON'larını assistant metninden temizle
            clean_text = assistant_text
            if tool_calls and assistant_text:
                clean_text = self._TOOL_CALL_RE.sub("", clean_text)
                clean_text = re.sub(r'</tool_call>', '', clean_text)
                # Serbest JSON bloklarını da temizle (sadece tool call parse edildiyse)
                for call in tool_calls:
                    clean_text = clean_text.replace(
                        f'"name": "{call.name}"', ''
                    )
                clean_text = re.sub(r'\{[^{}]*"arguments"[^{}]*\{[^{}]*\}[^{}]*\}', '', clean_text)
                clean_text = clean_text.strip()

            messages.append(ChatMessage(role="assistant", content=clean_text or ""))
            if not tool_calls:
                self.store.save(session_id, messages)
                return assistant_text.strip() or "(no content)", steps, used_tools, media_files

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
                    # Prompt-injection enforcement:
                    # If untrusted web content has been consumed in this run,
                    # block high-impact tools unless user explicitly requested them.
                    if (
                        untrusted_content_seen
                        and is_high_impact_tool(call.name)
                        and not user_explicitly_authorized_tool(user_message, call.name)
                    ):
                        raise ValueError(
                            f"Prompt-injection guard blocked tool '{call.name}'. "
                            "Bu arac icin kullanici mesajinda acik niyet bulunmuyor."
                        )
                    result = execute_tool(call.name, args)
                    used_tools.append(call.name)
                    if is_untrusted_content_tool(call.name):
                        untrusted_content_seen = True
                    # Tool result'ından media dosyalarını topla
                    self._collect_media(result, media_files)
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
        return fallback, steps, used_tools, media_files

    @staticmethod
    def _collect_media(result: Dict, media_files: List[str]) -> None:
        """Tool result'ından media dosya yollarını topla."""
        if not isinstance(result, dict) or "error" in result:
            return
        # "path" key'inde dosya yolu varsa kontrol et
        file_path = result.get("path", "")
        if not file_path:
            return
        p = Path(file_path)
        if p.exists() and p.is_file() and p.suffix.lower() in _MEDIA_EXTENSIONS:
            abs_path = str(p.resolve())
            if abs_path not in media_files:
                media_files.append(abs_path)

    # Hermes <tool_call> tag'lerini yakala
    _TOOL_CALL_RE = re.compile(
        r"<tool_call>\s*(\{.*?\})\s*</tool_call>",
        re.DOTALL,
    )

    def _parse_text_tool_calls(self, content: str) -> list:
        """Model'in text içinde döndürdüğü tool call'ları parse et.

        Desteklenen formatlar:
        1. Hermes: <tool_call>{"name": ..., "arguments": ...}</tool_call>
        2. Serbest JSON: {"name": ..., "arguments": ...}
        3. Eski format: {"tool": ..., "arguments": ...}
        """
        text = (content or "").strip()
        if not text:
            return []

        results = []

        # 1) Hermes <tool_call> tag'lerini ara
        matches = self._TOOL_CALL_RE.findall(text)
        if matches:
            for raw_json in matches:
                parsed = self._try_parse_single_call(raw_json)
                if parsed is not None:
                    results.append(parsed)
            return results

        # 2) </tool_call> tag'i var ama <tool_call> yok (model bazen atlar)
        if "</tool_call>" in text:
            chunks = text.split("</tool_call>")
            for chunk in chunks:
                chunk = chunk.strip()
                # JSON bloğunu bul
                brace_start = chunk.find("{")
                if brace_start == -1:
                    continue
                raw_json = chunk[brace_start:]
                parsed = self._try_parse_single_call(raw_json)
                if parsed is not None:
                    results.append(parsed)
            return results

        # 3) Düz JSON (tek tool call)
        if text.startswith("{") and text.endswith("}"):
            parsed = self._try_parse_single_call(text)
            if parsed is not None:
                return [parsed]

        # 4) Metin içinde gömülü JSON blokları
        for m in re.finditer(r'\{[^{}]*"(?:name|tool)"[^{}]*"arguments"[^{}]*\{[^{}]*\}[^{}]*\}', text):
            parsed = self._try_parse_single_call(m.group())
            if parsed is not None:
                results.append(parsed)

        return results

    @staticmethod
    def _try_parse_single_call(raw_json: str):
        """Tek bir JSON tool call'ı parse et."""
        raw_json = raw_json.strip()
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None

        # "name" veya "tool" key'ini kabul et
        name = data.get("name") or data.get("tool")
        arguments = data.get("arguments") or data.get("parameters") or {}

        if not isinstance(name, str) or not name:
            return None
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}
        if not isinstance(arguments, dict):
            return None

        call_id = f"text_tc_{hash(name) & 0xFFFF:04x}"
        return type("TextToolCall", (), {
            "id": call_id, "name": name, "arguments": arguments,
        })()
