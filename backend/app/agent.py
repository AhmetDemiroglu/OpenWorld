from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import settings

# Setup logging
LOGS_DIR = Path(__file__).resolve().parents[2] / "data" / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOGS_DIR / "openworld.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
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
    ".pdf", ".docx", ".xlsx", ".pptx", ".zip", ".tar", ".gz",
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

    def _check_notebook_resume(self, user_message: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Kullanici 'devam et' veya notebook adi soylerse, devam etme bilgisi dondur."""
        from .tools.notebook_tools import tool_notebook_list, tool_notebook_status
        
        normalized = self._normalize_text_for_match(user_message)
        
        # "devam et", "rapora devam", "tamamla" vb.
        resume_keywords = ("devam", "tamamla", "bitir", "ilerle", "sonraki adim")
        is_resume_request = any(k in normalized for k in resume_keywords)
        
        # Not defteri listesi al
        try:
            list_result = tool_notebook_list()
            notebooks = list_result.get("notebooks", [])
            
            if not notebooks:
                return None
            
            # 1. Eger belirli bir notebook adi geciyorsa onu bul
            specific_notebook = None
            for nb in notebooks:
                nb_name_norm = self._normalize_text_for_match(nb["name"])
                if nb_name_norm in normalized or nb["name"].lower() in user_message.lower():
                    specific_notebook = nb
                    break

            # Resume niyeti veya belirli notebook adi yoksa mevcut notebook akisini zorla dayatma.
            if not specific_notebook and not is_resume_request:
                return None
            
            # 2. Yoksa son aktif (Devam Ediyor) notebook'u bul
            if not specific_notebook:
                incomplete = [n for n in notebooks if n.get("status") == "Devam Ediyor"]
                if incomplete:
                    specific_notebook = incomplete[0]  # En sonuncu
            
            # 3. Hala yoksa en sonuncuyu al (tamamlanmis olsa bile)
            if not specific_notebook and notebooks:
                specific_notebook = notebooks[0]
            
            if specific_notebook:
                status = tool_notebook_status(specific_notebook["name"])
                return (specific_notebook["name"], status)
        except Exception:
            pass
        
        return None

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

        # NOTEBOOK DEVAM ETME KONTROLU
        notebook_resume = self._check_notebook_resume(user_message)
        notebook_goal_for_research = ""  # research_and_report icin topic sakla
        
        if notebook_resume:
            nb_name, nb_status = notebook_resume
            pending = nb_status.get("pending_steps", [])
            completed = nb_status.get("completed_steps", 0)
            total = nb_status.get("total_steps", 0)
            goal = nb_status.get("goal", "")
            notebook_goal_for_research = goal  # Sonradan kullanmak icin sakla

            fast_resume_reply, fast_resume_tools = self._try_fast_notebook_resume(
                user_message=user_message,
                notebook_name=nb_name,
                notebook_status=nb_status,
            )
            if fast_resume_reply:
                messages.append(ChatMessage(role="user", content=user_message))
                messages.append(ChatMessage(role="assistant", content=fast_resume_reply))
                self.store.save(session_id, messages)
                return fast_resume_reply, 1, fast_resume_tools, []
            
            if pending:
                next_step = pending[0]
                # Sistem mesaji olarak baglam ekle - COK AYRINTILI
                context_msg = (
                    f"[SISTEM NOTU] '{nb_name}' not defterine devam ediliyor.\n"
                    f"Hedef: {goal}\n"
                    f"İlerleme: {completed}/{total} adim tamamlandi.\n"
                    f"Siradaki adim: {next_step}\n\n"
                    f"KURALLAR:\n"
                    f"1. Kucuk adimlarla ilerle; tek turda tum raporu cikarmaya calisma.\n"
                    f"2. Her adim sonucunu notebook_add_note ile kaydet.\n"
                    f"3. Adim bitince notebook_complete_step ile isaretle.\n"
                    f"4. Bu not defteri hedefi ile tutarli kal."
                )
                messages.append(ChatMessage(role="system", content=context_msg))
                
                # Kullanici mesajini guncelle - hedefi vurgula
                if "devam" in user_message.lower() or len(user_message) < 30:
                    if goal:
                        user_message = f"{nb_name} not defteri icin devam et. Siradaki adim: {next_step}. Sadece bu adimi tamamla, not al ve adimi kapat."
                    else:
                        user_message = f"{nb_name} not defterindeki siradaki adimi yap: {next_step}"

        # Kompleks arastirma isteklerinde ilk adimi deterministic olarak baslat.
        kickoff_reply, kickoff_tools = self._try_auto_notebook_kickoff(user_message, notebook_resume)
        if kickoff_reply:
            messages.append(ChatMessage(role="user", content=user_message))
            messages.append(ChatMessage(role="assistant", content=kickoff_reply))
            self.store.save(session_id, messages)
            return kickoff_reply, 1, kickoff_tools, []

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

        # === HIZLI MOD: Dusunme gerektirmeyen basit araclar ===
        # Screenshot, webcam, ses kaydi vb. icin direkt calistir, LLM'e sorma
        fast_fallback = self._fallback_tool_call_from_user_message(user_message)
        if fast_fallback and self._is_fast_tool(fast_fallback.name):
            if fast_fallback.name in allowed_tool_names:
                import logging
                logger = logging.getLogger(__name__)
                
                try:
                    logger.info(f"[FAST MODE] Executing: {fast_fallback.name} with args: {fast_fallback.arguments}")
                    
                    # SES KAYDI - Ozel mantik: start -> bekle -> stop
                    if fast_fallback.name == "start_audio_recording":
                        return await self._handle_audio_recording_fast(session_id, messages, user_message)
                    
                    # NORMAL FAST TOOL
                    result = execute_tool(fast_fallback.name, fast_fallback.arguments)
                    logger.info(f"[FAST MODE] Result: {result}")
                    
                    # Hata kontrolü
                    if isinstance(result, dict) and result.get("error"):
                        error_msg = f"❌ Hata: {result['error']}"
                        messages.append(ChatMessage(role="assistant", content=error_msg))
                        self.store.save(session_id, messages)
                        return error_msg, 1, [fast_fallback.name], []
                    
                    # Medya dosyalarini topla - result'taki path'i kontrol et
                    if isinstance(result, dict) and result.get("path"):
                        from pathlib import Path
                        result_path = Path(result["path"])
                        logger.info(f"[FAST MODE] Result path: {result_path}, exists: {result_path.exists()}")
                        
                        # Dosya gercekten varsa media listesine ekle
                        if result_path.exists() and result_path.is_file():
                            abs_path = str(result_path.resolve())
                            if abs_path not in media_files:
                                media_files.append(abs_path)
                                logger.info(f"[FAST MODE] Added to media: {abs_path}")
                        else:
                            logger.warning(f"[FAST MODE] File not found: {result_path}")
                    
                    self._collect_media(result, media_files)
                    
                    # Basari mesaji olustur
                    success_msg = self._build_success_message(fast_fallback.name, result)
                    messages.append(ChatMessage(role="assistant", content=success_msg))
                    self.store.save(session_id, messages)
                    
                    logger.info(f"[FAST MODE] Success! Media files: {media_files}")
                    return success_msg, 1, [fast_fallback.name], media_files
                    
                except Exception as exc:
                    logger.error(f"[FAST MODE] Exception: {exc}")
                    error_msg = f"❌ Hata: {fast_fallback.name} calistirilamadi: {exc}"
                    messages.append(ChatMessage(role="assistant", content=error_msg))
                    self.store.save(session_id, messages)
                    return error_msg, 1, [fast_fallback.name], []

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
                and not self._is_negative_tool_mention(user_message, "research_and_report")
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
                
                # research_and_report icin topic kontrolu - COK KATIL
                if call_name == "research_and_report" and not args.get("topic"):
                    # 1. Once notebook resume'tan gelen goal'i kullan
                    topic_set = False
                    
                    # Notebook resume context'inden al
                    for msg in reversed(messages):
                        if msg.role == "system" and "[SISTEM NOTU]" in msg.content:
                            if "Hedef:" in msg.content:
                                lines = msg.content.split("\n")
                                for line in lines:
                                    if line.strip().startswith("Hedef:"):
                                        goal = line.replace("Hedef:", "").strip()
                                        if goal and goal != "":
                                            args["topic"] = goal
                                            topic_set = True
                                            import logging
                                            logging.getLogger(__name__).info(f"[TOPIC FIXED] From notebook context: {goal}")
                                            break
                            break
                    
                    # 2. Hala yoksa aktif notebook'lara bak
                    if not topic_set:
                        try:
                            from .tools.notebook_tools import tool_notebook_list, tool_notebook_status
                            list_result = tool_notebook_list()
                            notebooks = list_result.get("notebooks", [])
                            if notebooks:
                                incomplete = [n for n in notebooks if n.get("status") == "Devam Ediyor"]
                                if incomplete:
                                    nb_name = incomplete[0]["name"]
                                    status = tool_notebook_status(nb_name)
                                    goal = status.get("goal", "")
                                    if goal:
                                        args["topic"] = goal
                                        topic_set = True
                                    else:
                                        args["topic"] = nb_name.replace("_", " ")
                                        topic_set = True
                                else:
                                    args["topic"] = notebooks[0]["name"].replace("_", " ")
                                    topic_set = True
                        except Exception:
                            pass
                    
                    # 3. Hala yoksa kullanici mesajindan cikarsamaya calis
                    if not topic_set and not args.get("topic"):
                        user_msg = ""
                        for msg in reversed(messages):
                            if msg.role == "user":
                                user_msg = msg.content
                                break
                        # Mesajdan konu cikar
                        if user_msg:
                            if "hakkinda" in user_msg.lower():
                                args["topic"] = user_msg.lower().split("hakkinda")[0].strip()
                            elif "icin" in user_msg.lower():
                                args["topic"] = user_msg.lower().split("icin")[0].strip()
                            else:
                                args["topic"] = user_msg[:100]
                        else:
                            args["topic"] = "Genel arastirma"
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

    def _is_fast_tool(self, tool_name: str) -> bool:
        """Hizli calisacak, dusunme gerektirmeyen araclar.
        
        Bu araçlar LLM'in 'dusunme' asamasini atlayarak dogrudan calistirilir.
        Sonuc aninda dondurulur (~1-2 saniye).
        """
        # NOT: Notebook araçları HIZLI MODDA YOK çünkü devam eden iş akışı gerektirir
        fast_tools = {
            # Ekran - Anlık görüntü
            "screenshot_desktop", "screenshot_webpage",
            
            # Webcam - Anlık fotoğraf/video
            "webcam_capture", "webcam_record_video", "list_cameras",
            
            # Ses - Kayıt ve çalma
            "start_audio_recording", "stop_audio_recording", 
            "play_audio", "text_to_speech",
            
            # OCR - Anlık metin okuma
            "ocr_screenshot", "ocr_image",
            
            # Sistem - Bilgi sorgulama
            "get_system_info", "list_processes", "network_info", "ping_host",
            
            # Dosya - Okuma ve listeleme (yazma/silme hariç)
            "list_directory", "read_file", "search_files",
            
            # USB - Liste görüntüleme
            "list_usb_devices",
            
            # Fare - Pozisyon sorgulama (hareket hariç)
            "mouse_position",
            
            # Pencere - Liste görüntüleme
            "get_window_list",
        }
        return tool_name in fast_tools

    def _fallback_tool_call_from_user_message(self, user_message: str) -> Optional[ParsedTextToolCall]:
        text = (user_message or "").strip()
        if not text:
            return None

        normalized = self._normalize_text_for_match(text)

        for tool_name in sorted(self._known_tool_names, key=len, reverse=True):
            tool_norm = self._normalize_text_for_match(tool_name)
            explicit_patterns = (
                rf"\b(?:tool|arac|command|komut|name)\s*[:=]\s*{re.escape(tool_norm)}\b",
                rf"\b(?:run|execute|calistir|kullan)\s+{re.escape(tool_norm)}\b",
                rf"^\s*{re.escape(tool_norm)}\s*(?:\(|$)",
            )
            if (
                any(re.search(pattern, normalized) for pattern in explicit_patterns)
                and not self._is_negative_tool_mention(text, tool_name)
            ):
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

        # EKRAN GÖRÜNTÜSÜ ALMA - Fallback kuralları
        if "screenshot_desktop" in self._known_tool_names and any(
            k in normalized for k in ("ekran goruntusu", "screenshot", "desktop", "masaustu", "anlik goruntu", "fotograf cek")
        ) and any(k in normalized for k in ("al", "cek", "gonder", "kaydet", "goster")):
            return ParsedTextToolCall(
                id=f"text_tc_{uuid.uuid4().hex[:10]}",
                name="screenshot_desktop",
                arguments={},
            )
        
        if "screenshot_webpage" in self._known_tool_names and any(
            k in normalized for k in ("web sayfa", "website", "site", "url", "http")
        ) and any(k in normalized for k in ("ekran goruntusu", "screenshot", "goruntu", "al", "cek")):
            # URL'yi bul
            url_match = re.search(r"https?://\S+", text)
            if url_match:
                return ParsedTextToolCall(
                    id=f"text_tc_{uuid.uuid4().hex[:10]}",
                    name="screenshot_webpage",
                    arguments={"url": url_match.group(0).rstrip(".,)")},
                )

        # NOTEBOOK DEVAM ETME - "devam et", "rapora devam" vb.
        if "notebook_status" in self._known_tool_names and any(
            k in normalized for k in ("devam", "tamamla", "bitir", "ilerle", "sonraki adim", "rapor")
        ):
            # Mevcut not defterini bul
            from .tools.notebook_tools import tool_notebook_list
            try:
                list_result = tool_notebook_list()
                notebooks = list_result.get("notebooks", [])
                
                # Devam eden not defteri bul
                incomplete = [n for n in notebooks if n.get("status") == "Devam Ediyor"]
                if incomplete:
                    nb_name = incomplete[0]["name"]  # En sonuncu
                    return ParsedTextToolCall(
                        id=f"text_tc_{uuid.uuid4().hex[:10]}",
                        name="notebook_status",
                        arguments={"name": nb_name},
                    )
            except:
                pass

        # Kapsamlı görev algılama -> notebook_create öner
        if "notebook_create" in self._known_tool_names and any(
            k in normalized for k in ("kapsamli", "detayli", "adim adim", "parcala", "tum", "karsilastir")
        ) and any(
            k in normalized for k in ("arastir", "analiz", "rapor", "incele", "haber", "research")
        ):
            # Not defteri adı oluştur
            topic_words = [w for w in text.split()[:5] if len(w) > 2]
            nb_name = "_".join(topic_words[:3]) or "arastirma"
            return ParsedTextToolCall(
                id=f"text_tc_{uuid.uuid4().hex[:10]}",
                name="notebook_create",
                arguments={
                    "name": nb_name,
                    "goal": text,
                    "steps": "Haber ve kaynak ara\nKaynaklari oku ve not al\nBulgulari carpraz kontrol et\nRapor olustur",
                },
            )

        if "search_news" in self._known_tool_names and any(k in normalized for k in ("haber", "news", "gundem")):
            return ParsedTextToolCall(
                id=f"text_tc_{uuid.uuid4().hex[:10]}",
                name="search_news",
                arguments={"query": text},
            )
        
        # WEBCAM FOTOĞRAF ÇEKME - Geliştirilmiş pattern matching
        if "webcam_capture" in self._known_tool_names and any(
            k in normalized for k in ("webcam", "kamera", "fotograf cek", "fotograf cek", "selfie", 
                                      "anlik foto", "kamerani ac", "cam ac", "beni goster")
        ) and any(k in normalized for k in ("cek", "al", "gonder", "fotograf", "ac", "goster")):
            return ParsedTextToolCall(
                id=f"text_tc_{uuid.uuid4().hex[:10]}",
                name="webcam_capture",
                arguments={},
            )
        
        # WEBCAM VIDEO KAYDETME
        if "webcam_record_video" in self._known_tool_names and any(
            k in normalized for k in ("webcam video", "kamera video", "video kaydet", "video cek")
        ):
            return ParsedTextToolCall(
                id=f"text_tc_{uuid.uuid4().hex[:10]}",
                name="webcam_record_video",
                arguments={"duration": 5},
            )
        
        # SES KAYDI - Yeni eklendi
        if "start_audio_recording" in self._known_tool_names and any(
            k in normalized for k in ("ses kaydet", "ses kaydi", "mikrofon", "audio record", 
                                      "voice record", "sesini kaydet", "konus")
        ) and any(k in normalized for k in ("kaydet", "kaydi", "ac", "baslat", "konus")):
            return ParsedTextToolCall(
                id=f"text_tc_{uuid.uuid4().hex[:10]}",
                name="start_audio_recording",
                arguments={},
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

    def _try_fast_notebook_resume(
        self,
        user_message: str,
        notebook_name: str,
        notebook_status: Dict[str, Any],
    ) -> Tuple[str, List[str]]:
        normalized = self._normalize_text_for_match(user_message)
        status_only_markers = ("durum", "status", "ilerleme", "kac adim")
        if any(marker in normalized for marker in status_only_markers):
            return "", []

        pending = notebook_status.get("pending_steps", []) or []
        if not pending:
            return "", []

        next_step = str(pending[0]).strip()
        if not next_step:
            return "", []

        tools_used: List[str] = []
        goal = str(notebook_status.get("goal", "")).strip()
        step_norm = self._normalize_text_for_match(next_step)

        try:
            note_parts: List[str] = [f"Otomatik devam: {next_step}"]
            finding = "Adim tamamlandi."

            if any(k in step_norm for k in ("haber", "kaynak", "gelisme", "topla", "tara")):
                query = self._derive_news_query(goal or next_step)
                news_result = execute_tool("search_news", {"query": query, "limit": 6})
                tools_used.append("search_news")
                count = int(news_result.get("count", 0) or 0)
                finding = f"{count} kaynak listelendi."
                if count > 0:
                    titles: List[str] = []
                    for item in (news_result.get("results") or [])[:3]:
                        title = str((item or {}).get("title", "")).strip()
                        if title:
                            titles.append(title)
                    if titles:
                        note_parts.append("Ilk basliklar: " + " | ".join(titles))
                else:
                    warn = str(news_result.get("error", "")).strip()
                    if warn:
                        note_parts.append(f"Kaynak toplama uyari: {warn}")

            note_text = " ".join(part for part in note_parts if part).strip()
            execute_tool("notebook_add_note", {"name": notebook_name, "note": note_text})
            tools_used.append("notebook_add_note")

            step_keyword = self._step_keyword(next_step)
            complete_result = execute_tool(
                "notebook_complete_step",
                {"name": notebook_name, "step_keyword": step_keyword, "finding": finding},
            )
            tools_used.append("notebook_complete_step")

            if isinstance(complete_result, dict) and complete_result.get("error"):
                return "", []

            status_after = execute_tool("notebook_status", {"name": notebook_name})
            tools_used.append("notebook_status")
            done = int(status_after.get("completed_steps", 0) or 0)
            total = int(status_after.get("total_steps", 0) or 0)
            upcoming = status_after.get("next_step", "")

            if upcoming:
                reply = (
                    f"Not defteri guncellendi: `{notebook_name}`\n"
                    f"Ilerleme: {done}/{max(total, 1)} adim tamamlandi.\n"
                    f"Tamamlanan adim: {next_step}\n"
                    f"Siradaki adim: {upcoming}\n\n"
                    f"Devam etmek icin \"devam et\" yazabilirsiniz."
                )
            else:
                reply = (
                    f"Not defteri tamamlandi: `{notebook_name}`\n"
                    f"Ilerleme: {done}/{max(total, 1)} adim tamamlandi."
                )
            return reply, tools_used
        except Exception:
            return "", []

    @staticmethod
    def _derive_news_query(goal: str) -> str:
        words = re.findall(r"[A-Za-z0-9ÇĞİÖŞÜçğıöşü]+", goal)
        filtered = [w for w in words if len(w) > 2][:8]
        if not filtered:
            return "dunya gundem"
        return " ".join(filtered)

    def _try_auto_notebook_kickoff(
        self,
        user_message: str,
        notebook_resume: Optional[Tuple[str, Dict[str, Any]]],
    ) -> Tuple[str, List[str]]:
        if not self._should_auto_kickoff_notebook(user_message, notebook_resume):
            return "", []

        tools_used: List[str] = []
        goal = (user_message or "").strip()
        if not goal:
            return "", []

        try:
            notebook_name = self._suggest_notebook_name(goal)
            steps = self._default_notebook_steps(goal)
            first_step = steps[0] if steps else "Kapsam ve metodoloji planini olustur"

            create_result = execute_tool(
                "notebook_create",
                {
                    "name": notebook_name,
                    "goal": goal,
                    "steps": "\n".join(steps),
                },
            )
            tools_used.append("notebook_create")
            if isinstance(create_result, dict) and create_result.get("error"):
                return "", []

            kickoff_note = (
                "Kickoff tamamlandi: gorev kapsami alindi, adimlar olusturuldu ve "
                "ilk adim (planlama) otomatik tamamlandi."
            )
            execute_tool("notebook_add_note", {"name": notebook_name, "note": kickoff_note})
            tools_used.append("notebook_add_note")

            step_keyword = self._step_keyword(first_step)
            complete_result = execute_tool(
                "notebook_complete_step",
                {
                    "name": notebook_name,
                    "step_keyword": step_keyword,
                    "finding": "Plan ve is akisi hazirlandi.",
                },
            )
            tools_used.append("notebook_complete_step")

            status_result = execute_tool("notebook_status", {"name": notebook_name})
            tools_used.append("notebook_status")
        except Exception:
            return "", []

        total = int(status_result.get("total_steps", len(steps)) or len(steps))
        done = int(status_result.get("completed_steps", 1) or 1)
        next_step = status_result.get("next_step", "Kaynak toplama")

        if isinstance(complete_result, dict) and complete_result.get("error"):
            # Adim anahtar kelimesi eslesmediyse fallback: ilerlemeyi yansitmadan devam mesaji ver.
            done = max(done, 0)

        reply = (
            f"Not defteri olusturuldu: `{notebook_name}`\n"
            f"Ilerleme: {done}/{max(total, 1)} adim tamamlandi.\n"
            f"Siradaki adim: {next_step}\n\n"
            f"Devam etmek icin: \"{notebook_name} raporuna devam et\" yazabilirsiniz."
        )
        return reply, tools_used

    def _should_auto_kickoff_notebook(
        self,
        user_message: str,
        notebook_resume: Optional[Tuple[str, Dict[str, Any]]],
    ) -> bool:
        if notebook_resume:
            return False
        text = (user_message or "").strip()
        if len(text) < 80:
            return False

        normalized = self._normalize_text_for_match(text)

        skip_markers = (
            "devam et",
            "rapora devam",
            "not defter",
            "siradaki adim",
            "webcam",
            "ekran goruntusu",
            "screenshot",
        )
        if any(marker in normalized for marker in skip_markers):
            return False

        complex_markers = (
            "arastir",
            "detayli",
            "analiz",
            "rapor",
            "tum gelisme",
            "karsilastir",
            "etkisi",
        )
        domain_markers = (
            "iran",
            "abd",
            "amerika",
            "savas",
            "piyasa",
            "ekonomi",
            "haber",
            "dunya",
            "world",
        )
        return any(k in normalized for k in complex_markers) and any(k in normalized for k in domain_markers)

    @staticmethod
    def _default_notebook_steps(goal: str) -> List[str]:
        return [
            "Kapsam ve metodoloji planini olustur",
            "Son 48 saatin kritik haber kaynaklarini topla",
            "Kaynaklari tarih ve guvenilirlik bazinda dogrula",
            "Finansal ve kuresel etkileri siniflandir",
            "Rapor taslagini olustur",
            "Nihai dosyalari (txt/docx/pdf) hazirla",
        ]

    @staticmethod
    def _suggest_notebook_name(goal: str) -> str:
        words = re.findall(r"[A-Za-z0-9ÇĞİÖŞÜçğıöşü]+", goal)
        keep = [w for w in words if len(w) > 2][:4]
        name = "_".join(keep) if keep else "Arastirma_Notu"
        return name[:60]

    @staticmethod
    def _step_keyword(step_text: str) -> str:
        words = re.findall(r"[A-Za-z0-9ÇĞİÖŞÜçğıöşü]+", step_text)
        key = " ".join(words[:4]).strip()
        return key or step_text[:24]

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

    @staticmethod
    def _is_negative_tool_mention(text: str, tool_name: str) -> bool:
        normalized = AgentService._normalize_text_for_match(text)
        tool_norm = AgentService._normalize_text_for_match(tool_name)
        if tool_norm not in normalized:
            return False

        negative_patterns = (
            rf"\b{re.escape(tool_norm)}\b\s*(?:ile\s*)?(?:kullanma|kullanmadan|olmadan|haric|disinda|except|without)\b",
            rf"\b(?:kullanma|kullanmadan|olmadan|haric|disinda|except|without)\s+\b{re.escape(tool_norm)}\b",
        )
        return any(re.search(pattern, normalized) for pattern in negative_patterns)

    async def _handle_audio_recording_fast(self, session_id: str, messages: List[ChatMessage], user_message: str) -> Tuple[str, int, List[str], List[str]]:
        """Ses kaydı için fast mode handler - start, bekle, stop yapar."""
        import logging
        import asyncio
        import re
        logger = logging.getLogger(__name__)
        
        # Kullanıcıdan süre al (varsayılan 5 saniye)
        duration = 5
        duration_match = re.search(r'(\d+)\s*(?:sn|saniye|sec|dk|dakika|min)', user_message.lower())
        if duration_match:
            duration = int(duration_match.group(1))
            if 'dk' in user_message.lower() or 'dakika' in user_message.lower() or 'min' in user_message.lower():
                duration *= 60
            # Max 60 saniye
            duration = min(duration, 60)
        
        logger.info(f"[AUDIO FAST] Starting recording for {duration} seconds")
        
        try:
            # 1. Kaydı başlat
            from .tools.registry import execute_tool
            start_result = execute_tool("start_audio_recording", {})
            logger.info(f"[AUDIO FAST] Start result: {start_result}")
            
            if isinstance(start_result, dict) and start_result.get("error"):
                error_msg = f"❌ Ses kaydı başlatılamadı: {start_result['error']}"
                messages.append(ChatMessage(role="assistant", content=error_msg))
                self.store.save(session_id, messages)
                return error_msg, 1, ["start_audio_recording"], []
            
            # 2. Kullanıcıya bilgi ver
            info_msg = f"🎙️ Ses kaydı başladı ({duration} saniye)..."
            messages.append(ChatMessage(role="assistant", content=info_msg))
            self.store.save(session_id, messages)
            
            # 3. Bekle
            await asyncio.sleep(duration)
            
            # 4. Kaydı durdur
            stop_result = execute_tool("stop_audio_recording", {})
            logger.info(f"[AUDIO FAST] Stop result: {stop_result}")
            
            # 5. Hata kontrolü
            if isinstance(stop_result, dict) and stop_result.get("error"):
                error_msg = f"❌ Ses kaydı kaydedilemedi: {stop_result['error']}"
                messages.append(ChatMessage(role="assistant", content=error_msg))
                self.store.save(session_id, messages)
                return error_msg, 1, ["start_audio_recording", "stop_audio_recording"], []
            
            # 6. Medya dosyasını topla
            media_files: List[str] = []
            self._collect_media(stop_result, media_files)
            
            # 7. Başarı mesajı
            success_msg = self._build_success_message("stop_audio_recording", stop_result)
            messages.append(ChatMessage(role="assistant", content=success_msg))
            self.store.save(session_id, messages)
            
            logger.info(f"[AUDIO FAST] Success! Media: {media_files}")
            return success_msg, 2, ["start_audio_recording", "stop_audio_recording"], media_files
            
        except Exception as exc:
            logger.error(f"[AUDIO FAST] Exception: {exc}")
            error_msg = f"❌ Ses kaydı hatası: {exc}"
            messages.append(ChatMessage(role="assistant", content=error_msg))
            self.store.save(session_id, messages)
            return error_msg, 1, ["start_audio_recording"], []

    @staticmethod
    def _build_success_message(tool_name: str, result: Dict[str, Any]) -> str:
        """Başarı mesajı oluştur."""
        success_msg = f"✅ Islem tamamlandi: `{tool_name}`"
        
        if isinstance(result, dict):
            if "path" in result:
                success_msg += f"\n📁 Dosya: {result['path']}"
            if "resolution" in result:
                success_msg += f"\n📐 Cozunurluk: {result['resolution']}"
            if "size" in result:
                size = result['size']
                if isinstance(size, int):
                    if size > 1024 * 1024:
                        success_msg += f"\n📊 Boyut: {size / (1024 * 1024):.2f} MB"
                    elif size > 1024:
                        success_msg += f"\n📊 Boyut: {size / 1024:.2f} KB"
                    else:
                        success_msg += f"\n📊 Boyut: {size} bytes"
            if "duration" in result:
                success_msg += f"\n⏱️ Sure: {result['duration']} sn"
            if "text" in result and len(result['text']) < 100:
                success_msg += f"\n📝 Metin: {result['text']}"
        
        return success_msg
