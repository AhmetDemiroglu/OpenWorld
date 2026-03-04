from __future__ import annotations

import asyncio
import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import settings
from .llm import LLMClient, parse_tool_calls
from .memory import SessionStore
from .models import ChatMessage
from .policy import (
    contains_forbidden_financial_intent,
    is_forbidden_tool_payload,
    is_high_impact_tool,
    is_untrusted_content_tool,
    user_explicitly_authorized_tool,
)
from .system_prompt import build_system_prompt
from .tools.registry import execute_tool, get_relevant_tools, get_tool_specs, serialize_tool_result

_MEDIA_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp",
    ".wav", ".mp3", ".ogg", ".m4a", ".flac",
    ".mp4", ".avi", ".mkv", ".mov", ".webm",
}


@dataclass
class ParsedTextToolCall:
    id: str
    name: str
    arguments: Dict[str, Any]


class AgentService:
    # Hermes-style tool call block.
    _TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)
    _COMMAND_LINE_RE = re.compile(
        r"(?im)^\s*(?:command|tool|name)\s*[:=]\s*[\"']?([a-zA-Z0-9_.:-]+)[\"']?\s*$"
    )

    def __init__(self, store: SessionStore) -> None:
        self.store = store
        self.llm = LLMClient()
        self._session_locks: Dict[str, asyncio.Lock] = {}
        self._session_locks_guard = asyncio.Lock()
        self._known_tool_names = self._extract_tool_names()

    async def run(self, session_id: str, user_message: str) -> Tuple[str, int, List[str], List[str]]:
        lock = await self._get_session_lock(session_id)
        async with lock:
            return await self._run_locked(session_id, user_message)

    async def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        async with self._session_locks_guard:
            lock = self._session_locks.get(session_id)
            if lock is None:
                lock = asyncio.Lock()
                self._session_locks[session_id] = lock
            return lock

    async def _run_locked(self, session_id: str, user_message: str) -> Tuple[str, int, List[str], List[str]]:
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

        relevant_tools = get_relevant_tools(user_message)
        allowed_tool_names = self._extract_allowed_tool_names(relevant_tools)
        if not allowed_tool_names:
            allowed_tool_names = set(self._known_tool_names)

        used_tools: List[str] = []
        media_files: List[str] = []
        steps = 0
        untrusted_content_seen = False
        last_step_results: List[Tuple[str, Dict[str, Any]]] = []
        call_counts: Dict[str, int] = {}
        cached_results: Dict[str, Dict[str, Any]] = {}

        while steps < settings.ollama_max_steps:
            steps += 1
            payload_messages = [m.model_dump(exclude_none=True) for m in messages]
            raw = await self.llm.chat(payload_messages, relevant_tools)
            raw_message: Dict[str, Any] = raw.get("message", {})
            assistant_text = raw_message.get("content", "") or ""

            tool_calls: List[Any] = parse_tool_calls(raw_message)
            tool_calls_from_text = False
            fallback_from_user_intent = False

            if not tool_calls:
                parsed_text_tools = self._parse_text_tool_calls(assistant_text)
                if parsed_text_tools:
                    tool_calls = parsed_text_tools
                    tool_calls_from_text = True

            if not tool_calls and not used_tools and self._looks_like_unavailable_claim(assistant_text):
                fallback_call = self._fallback_tool_call_from_user_message(user_message)
                if fallback_call is not None and fallback_call.name in allowed_tool_names:
                    tool_calls = [fallback_call]
                    tool_calls_from_text = True
                    fallback_from_user_intent = True

            if not tool_calls and not used_tools and self._should_force_tool_execution(user_message):
                fallback_call = self._fallback_tool_call_from_user_message(user_message)
                if fallback_call is not None and fallback_call.name in allowed_tool_names:
                    tool_calls = [fallback_call]
                    tool_calls_from_text = True
                    fallback_from_user_intent = True

            preferred_call = self._fallback_tool_call_from_user_message(user_message)
            if (
                steps == 1
                and preferred_call is not None
                and preferred_call.name == "research_and_report"
                and preferred_call.name in allowed_tool_names
                and (not tool_calls or all(getattr(c, "name", "") != "research_and_report" for c in tool_calls))
            ):
                tool_calls = [preferred_call]
                tool_calls_from_text = True
                fallback_from_user_intent = True

            clean_text = assistant_text
            if tool_calls and assistant_text:
                clean_text = "" if fallback_from_user_intent else self._strip_tool_call_noise(clean_text, tool_calls)

            messages.append(ChatMessage(role="assistant", content=clean_text or ""))

            if not tool_calls:
                if used_tools and self._looks_like_stalled_reply(assistant_text):
                    synthesized = self._build_tool_summary(last_step_results)
                    messages.append(ChatMessage(role="assistant", content=synthesized))
                    self.store.save(session_id, messages)
                    return synthesized, steps, used_tools, media_files

                self.store.save(session_id, messages)
                return assistant_text.strip() or "(no content)", steps, used_tools, media_files

            step_results: List[Tuple[str, Dict[str, Any]]] = []

            for call in tool_calls:
                call_name = getattr(call, "name", "")
                call_id = getattr(call, "id", f"tc_{uuid.uuid4().hex[:8]}")
                raw_arguments = getattr(call, "arguments", {})

                if not call_name:
                    result = {"error": "Tool call name is missing."}
                    step_results.append(("", result))
                    messages.append(
                        ChatMessage(
                            role="tool",
                            name="",
                            tool_call_id=call_id,
                            content=serialize_tool_result(result),
                        )
                    )
                    continue

                if allowed_tool_names and call_name not in allowed_tool_names:
                    result = {
                        "error": (
                            f"Tool '{call_name}' bu istek icin uygun degil. "
                            "Sadece ilgili tool listesindeki araclar kullanilabilir."
                        )
                    }
                    step_results.append((call_name, result))
                    messages.append(
                        ChatMessage(
                            role="tool",
                            name=call_name,
                            tool_call_id=call_id,
                            content=serialize_tool_result(result),
                        )
                    )
                    continue

                args = self._normalize_tool_call_arguments(raw_arguments)
                signature = self._call_signature(call_name, args)
                call_counts[signature] = call_counts.get(signature, 0) + 1
                used_tools.append(call_name)

                try:
                    if is_forbidden_tool_payload({"name": call_name, "arguments": args}):
                        raise ValueError("Financial operation policy blocked this action.")

                    if (
                        untrusted_content_seen
                        and is_high_impact_tool(call_name)
                        and not user_explicitly_authorized_tool(user_message, call_name)
                    ):
                        raise ValueError(
                            f"Prompt-injection guard blocked tool '{call_name}'. "
                            "Bu arac icin kullanici mesajinda acik niyet bulunmuyor."
                        )

                    if call_counts[signature] > 2 and signature in cached_results:
                        result = {
                            "warning": "Ayni arac ayni argumanlarla tekrarlandigi icin onceki sonuc kullanildi.",
                            "cached": True,
                            "result": cached_results[signature],
                        }
                    else:
                        result = execute_tool(call_name, args)
                        cached_results[signature] = result

                    if is_untrusted_content_tool(call_name):
                        untrusted_content_seen = True

                    self._collect_media(result, media_files)
                except Exception as exc:  # noqa: BLE001
                    result = {"error": str(exc)}

                step_results.append((call_name, result))
                messages.append(
                    ChatMessage(
                        role="tool",
                        name=call_name,
                        tool_call_id=call_id,
                        content=serialize_tool_result(result),
                    )
                )

            last_step_results = step_results

            # If calls were parsed from text, synthesize deterministic completion.
            if tool_calls_from_text and (not clean_text or self._looks_like_stalled_reply(assistant_text)):
                synthesized = self._build_tool_summary(step_results)
                messages.append(ChatMessage(role="assistant", content=synthesized))
                self.store.save(session_id, messages)
                return synthesized, steps, used_tools, media_files

        fallback = "Maksimum adim sinirina ulastim. Gorevi daha kucuk parcalara bolebiliriz."
        messages.append(ChatMessage(role="assistant", content=fallback))
        self.store.save(session_id, messages)
        return fallback, steps, used_tools, media_files

    @staticmethod
    def _collect_media(result: Dict[str, Any], media_files: List[str]) -> None:
        if not isinstance(result, dict) or "error" in result:
            return

        candidate_paths: List[str] = []
        for key in ("path", "output_path", "file_path", "saved_path", "saved_to", "output"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                candidate_paths.append(value.strip())

        files = result.get("files")
        if isinstance(files, list):
            for item in files:
                if isinstance(item, str):
                    candidate_paths.append(item)

        for file_path in candidate_paths:
            p = Path(file_path)
            if p.exists() and p.is_file() and p.suffix.lower() in _MEDIA_EXTENSIONS:
                abs_path = str(p.resolve())
                if abs_path not in media_files:
                    media_files.append(abs_path)

    def _parse_text_tool_calls(self, content: str) -> List[ParsedTextToolCall]:
        text = (content or "").strip()
        if not text:
            return []

        results: List[ParsedTextToolCall] = []
        seen_signatures: set[str] = set()

        def add_result(call: Optional[ParsedTextToolCall]) -> None:
            if call is None:
                return
            signature = self._call_signature(call.name, call.arguments)
            if signature in seen_signatures:
                return
            seen_signatures.add(signature)
            results.append(call)

        for raw_json in self._TOOL_CALL_RE.findall(text):
            add_result(self._try_parse_single_call(raw_json))

        for obj in self._extract_json_objects(text):
            add_result(self._try_parse_single_call(obj))

        # Non-strict JSON-like blocks (unescaped windows paths etc.).
        for match in re.finditer(r"\{[\s\S]*?(?:\"name\"|\"tool\"|\"command\")[\s\S]*?\}", text):
            add_result(self._try_parse_single_call(match.group(0)))

        for match in self._COMMAND_LINE_RE.finditer(text):
            add_result(
                ParsedTextToolCall(
                    id=f"text_tc_{uuid.uuid4().hex[:10]}",
                    name=match.group(1).strip(),
                    arguments={},
                )
            )

        return results

    def _try_parse_single_call(self, raw_data: Any) -> Optional[ParsedTextToolCall]:
        data: Any = raw_data
        if isinstance(raw_data, str):
            raw_text = raw_data.strip()
            if not raw_text:
                return None
            try:
                data = json.loads(raw_text)
            except json.JSONDecodeError:
                data = self._parse_loose_json_like_call(raw_text)
                if data is None:
                    return None

        if not isinstance(data, dict):
            return None

        name = (
            data.get("name")
            or data.get("tool")
            or data.get("command")
            or data.get("tool_name")
            or data.get("function")
        )
        if not isinstance(name, str) or not name.strip():
            return None

        name = name.strip().strip("`").strip('"').strip("'")
        if "." in name and name not in self._known_tool_names:
            name = name.split(".")[-1]
        if not name:
            return None

        arguments = (
            data.get("arguments")
            or data.get("parameters")
            or data.get("params")
            or data.get("args")
            or {}
        )

        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}

        if not isinstance(arguments, dict):
            arguments = {}

        if not arguments:
            reserved_keys = {
                "name",
                "tool",
                "command",
                "tool_name",
                "function",
                "arguments",
                "parameters",
                "params",
                "args",
                "status",
                "message",
                "note",
                "thinking",
                "plan",
                "step",
            }
            arguments = {
                key: value
                for key, value in data.items()
                if key not in reserved_keys and not key.startswith("_")
            }

        return ParsedTextToolCall(
            id=f"text_tc_{uuid.uuid4().hex[:10]}",
            name=name,
            arguments=arguments,
        )

    @staticmethod
    def _parse_loose_json_like_call(raw_text: str) -> Optional[Dict[str, Any]]:
        name_match = re.search(
            r'"(?:name|tool|command|tool_name|function)"\s*:\s*"([^"]+)"',
            raw_text,
            flags=re.IGNORECASE,
        )
        if not name_match:
            return None

        data: Dict[str, Any] = {"command": name_match.group(1).strip()}
        reserved = {"name", "tool", "command", "tool_name", "function", "arguments", "parameters", "params", "args"}

        for pair in re.finditer(
            r'"([A-Za-z0-9_]+)"\s*:\s*("(?:[^"]*)?"|-?\d+(?:\.\d+)?|true|false|null)',
            raw_text,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            key = pair.group(1)
            if key in reserved:
                continue
            raw_value = pair.group(2).strip()
            if raw_value.startswith('"') and raw_value.endswith('"'):
                value: Any = raw_value[1:-1]
                value = value.replace('\\"', '"').replace('\\\\', '\\')
            elif raw_value.lower() in {"true", "false"}:
                value = raw_value.lower() == "true"
            elif raw_value.lower() == "null":
                value = None
            elif "." in raw_value:
                try:
                    value = float(raw_value)
                except ValueError:
                    value = raw_value
            else:
                try:
                    value = int(raw_value)
                except ValueError:
                    value = raw_value
            data[key] = value
        return data

    @staticmethod
    def _extract_json_objects(text: str) -> List[Dict[str, Any]]:
        decoder = json.JSONDecoder()
        idx = 0
        found: List[Dict[str, Any]] = []

        while idx < len(text):
            brace = text.find("{", idx)
            if brace == -1:
                break
            try:
                obj, consumed = decoder.raw_decode(text[brace:])
            except json.JSONDecodeError:
                idx = brace + 1
                continue
            if isinstance(obj, dict):
                found.append(obj)
            idx = brace + consumed

        return found

    @staticmethod
    def _normalize_tool_call_arguments(raw_arguments: Any) -> Dict[str, Any]:
        if isinstance(raw_arguments, str):
            try:
                raw_arguments = json.loads(raw_arguments)
            except json.JSONDecodeError:
                raw_arguments = {}

        if not isinstance(raw_arguments, dict):
            return {}

        args = dict(raw_arguments)
        nested = args.get("arguments")
        if isinstance(nested, dict):
            args.pop("arguments", None)
            for key, value in nested.items():
                args.setdefault(key, value)

        for transient_key in ("status", "process", "state", "step", "progress"):
            args.pop(transient_key, None)

        return args

    @staticmethod
    def _strip_tool_call_noise(content: str, tool_calls: List[Any]) -> str:
        clean = content or ""
        clean = AgentService._TOOL_CALL_RE.sub("", clean)
        clean = re.sub(r"</tool_call>", "", clean, flags=re.IGNORECASE)
        clean = re.sub(
            r"```json\s*\{[\s\S]*?(?:\"name\"|\"tool\"|\"command\")[\s\S]*?\}\s*```",
            "",
            clean,
            flags=re.IGNORECASE,
        )

        for call in tool_calls:
            name = getattr(call, "name", "")
            if not name:
                continue
            name_re = re.escape(name)
            clean = re.sub(
                rf'\{{[^{{}}]*(?:\"name\"|\"tool\"|\"command\")\s*:\s*\"{name_re}\"[^{{}}]*\}}',
                "",
                clean,
                flags=re.DOTALL,
            )

        return clean.strip()

    def _fallback_tool_call_from_user_message(self, user_message: str) -> Optional[ParsedTextToolCall]:
        text = (user_message or "").strip()
        if not text:
            return None

        lower = text.lower()
        normalized = self._normalize_text_for_match(text)

        for tool_name in sorted(self._known_tool_names, key=len, reverse=True):
            if re.search(rf"\b{re.escape(tool_name.lower())}\b", lower):
                return ParsedTextToolCall(
                    id=f"text_tc_{uuid.uuid4().hex[:10]}",
                    name=tool_name,
                    arguments={},
                )

        url_match = re.search(r"https?://\S+", text)
        if (
            url_match
            and "screenshot_webpage" in self._known_tool_names
            and any(k in normalized for k in ("web", "sayfa", "screenshot", "goruntu"))
        ):
            return ParsedTextToolCall(
                id=f"text_tc_{uuid.uuid4().hex[:10]}",
                name="screenshot_webpage",
                arguments={"url": url_match.group(0).rstrip(".,)")},
            )

        if "webcam_capture" in self._known_tool_names and any(
            k in normalized for k in ("webcam", "kamera", "foto", "selfie", "camera")
        ):
            return ParsedTextToolCall(
                id=f"text_tc_{uuid.uuid4().hex[:10]}",
                name="webcam_capture",
                arguments={"camera_index": 0},
            )

        if "check_gmail_messages" in self._known_tool_names and (
            "gmail" in normalized or ("mail" in normalized and "outlook" not in normalized)
        ):
            return ParsedTextToolCall(
                id=f"text_tc_{uuid.uuid4().hex[:10]}",
                name="check_gmail_messages",
                arguments={"max_results": 10},
            )

        if "check_outlook_messages" in self._known_tool_names and "outlook" in normalized:
            return ParsedTextToolCall(
                id=f"text_tc_{uuid.uuid4().hex[:10]}",
                name="check_outlook_messages",
                arguments={"max_results": 10},
            )

        if "research_and_report" in self._known_tool_names and any(
            k in normalized for k in ("detay", "analiz", "tum kaynak", "tum haber", "rapor")
        ) and any(k in normalized for k in ("haber", "news", "gundem", "savas", "iran", "dunya", "world")):
            args: Dict[str, Any] = {"topic": text, "max_sources": 8}
            if any(k in normalized for k in ("desktop", "masaustu")):
                args["out_path"] = "Desktop\\arastirma_raporu.txt"
            return ParsedTextToolCall(
                id=f"text_tc_{uuid.uuid4().hex[:10]}",
                name="research_and_report",
                arguments=args,
            )

        if "search_news" in self._known_tool_names and any(k in normalized for k in ("haber", "news", "gundem")):
            return ParsedTextToolCall(
                id=f"text_tc_{uuid.uuid4().hex[:10]}",
                name="search_news",
                arguments={"query": text},
            )

        if "create_markdown_report" in self._known_tool_names and any(
            k in normalized for k in ("rapor", "report", "hata", "error")
        ):
            title = "Hata Raporu" if any(k in normalized for k in ("hata", "error", "sorun")) else "Rapor"
            return ParsedTextToolCall(
                id=f"text_tc_{uuid.uuid4().hex[:10]}",
                name="create_markdown_report",
                arguments={"title": title, "content": text},
            )

        return None

    @staticmethod
    def _normalize_text_for_match(text: str) -> str:
        turkish_map = {
            0x00E7: "c",  # c-cedilla
            0x011F: "g",  # g-breve
            0x0131: "i",  # dotless i
            0x00F6: "o",  # o-umlaut
            0x015F: "s",  # s-cedilla
            0x00FC: "u",  # u-umlaut
        }
        return (text or "").lower().translate(turkish_map)

    @staticmethod
    def _looks_like_stalled_reply(text: str) -> bool:
        lower = AgentService._normalize_text_for_match(text)
        stalled_markers = (
            "process_start",
            "sonucu bekliyorum",
            "kontrol ediyorum",
            "devam ediyor",
            "hazirlaniyor",
            "baslatildi",
            "islem sureci",
            "tekrar deneniyor",
            "retrying",
        )
        return any(marker in lower for marker in stalled_markers)

    @staticmethod
    def _looks_like_unavailable_claim(text: str) -> bool:
        lower = AgentService._normalize_text_for_match(text)
        blocked_markers = (
            "mevcut arac yok",
            "arac bulunmamaktadir",
            "boyle bir aracim yok",
            "yetkim yok",
            "kullanilabilir arac",
        )
        return any(marker in lower for marker in blocked_markers)

    @staticmethod
    def _build_tool_summary(step_results: List[Tuple[str, Dict[str, Any]]]) -> str:
        if not step_results:
            return "Islem tamamlandi."

        lines = ["Islem tamamlandi. Sonuclar:"]
        for name, result in step_results:
            lines.append(f"- `{name}`: {AgentService._summarize_tool_result(result)}")
        return "\n".join(lines)

    @staticmethod
    def _summarize_tool_result(result: Dict[str, Any]) -> str:
        if not isinstance(result, dict):
            return str(result)[:240]

        err = result.get("error")
        if err:
            return f"hata -> {err}"

        for key in ("path", "output_path", "file_path", "opened", "url"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return f"tamamlandi ({key}: {value})"

        if isinstance(result.get("messages"), list):
            messages = result["messages"]
            if messages and isinstance(messages[0], dict):
                sample = []
                for item in messages[:3]:
                    subj = str(item.get("subject") or item.get("title") or "").strip()
                    if subj:
                        sample.append(subj)
                if sample:
                    return f"{len(messages)} kayit bulundu. ilk basliklar: " + " | ".join(sample)
            return f"{len(messages)} kayit bulundu"

        if isinstance(result.get("results"), list):
            rows = result["results"]
            if rows and isinstance(rows[0], dict):
                sample = []
                for item in rows[:3]:
                    title = str(item.get("title") or "").strip()
                    if title:
                        sample.append(title)
                if sample:
                    return f"{len(rows)} sonuc bulundu. ilk basliklar: " + " | ".join(sample)
            return f"{len(rows)} sonuc bulundu"

        if isinstance(result.get("count"), int):
            return f"{result['count']} sonuc"

        if result.get("success") is True:
            return "basarili"

        summary = json.dumps(result, ensure_ascii=False)
        return summary[:280] + ("..." if len(summary) > 280 else "")

    @staticmethod
    def _call_signature(name: str, arguments: Dict[str, Any]) -> str:
        try:
            arg_text = json.dumps(arguments or {}, sort_keys=True, ensure_ascii=False)
        except Exception:  # noqa: BLE001
            arg_text = str(arguments)
        return f"{name}:{arg_text}"

    def _extract_tool_names(self) -> set[str]:
        names: set[str] = set()
        for spec in get_tool_specs():
            fn = (spec or {}).get("function", {})
            name = fn.get("name")
            if isinstance(name, str) and name.strip():
                names.add(name.strip())
        return names

    @staticmethod
    def _extract_allowed_tool_names(tool_specs: List[Dict[str, Any]]) -> set[str]:
        names: set[str] = set()
        for spec in tool_specs:
            if not isinstance(spec, dict):
                continue
            fn = spec.get("function", {})
            if not isinstance(fn, dict):
                continue
            name = fn.get("name")
            if isinstance(name, str) and name.strip():
                names.add(name.strip())
        return names

    @staticmethod
    def _should_force_tool_execution(user_message: str) -> bool:
        normalized = AgentService._normalize_text_for_match(user_message)
        intent_markers = (
            "kontrol et",
            "tara",
            "ara",
            "bul",
            "cek",
            "gonder",
            "kaydet",
            "olustur",
            "rapor",
            "arastir",
            "haber",
            "mail",
            "gmail",
            "outlook",
            "webcam",
            "kamera",
        )
        return any(marker in normalized for marker in intent_markers)
