from __future__ import annotations

import asyncio
import html as html_lib
import json
import logging
import re
import time
import unicodedata
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
from .tools.registry import execute_tool, get_relevant_tools, get_tool_specs, get_tools_by_names, serialize_tool_result

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
        self._session_running_tasks: Dict[str, asyncio.Task] = {}
        self._session_locks_guard = asyncio.Lock()
        self._known_tool_names = self._extract_tool_names()
        self._vscode_extension_presence_cache: Dict[str, bool] = {}
        self._pending_watcher_confirmation: Dict[str, Dict[str, Any]] = {}

    async def run(
        self,
        session_id: str,
        user_message: str,
        tool_subset: Optional[List[str]] = None,
        prompt_suffix: str = "",
    ) -> Tuple[str, int, List[str], List[str]]:
        current_task = asyncio.current_task()
        emergency = await self._try_handle_emergency_stop(session_id, user_message, current_task)
        if emergency is not None:
            return emergency

        lock = await self._get_session_lock(session_id)

        if lock.locked():
            if self._is_global_stop_request(user_message):
                await self._cancel_running_task(session_id, current_task)
                lines: List[str] = ["Aktif isleme iptal sinyali gonderildi."]
                used_tools: List[str] = []
                if "stop_approval_watcher" in self._known_tool_names:
                    try:
                        stop_result = execute_tool("stop_approval_watcher", {})
                        used_tools.append("stop_approval_watcher")
                        if isinstance(stop_result, dict):
                            stop_message = str(stop_result.get("message", "")).strip()
                            if stop_message:
                                lines.append(stop_message)
                    except Exception:
                        lines.append("Onay izleyici durdurulamadi.")
                return "\n".join(lines), 1, used_tools, []
            quick_stop_reply, quick_stop_tools = self._try_force_watcher_stop_while_busy(user_message)
            if quick_stop_reply:
                return quick_stop_reply, 1, quick_stop_tools, []
            if self._should_interrupt_running_task(user_message):
                await self._cancel_running_task(session_id, current_task)
            try:
                await asyncio.wait_for(
                    lock.acquire(),
                    timeout=self._lock_wait_timeout_seconds(user_message),
                )
            except asyncio.TimeoutError:
                return self._build_busy_reply(user_message), 1, [], []
        else:
            await lock.acquire()

        try:
            async with self._session_locks_guard:
                if current_task is not None:
                    self._session_running_tasks[session_id] = current_task
            return await asyncio.wait_for(
                self._run_locked(session_id, user_message, tool_subset=tool_subset, prompt_suffix=prompt_suffix),
                timeout=self._request_timeout_seconds(user_message),
            )
        except asyncio.TimeoutError:
            return self._build_timeout_reply(session_id, user_message), 1, [], []
        except asyncio.CancelledError:
            return "Onceki islem yeni isteginiz nedeniyle durduruldu.", 1, [], []
        finally:
            async with self._session_locks_guard:
                existing = self._session_running_tasks.get(session_id)
                if existing is current_task:
                    self._session_running_tasks.pop(session_id, None)
            if lock.locked():
                lock.release()

    async def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        async with self._session_locks_guard:
            lock = self._session_locks.get(session_id)
            if lock is None:
                lock = asyncio.Lock()
                self._session_locks[session_id] = lock
            return lock

    async def _cancel_running_task(
        self,
        session_id: str,
        requester_task: Optional[asyncio.Task],
    ) -> None:
        async with self._session_locks_guard:
            running = self._session_running_tasks.get(session_id)
        if running is None or running.done() or running is requester_task:
            return
        running.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(running), timeout=1.5)
        except Exception:
            pass

    def _lock_wait_timeout_seconds(self, user_message: str) -> float:
        normalized = self._normalize_text_for_match(user_message)
        if any(k in normalized for k in ("screenshot", "ekran goruntusu", "webcam", "kamera", "ses kaydi")):
            return 1.5
        if self._extract_approval_watcher_action(user_message) == "stop":
            return 1.2
        if self._is_resume_like_request(user_message):
            return 3.0
        return 4.0

    def _try_force_watcher_stop_while_busy(self, user_message: str) -> Tuple[str, List[str]]:
        if self._extract_approval_watcher_action(user_message) != "stop":
            return "", []
        if "stop_approval_watcher" not in self._known_tool_names:
            return "Onay izleyici araci aktif degil.", []
        try:
            result = execute_tool("stop_approval_watcher", {})
        except Exception as exc:
            return f"Hata: onay izleyici durdurulamadi: {exc}", ["stop_approval_watcher"]
        if isinstance(result, dict) and result.get("error"):
            return f"Hata: {result.get('error')}", ["stop_approval_watcher"]
        if isinstance(result, dict):
            message = str(result.get("message", "")).strip()
            if message:
                return message, ["stop_approval_watcher"]
        return "Onay izleyici kapatildi.", ["stop_approval_watcher"]

    @staticmethod
    def _is_global_stop_request(user_message: str) -> bool:
        normalized = AgentService._normalize_text_for_match(user_message)
        if not normalized:
            return False
        stop_verbs = ("iptal", "durdur", "cancel", "stop", "vazgec", "yarida birak", "birak", "kes")
        scope_markers = ("islem", "gorev", "rapor", "ajan", "hepsi", "tum", "tamamen", "calismayi")
        if any(v in normalized for v in stop_verbs) and any(s in normalized for s in scope_markers):
            return True
        # Kisa ve net komutlari da kabul et.
        compact = normalized.replace(" ", "")
        return compact in {"iptalet", "islemiiptalet", "gorevidurdur", "hepsinidurdur", "stopeverything"}

    async def _try_handle_emergency_stop(self, session_id: str, user_message: str, requester_task: Optional[asyncio.Task]) -> Tuple[str, int, List[str], List[str]] | None:
        watcher_action = self._extract_approval_watcher_action(user_message)
        is_global_stop = self._is_global_stop_request(user_message)
        if watcher_action != "stop" and not is_global_stop:
            return None

        used_tools: List[str] = []
        running_cancelled = False

        # Session task'ini lock beklemeden kesmeyi dene.
        async with self._session_locks_guard:
            running = self._session_running_tasks.get(session_id)
        if running is not None and running is not requester_task and not running.done():
            running.cancel()
            running_cancelled = True

        watcher_reply = ""
        if "stop_approval_watcher" in self._known_tool_names:
            try:
                stop_result = execute_tool("stop_approval_watcher", {})
                used_tools.append("stop_approval_watcher")
                if isinstance(stop_result, dict):
                    watcher_reply = str(stop_result.get("message", "")).strip()
                    if stop_result.get("error"):
                        watcher_reply = f"Hata: {stop_result.get('error')}"
            except Exception as exc:
                watcher_reply = f"Hata: onay izleyici durdurulamadi: {exc}"
        else:
            watcher_reply = "Onay izleyici araci aktif degil."

        # Bekleyen onay state'lerini temizle.
        self._pending_watcher_confirmation.pop(session_id, None)

        lines: List[str] = []
        if is_global_stop:
            if running_cancelled:
                lines.append("Aktif isleme iptal sinyali gonderildi.")
            else:
                lines.append("Aktif uzun islem bulunmuyor.")
        if watcher_reply:
            lines.append(watcher_reply)
        if not lines:
            lines.append("Durdurma komutu uygulandi.")
        reply = "\n".join(lines)
        return reply, 1, list(dict.fromkeys(used_tools)), []

    def _request_timeout_seconds(self, user_message: str) -> float:
        normalized = self._normalize_text_for_match(user_message)
        if any(k in normalized for k in ("screenshot", "ekran goruntusu", "webcam", "kamera", "ses kaydi")):
            return float(max(20, int(getattr(settings, "agent_timeout_media_sec", 25))))
        if any(k in normalized for k in ("vscode", "vs code", "kimicode", "kimi code", "codex", "claude code", "claudecode")) and any(
            k in normalized for k in ("yaz", "session", "oturum", "onay", "kabul", "izin", "approve", "allow")
        ):
            return float(max(90, int(getattr(settings, "agent_timeout_automation_sec", 180))))
        if self._is_resume_like_request(user_message):
            return float(max(90, int(getattr(settings, "agent_timeout_resume_sec", 180))))
        if any(k in normalized for k in ("arastir", "detayli", "analiz", "rapor")):
            return float(max(120, int(getattr(settings, "agent_timeout_research_sec", 420))))
        return float(max(90, int(getattr(settings, "agent_timeout_default_sec", 240))))

    def _build_busy_reply(self, user_message: str) -> str:
        if self._is_resume_like_request(user_message):
            return (
                "Onceki islem halen calisiyor. Birkac saniye sonra tekrar \"devam et\" yazin."
            )
        return (
            "Onceki islem halen calisiyor. Yeni gorevi hemen baslatamiyorum; "
            "birkac saniye sonra tekrar gonderin."
        )

    def _build_timeout_reply(self, session_id: str, user_message: str) -> str:
        if self._is_resume_like_request(user_message):
            session_messages = self.store.load(session_id)
            notebook_name = self._extract_session_notebook_name(session_messages)
            if notebook_name:
                return (
                    f"Not defteri adimi zaman asimina ugradi: `{notebook_name}`.\n"
                    "Ayni adimi tekrar denemek icin \"devam et\" yazabilirsiniz."
                )
            return "Devam adimi zaman asimina ugradi. Lutfen tekrar \"devam et\" yazin."
        return (
            "Islem zaman asimina ugradi. Model uzun sure dusunuyor olabilir.\n"
            "Ayni istegi tekrar gonderebilir veya \"devam et\" yazarak kaldigi yerden surdurmeyi deneyebilirsiniz."
        )

    def _should_interrupt_running_task(self, user_message: str) -> bool:
        # Resume/ilerleme mesajlari onceki akisi bozmamali; yeni gorevler onceki uzun islemi kesebilsin.
        return not self._is_resume_like_request(user_message)

    def _check_notebook_resume(self, user_message: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Kullanici 'devam et' veya notebook adi soylerse, devam etme bilgisi dondur."""
        from .tools.notebook_tools import tool_notebook_list, tool_notebook_status
        
        normalized = self._normalize_text_for_match(user_message)
        
        # Sadece net resume niyeti varsa otomatik devam et.
        is_resume_request = self._is_resume_like_request(user_message)
        
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
            
            if specific_notebook:
                status = tool_notebook_status(specific_notebook["name"])
                return (specific_notebook["name"], status)
        except Exception:
            pass
        
        return None

    async def _run_locked(
        self,
        session_id: str,
        user_message: str,
        tool_subset: Optional[List[str]] = None,
        prompt_suffix: str = "",
    ) -> Tuple[str, int, List[str], List[str]]:
        messages = self.store.load(session_id)
        if not messages:
            messages.append(ChatMessage(role="system", content=build_system_prompt(suffix=prompt_suffix)))
            # Inject long-term memory context on session initialization
            try:
                from .vector_memory import memory_get_context
                mems = memory_get_context(limit=10)
                if mems:
                    mem_blocks = "\n".join(f"- {m}" for m in mems)
                    mem_sys_msg = f"=== UZUN SURELI HAFIZAN ===\nAsagidaki bilgiler onceki konusmalarindan ogrendiklerin:\n{mem_blocks}\n=========================="
                    messages.append(ChatMessage(role="system", content=mem_sys_msg))
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to load memory context: {e}")

        if contains_forbidden_financial_intent(user_message):
            refusal = (
                "Finansal islem taleplerini yerine getirmem yasak: kredi karti, odeme, para transferi "
                "ve satin alma islemleri yapmam."
            )
            messages.append(ChatMessage(role="user", content=user_message))
            messages.append(ChatMessage(role="assistant", content=refusal))
            self.store.save(session_id, messages)
            return refusal, 0, [], []

        pending_reply, pending_tools, pending_consumed = self._try_handle_pending_watcher_confirmation(
            session_id,
            user_message,
        )
        if pending_consumed:
            messages.append(ChatMessage(role="user", content=user_message))
            messages.append(ChatMessage(role="assistant", content=pending_reply))
            self.store.save(session_id, messages)
            return pending_reply, 1, pending_tools, []

        completion_reply, completion_tools, completion_consumed = self._try_handle_completion_prompt_answer(user_message)
        if completion_consumed:
            messages.append(ChatMessage(role="user", content=user_message))
            messages.append(ChatMessage(role="assistant", content=completion_reply))
            self.store.save(session_id, messages)
            return completion_reply, 1, completion_tools, []

        if self._is_no_action_check_request(user_message):
            reply = (
                "Kontrol modu acik: otomasyon araci calistirmadim.\n"
                "Sadece durum kontrolu yapildi; timeout loop'u tetiklenmedi.\n"
                "Gercek test icin eylem komutunu ayri gonderin (ornek: \"OpenWorld klasorunu VS Code ile ac\")."
            )
            messages.append(ChatMessage(role="user", content=user_message))
            messages.append(ChatMessage(role="assistant", content=reply))
            self.store.save(session_id, messages)
            return reply, 1, [], []

        if self._is_incomplete_task_query(user_message):
            list_reply, list_tools = self._build_incomplete_task_reply()
            messages.append(ChatMessage(role="user", content=user_message))
            messages.append(ChatMessage(role="assistant", content=list_reply))
            self.store.save(session_id, messages)
            return list_reply, 1, list_tools, []

        vscode_chat_reply, vscode_chat_tools = self._try_fast_vscode_agent_chat_write(session_id, user_message)
        if vscode_chat_reply:
            messages.append(ChatMessage(role="user", content=user_message))
            messages.append(ChatMessage(role="assistant", content=vscode_chat_reply))
            self.store.save(session_id, messages)
            return vscode_chat_reply, 1, vscode_chat_tools, []

        ide_approval_reply, ide_approval_tools = self._try_fast_ide_approval_unblock(user_message)
        if ide_approval_reply:
            messages.append(ChatMessage(role="user", content=user_message))
            messages.append(ChatMessage(role="assistant", content=ide_approval_reply))
            self.store.save(session_id, messages)
            return ide_approval_reply, 1, ide_approval_tools, []

        approval_watcher_reply, approval_watcher_tools = self._try_fast_approval_watcher_control(user_message)
        if approval_watcher_reply:
            messages.append(ChatMessage(role="user", content=user_message))
            messages.append(ChatMessage(role="assistant", content=approval_watcher_reply))
            self.store.save(session_id, messages)
            return approval_watcher_reply, 1, approval_watcher_tools, []

        # NOTEBOOK DEVAM ETME KONTROLU
        notebook_resume = self._check_notebook_resume(user_message)
        notebook_goal_for_research = ""  # research_and_report icin topic sakla
        normalized_user_message = self._normalize_text_for_match(user_message)
        session_notebook = self._extract_session_notebook_name(messages)
        is_resume_like_request = self._is_resume_like_request(user_message)
        generic_resume_tokens = {"devam", "et", "tamamla", "bitir", "ilerle", "sonraki", "adim"}
        words = [w for w in re.findall(r"[^\W_]+", normalized_user_message, flags=re.UNICODE) if w]
        is_generic_resume_request = bool(words) and len(words) <= 3 and all(w in generic_resume_tokens for w in words)

        # Kisa "devam et/durum" mesajlarinda oturumun kendi notebook'unu tercih et.
        should_prefer_session_notebook = is_resume_like_request and session_notebook and (
            is_generic_resume_request or len(normalized_user_message.strip()) <= 20
        )
        if should_prefer_session_notebook:
            try:
                from .tools.notebook_tools import tool_notebook_status
                status = tool_notebook_status(session_notebook)
                if not status.get("error"):
                    notebook_resume = (session_notebook, status)
            except Exception:
                pass
        elif not notebook_resume and is_resume_like_request and session_notebook:
            try:
                from .tools.notebook_tools import tool_notebook_status
                status = tool_notebook_status(session_notebook)
                if not status.get("error"):
                    notebook_resume = (session_notebook, status)
            except Exception:
                pass

        if is_resume_like_request and not notebook_resume:
            try:
                from .tools.notebook_tools import tool_notebook_list
                listing = tool_notebook_list()
                notebooks = listing.get("notebooks", []) if isinstance(listing, dict) else []
            except Exception:
                notebooks = []

            if notebooks:
                incomplete = [n for n in notebooks if n.get("status") == "Devam Ediyor"]
                if incomplete:
                    suggestion = incomplete[0]
                    quick_reply = (
                        "Devam etmek icin hedef not defterini belirtin.\n"
                        f"Oneri: `{suggestion.get('name', '')}` ({suggestion.get('progress', '-')})\n"
                        f"Komut: \"{suggestion.get('name', '')} raporuna devam et\""
                    )
                else:
                    latest = notebooks[0]
                    quick_reply = (
                        "Devam edilecek aktif not defteri bulunamadi.\n"
                        f"Son not defteri: `{latest.get('name', '')}` ({latest.get('status', '-')}, {latest.get('progress', '-')})\n"
                        f"Yeni bir gorev yazarak yeni not defteri baslatabilirsiniz."
                    )
            else:
                quick_reply = "Devam edilecek not defteri bulunamadi. Yeni bir gorev yazabilirsiniz."

            messages.append(ChatMessage(role="user", content=user_message))
            messages.append(ChatMessage(role="assistant", content=quick_reply))
            self.store.save(session_id, messages)
            return quick_reply, 1, ["notebook_list"], []

        if notebook_resume:
            nb_name, nb_status = notebook_resume
            pending = nb_status.get("pending_steps", [])
            completed = nb_status.get("completed_steps", 0)
            total = nb_status.get("total_steps", 0)
            goal = nb_status.get("goal", "")
            notebook_goal_for_research = goal  # Sonradan kullanmak icin sakla

            # Tamamlanmis notebook'larda LLM'e dusme; aninda durum ve cikti yollarini dondur.
            if is_resume_like_request and total > 0 and not pending:
                done = int(completed or 0)
                latest_outputs = self._find_latest_notebook_outputs(nb_name)
                output_lines: List[str] = []
                completion_media: List[str] = []
                if latest_outputs:
                    output_lines.append("En son uretilen dosyalar:")
                    for key in ("txt", "docx", "pdf"):
                        path = latest_outputs.get(key)
                        if path:
                            output_lines.append(f"- {key.upper()}: {path}")
                            if Path(path).exists():
                                completion_media.append(path)
                output_text = ("\n" + "\n".join(output_lines)) if output_lines else ""
                completion_reply = (
                    f"Not defteri zaten tamamlandi: `{nb_name}`\n"
                    f"Ilerleme: {done}/{max(int(total or 0), 1)} adim tamamlandi."
                    f"{output_text}"
                )
                messages.append(ChatMessage(role="user", content=user_message))
                messages.append(ChatMessage(role="assistant", content=completion_reply))
                self.store.save(session_id, messages)
                return completion_reply, 1, ["notebook_status"], completion_media

            fast_resume_reply, fast_resume_tools, fast_resume_media = self._run_fast_notebook_autopilot(
                user_message=user_message,
                notebook_name=nb_name,
                notebook_status=nb_status,
            )
            if fast_resume_reply:
                messages.append(ChatMessage(role="user", content=user_message))
                messages.append(ChatMessage(role="assistant", content=fast_resume_reply))
                self.store.save(session_id, messages)
                return fast_resume_reply, 1, fast_resume_tools, fast_resume_media
            
            if pending:
                next_step = pending[0]
                # Sistem mesaji olarak baglam ekle - COK AYRINTILI
                context_msg = (
                    f"[SISTEM NOTU] '{nb_name}' not defterine devam ediliyor.\n"
                    f"Hedef: {goal}\n"
                    f"Ilerleme: {completed}/{total} adim tamamlandi.\n"
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
        kickoff_reply, kickoff_tools, kickoff_media = self._try_auto_notebook_kickoff(user_message, notebook_resume)
        if kickoff_reply:
            messages.append(ChatMessage(role="user", content=user_message))
            messages.append(ChatMessage(role="assistant", content=kickoff_reply))
            self.store.save(session_id, messages)
            return kickoff_reply, 1, kickoff_tools, kickoff_media

        messages.append(ChatMessage(role="user", content=user_message))

        # Sub-ajan profili verilmişse sadece o subset'ten araç kullan;
        # yoksa semantic router tüm 100+ araç içinden filtreler.
        if tool_subset:
            relevant_tools = get_tools_by_names(tool_subset)
        else:
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
            if not self._is_negative_tool_mention(user_message, fast_fallback.name):
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
                    
                    # Hata kontrolu
                    if isinstance(result, dict) and result.get("error"):
                        error_msg = f"Hata: {result['error']}"
                        messages.append(ChatMessage(role="assistant", content=error_msg))
                        self.store.save(session_id, messages)
                        return error_msg, 1, [fast_fallback.name], []
                    
                    # Medya dosyalarini topla - result'taki path'i kontrol et
                    if isinstance(result, dict) and result.get("path"):
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
                    error_msg = f"Hata: {fast_fallback.name} calistirilamadi: {exc}"
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
                and preferred_call.name == "research_async"
                and not self._is_negative_tool_mention(user_message, "research_async")
                and preferred_call.name in allowed_tool_names
                and (not tool_calls or all(getattr(c, "name", "") != "research_async" for c in tool_calls))
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
        
        Bu araclar LLM'in 'dusunme' asamasini atlayarak dogrudan calistirilir.
        Sonuc aninda dondurulur (~1-2 saniye).
        """
        fast_tools = {
            # Ekran - Anlik goruntu
            "screenshot_desktop", "screenshot_webpage",
            
            # Webcam - Anlik fotograf/video
            "webcam_capture", "webcam_record_video", "list_cameras",
            
            # Ses - Kayit ve calma
            "start_audio_recording", "stop_audio_recording", 
            "play_audio", "text_to_speech",
            
            # OCR - Anlik metin okuma
            "ocr_screenshot", "ocr_image",
            
            # VS Code - Hizli acma
            "open_in_vscode", "vscode_command",
            "wait_and_accept_approval", "start_approval_watcher", "stop_approval_watcher", "approval_watcher_status",
            
            # Sistem - Bilgi sorgulama
            "get_system_info", "list_processes", "network_info", "ping_host",
            
            # Dosya - Okuma ve listeleme
            "list_directory", "read_file", "search_files",
            
            # USB - Liste goruntuleme
            "list_usb_devices",
            
            # Fare - Pozisyon sorgulama (hareket haric)
            "mouse_position",
            
            # Pencere - Liste goruntuleme
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

        # SCREENSHOT - Masaustu (en yaygin istek!)
        # NOT: "vs code", "kimicode", "codex" gibi IDE/AI keyword'leri varsa screenshot'a yonlendirme!
        _ide_keywords = {"vs code", "vscode", "visual studio", "kimicode", "kimi code", "codex", "claude code", "claudecode", "copilot"}
        _has_ide_intent = any(k in normalized for k in _ide_keywords)
        if "screenshot_desktop" in self._known_tool_names and not _has_ide_intent and any(
            k in normalized for k in ("ekran goruntusu", "screenshot", "masaustu", "desktop", "masaustu", "ekran fotograf", "ekran resmi")
        ):
            return ParsedTextToolCall(
                id=f"text_tc_{uuid.uuid4().hex[:10]}",
                name="screenshot_desktop",
                arguments={},
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

        if "research_async" in self._known_tool_names and not _has_ide_intent and any(
            k in normalized for k in ("detay", "analiz", "tum kaynak", "tum haber", "rapor", "arastir", "araştır")
        ) and any(k in normalized for k in ("haber", "news", "gundem", "savas", "iran", "israil", "dunya", "world", "piyasa", "finans")):
            args: Dict[str, Any] = {"topic": text, "max_sources": 8}
            if any(k in normalized for k in ("desktop", "masaustu")):
                args["out_path"] = "Desktop\\arastirma_raporu.txt"
            return ParsedTextToolCall(
                id=f"text_tc_{uuid.uuid4().hex[:10]}",
                name="research_async",
                arguments=args,
            )

        # EKRAN GORUNTUSU ALMA - Fallback kurallari
        # NOT: "masaustu" tek basina tetiklemez - "masaustunde X'i ac" automation, screenshot degil
        screenshot_keywords = {"ekran goruntusu", "screenshot", "anlik goruntu", "fotograf cek"}
        screenshot_actions = {"al", "cek", "gonder", "kaydet", "goster"}
        automation_overrides = {"ac", "yaz", "bul", "tikla", "git", "gir", "baslat", "calistir", "kapat"}
        
        if "screenshot_desktop" in self._known_tool_names and not _has_ide_intent and any(
            k in normalized for k in screenshot_keywords | {"desktop", "masaustu"}
        ) and any(k in normalized for k in screenshot_actions):
            # "masaustunde X'i ac" gibi ifadelerde screenshot'a degil, automasyona yonlendir
            is_desktop_only = not any(k in normalized for k in screenshot_keywords)
            has_automation_intent = any(k in normalized for k in automation_overrides)
            if not (is_desktop_only and has_automation_intent):
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

        # Kapsamli gorev algilama -> notebook_create oner
        if "notebook_create" in self._known_tool_names and any(
            k in normalized for k in ("kapsamli", "detayli", "adim adim", "parcala", "tum", "karsilastir")
        ) and any(
            k in normalized for k in ("arastir", "analiz", "rapor", "incele", "haber", "research")
        ):
            # Not defteri adi olustur
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

        # VS CODE - deterministic fallback (LLM'e dusmeden hizli calissin)
        if "open_in_vscode" in self._known_tool_names and any(
            k in normalized for k in ("vscode", "vs code", "visual studio code", "code ile")
        ) and any(k in normalized for k in ("ac", "open", "baslat", "calistir")):
            path = ".."  # Varsayilan: proje koku (data dizininin ustu)

            if any(k in normalized for k in ("masaustu", "desktop")):
                path = "desktop"

            if any(k in normalized for k in ("openworld", "proje", "project")):
                path = ".."

            quoted = re.search(r'["\'"]([^"\']{1,260})["\'"]', text)
            if quoted:
                candidate = quoted.group(1).strip()
                if candidate:
                    path = candidate

            if re.search(r"\bopenworld\b", normalized):
                path = ".."

            # AI Extension chat intent kontrolu
            _ai_ext_map = {
                "kimicode": "kimicode", "kimi code": "kimicode", "kimi": "kimicode",
                "copilot": "copilot",
                "claude code": "claudecode", "claudecode": "claudecode",
                "codex": "codex",
            }
            detected_ext = ""
            for kw, ext_name in _ai_ext_map.items():
                if kw in normalized:
                    detected_ext = ext_name
                    break

            # Chat intent: "yaz", "sor", "gonder", "mesaj" gibi kelimeler
            has_chat_intent = any(k in normalized for k in ("yaz", "sor", "gonder", "mesaj", "session", "sohbet"))

            if detected_ext and has_chat_intent and "vscode_command" in self._known_tool_names:
                # Mesaji cikar: tirnak icindeki metin veya AI extension'dan sonraki kisim
                chat_msg = ""
                # Tirnak icindeki mesaji bul
                msg_match = re.search(r"['\u2018\u2019\u201c\u201d\"](.*?)['\u2018\u2019\u201c\u201d\"]", text)
                if msg_match:
                    chat_msg = msg_match.group(1).strip()
                return ParsedTextToolCall(
                    id=f"text_tc_{uuid.uuid4().hex[:10]}",
                    name="vscode_command",
                    arguments={"path": path, "action": "chat", "extension": detected_ext, "command": chat_msg},
                )

            # Sadece VS Code ac (AI extension intent yok)
            return ParsedTextToolCall(
                id=f"text_tc_{uuid.uuid4().hex[:10]}",
                name="open_in_vscode",
                arguments={"path": path},
            )

        if "search_news" in self._known_tool_names and any(k in normalized for k in ("haber", "news", "gundem")):
            return ParsedTextToolCall(
                id=f"text_tc_{uuid.uuid4().hex[:10]}",
                name="search_news",
                arguments={"query": text},
            )
        
        # WEBCAM FOTOGRAF CEKME - Gelistirilmis pattern matching
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
            0x00C7: "c",  # C-cedilla
            0x011E: "g",  # G-breve
            0x0130: "i",  # I-with-dot
            0x00D6: "o",  # O-umlaut
            0x015E: "s",  # S-cedilla
            0x00DC: "u",  # U-umlaut
        }
        lowered = (text or "").lower().translate(turkish_map)
        normalized = unicodedata.normalize("NFKD", lowered)
        normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    @staticmethod
    def _clean_text_for_report(text: str) -> str:
        cleaned = html_lib.unescape(str(text or ""))
        cleaned = cleaned.replace("\u00a0", " ").replace("\u200b", "")

        replacements = {
            "\u00e2\u20ac\u2122": "'",
            "\u00e2\u20ac\u0153": '"',
            "\u00e2\u20ac\u009d": '"',
            "\u00e2\u20ac\u201c": "-",
            "\u00e2\u20ac\u201d": "-",
            "\u00e2\u20ac\u00a6": "...",
        }
        for bad, good in replacements.items():
            cleaned = cleaned.replace(bad, good)

        if any(marker in cleaned for marker in ("\u00c3", "\u00c5", "\u00c4", "\u00e2")):
            try:
                repaired = cleaned.encode("latin-1", errors="ignore").decode("utf-8", errors="ignore")
                if repaired:
                    cleaned = repaired
            except Exception:
                pass

        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @staticmethod
    def _truncate_text(text: str, max_chars: int = 180) -> str:
        value = str(text or "").strip()
        if len(value) <= max_chars:
            return value
        clipped = value[: max_chars + 1]
        if " " in clipped:
            clipped = clipped.rsplit(" ", 1)[0]
        return clipped.rstrip(" ,.;:") + "..."

    @staticmethod
    def _extract_session_notebook_name(messages: List[ChatMessage]) -> str:
        pattern = re.compile(
            r"Not defteri (?:olusturuldu|guncellendi|tamamlandi|zaten tamamlandi):\s*`([^`]+)`",
            flags=re.IGNORECASE,
        )
        for msg in reversed(messages):
            if msg.role != "assistant":
                continue
            content = msg.content or ""
            match = pattern.search(content)
            if match:
                return match.group(1).strip()
        return ""

    @staticmethod
    def _is_resume_like_request(user_message: str) -> bool:
        normalized = AgentService._normalize_text_for_match(user_message)
        if not normalized.strip():
            return False

        strong_phrases = (
            "devam et",
            "rapora devam",
            "raporuna devam",
            "kaldigim yerden",
            "kaldigimiz yerden",
            "sonraki adim",
            "devam edelim",
        )
        if any(phrase in normalized for phrase in strong_phrases):
            return True

        tokens = [w for w in re.findall(r"[^\W_]+", normalized, flags=re.UNICODE) if w]
        if not tokens:
            return False
        compact_resume_tokens = {"devam", "et", "tamamla", "bitir", "ilerle"}
        return len(tokens) <= 3 and all(t in compact_resume_tokens for t in tokens)

    @staticmethod
    def _is_incomplete_task_query(user_message: str) -> bool:
        normalized = AgentService._normalize_text_for_match(user_message)
        markers = (
            "yarim kalan gorev",
            "tamamlanmamis gorev",
            "acik gorev",
            "hangi gorevler var",
            "gorevlerim neler",
            "notebook listesi",
            "not defteri listesi",
            "unfinished task",
            "pending task",
        )
        return any(marker in normalized for marker in markers)

    @staticmethod
    def _is_no_action_check_request(user_message: str) -> bool:
        normalized = AgentService._normalize_text_for_match(user_message)
        no_action_markers = (
            "sadece kontrol et",
            "islem yapma",
            "islem yapmadan",
            "sadece kontrol",
            "yalnizca kontrol",
        )
        check_topics = (
            "timeout",
            "zaman asimi",
            "baglanti",
            "hata",
            "giderildi mi",
        )
        return any(m in normalized for m in no_action_markers) and any(t in normalized for t in check_topics)

    def _build_incomplete_task_reply(self) -> Tuple[str, List[str]]:
        try:
            from .tools.notebook_tools import tool_notebook_list, tool_notebook_status

            listing = tool_notebook_list()
            notebooks = listing.get("notebooks", []) if isinstance(listing, dict) else []
            if not notebooks:
                return "Kayitli bir not defteri bulunamadi.", ["notebook_list"]

            incomplete = [n for n in notebooks if n.get("status") == "Devam Ediyor"]
            if not incomplete:
                latest = notebooks[:3]
                lines = ["Su anda acik kalan gorev yok. Son not defterleri:"]
                for nb in latest:
                    lines.append(f"- {nb.get('name', '')} ({nb.get('status', '-')}, {nb.get('progress', '-')})")
                return "\n".join(lines), ["notebook_list"]

            lines = ["Yarim kalan gorevler:"]
            tools_used = ["notebook_list"]
            for nb in incomplete[:5]:
                name = str(nb.get("name", "")).strip()
                progress = str(nb.get("progress", "-")).strip()
                next_step = ""
                if name:
                    status = tool_notebook_status(name)
                    tools_used.append("notebook_status")
                    next_step = str(status.get("next_step", "")).strip()
                line = f"- {name} ({progress})"
                if next_step:
                    line += f" | Siradaki: {next_step}"
                lines.append(line)
            first_name = str(incomplete[0].get("name", "")).strip()
            if first_name:
                lines.append("")
                lines.append(f'Devam etmek isterseniz: "{first_name} raporuna devam et" yazabilirsiniz.')
            return "\n".join(lines), tools_used
        except Exception:
            return "Not defteri listesi okunurken hata olustu.", ["notebook_list"]

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
            final_outputs: Dict[str, str] = {}
            final_summary = ""
            final_errors: List[str] = []

            is_source_step = any(k in step_norm for k in ("haber", "kaynak", "gelisme", "topla", "tara"))
            is_validation_step = any(k in step_norm for k in ("dogrula", "guvenilirlik", "tarih"))
            is_impact_step = any(k in step_norm for k in ("finansal", "kuresel", "etki", "siniflandir"))
            is_draft_step = any(k in step_norm for k in ("taslak", "rapor"))
            is_final_step = any(k in step_norm for k in ("nihai", "dosya", "txt", "docx", "pdf", "cikti"))

            if is_source_step:
                query_candidates = [
                    self._derive_news_query(goal or next_step),
                    "iran amerika savas son 48 saat",
                    "iran abd finansal piyasalar etkisi",
                ]
                best_news: Dict[str, Any] = {}
                best_count = 0
                for q in query_candidates:
                    news_result = execute_tool("search_news", {"query": q, "limit": 6})
                    tools_used.append("search_news")
                    count = int(news_result.get("count", 0) or 0)
                    if count > best_count:
                        best_count = count
                        best_news = news_result
                    if count > 0:
                        break

                if best_count <= 0:
                    warning_note = "Kaynak taramasi yapildi ancak dogrulanabilir haber bulunamadi."
                    execute_tool("notebook_add_note", {"name": notebook_name, "note": warning_note})
                    tools_used.append("notebook_add_note")
                    status_after = execute_tool("notebook_status", {"name": notebook_name})
                    tools_used.append("notebook_status")
                    done = int(status_after.get("completed_steps", 0) or 0)
                    total = int(status_after.get("total_steps", 0) or 0)
                    reply = (
                        f"Not defteri guncellendi: `{notebook_name}`\n"
                        f"Ilerleme: {done}/{max(total, 1)} adim tamamlandi.\n"
                        f"Adim tamamlanmadi: {next_step}\n"
                        "Neden: 0 dogrulanabilir kaynak bulundu.\n\n"
                        "Ayni adimi yeniden denemek icin \"devam et\" yazabilirsiniz."
                    )
                    return reply, tools_used

                finding = f"{best_count} kaynak listelendi."
                titles: List[str] = []
                source_summaries: List[str] = []
                for idx, item in enumerate((best_news.get("results") or [])[:6], start=1):
                    row = item or {}
                    title = self._clean_text_for_report(str(row.get("title", "")).strip())
                    published = self._clean_text_for_report(
                        str(row.get("published_at", "") or row.get("published", "")).strip()
                    )
                    url = str(row.get("url", "")).strip()
                    if title:
                        titles.append(title)
                    pieces: List[str] = []
                    if title:
                        pieces.append(f"{idx}) {self._truncate_text(title, 170)}")
                    if published:
                        pieces.append(f"({published[:10]})")
                    if url:
                        pieces.append(url)
                    if pieces:
                        source_summaries.append(" - ".join(pieces))
                if source_summaries:
                    note_parts.append("Kaynak ozeti: " + " || ".join(source_summaries[:4]))
                if titles:
                    finding = f"{best_count} kaynak listelendi. Ilk kaynak: {titles[0]}"
                warn = str(best_news.get("error", "")).strip()
                if warn:
                    note_parts.append(f"Kaynak toplama uyari: {warn}")

            if is_validation_step and not is_source_step:
                finding = "Kaynaklar tarih ve guvenilirlik acisindan kontrol edildi."
                note_parts.append("Kaynak tarihleri ve kurum guvenilirligi capraz kontrol edildi.")

            if is_impact_step:
                finding = "Finansal ve kuresel etkiler siniflandirildi."
                note_parts.append(
                    "Etkiler enerji fiyatlari, risk primi, borsa endeksleri ve guvenli liman varliklari "
                    "basliklarinda siniflandirildi."
                )

            if is_draft_step and not is_final_step and not is_source_step:
                finding = "Rapor taslagi olusturuldu."
                note_parts.append("Taslak; ozet, kaynaklar, dogrulama ve etkiler bolumleriyle derlendi.")

            if is_final_step:
                final_outputs, final_summary, final_errors, output_tools = self._build_notebook_outputs(
                    notebook_name=notebook_name,
                    notebook_status=notebook_status,
                )
                tools_used.extend(output_tools)
                if final_summary:
                    note_parts.append(final_summary)
                if final_outputs:
                    finding = "Rapor dosyalari olusturuldu."
                elif final_errors:
                    finding = "Nihai cikti olusturma kismen basarisiz."
                    note_parts.append("Hatalar: " + " | ".join(final_errors))

            note_text = " ".join(part for part in note_parts if part).strip()
            execute_tool("notebook_add_note", {"name": notebook_name, "note": note_text})
            tools_used.append("notebook_add_note")

            complete_result = self._complete_notebook_step_best_effort(
                notebook_name=notebook_name,
                step_text=next_step,
                finding=finding,
            )
            tools_used.append("notebook_complete_step")

            if isinstance(complete_result, dict) and complete_result.get("error"):
                status_after = execute_tool("notebook_status", {"name": notebook_name})
                tools_used.append("notebook_status")
                done = int(status_after.get("completed_steps", 0) or 0)
                total = int(status_after.get("total_steps", 0) or 0)
                reply = (
                    f"Not defteri guncellendi: `{notebook_name}`\n"
                    f"Ilerleme: {done}/{max(total, 1)} adim tamamlandi.\n"
                    f"Adim kapanamadi: {next_step}\n"
                    f"Hata: {complete_result.get('error')}\n\n"
                    "Ayni adimi tekrar denemek icin \"devam et\" yazabilirsiniz."
                )
                return reply, tools_used

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
                    "Devam etmek icin \"devam et\" yazabilirsiniz."
                )
            else:
                output_lines: List[str] = []
                if final_outputs:
                    output_lines.append("Uretilen dosyalar:")
                    for key, path in final_outputs.items():
                        output_lines.append(f"- {key.upper()}: {path}")
                if final_errors:
                    output_lines.append("Uyari:")
                    for err in final_errors:
                        output_lines.append(f"- {err}")
                output_text = ("\n" + "\n".join(output_lines)) if output_lines else ""
                reply = (
                    f"Not defteri tamamlandi: `{notebook_name}`\n"
                    f"Ilerleme: {done}/{max(total, 1)} adim tamamlandi."
                    f"{output_text}"
                )
            return reply, tools_used
        except Exception as exc:
            logger = logging.getLogger(__name__)
            logger.exception("Fast notebook resume failed: %s", notebook_name)
            try:
                status_after = execute_tool("notebook_status", {"name": notebook_name})
                done = int(status_after.get("completed_steps", 0) or 0)
                total = int(status_after.get("total_steps", 0) or 0)
                upcoming = str(status_after.get("next_step", "")).strip()
                reply = (
                    f"Not defteri durumunu okuyabildim ancak adim ilerletilemedi: `{notebook_name}`\n"
                    f"Ilerleme: {done}/{max(total, 1)} adim tamamlandi.\n"
                    f"Hata: {type(exc).__name__}"
                )
                if upcoming:
                    reply += f"\nSiradaki adim: {upcoming}"
                reply += "\n\nAyni adimi yeniden denemek icin \"devam et\" yazabilirsiniz."
                return reply, ["notebook_status"]
            except Exception:
                return (
                    f"Not defteri devam islemi sirasinda hata olustu: {type(exc).__name__}. "
                    "Tekrar denemek icin \"devam et\" yazabilirsiniz."
                ), []

    def _run_fast_notebook_autopilot(
        self,
        user_message: str,
        notebook_name: str,
        notebook_status: Dict[str, Any],
        *,
        force_auto: bool = False,
    ) -> Tuple[str, List[str], List[str]]:
        normalized = self._normalize_text_for_match(user_message)
        status_only_markers = ("durum", "status", "ilerleme", "kac adim")
        if any(marker in normalized for marker in status_only_markers):
            return "", [], []

        current_status = notebook_status or {}
        pending_steps = current_status.get("pending_steps", []) or []
        if not pending_steps:
            return "", [], []

        auto_requested = force_auto or self._is_resume_like_request(user_message)
        max_steps = min(max(len(pending_steps), 1), 8) if auto_requested else 1
        deadline = time.monotonic() + (48.0 if auto_requested else 22.0)

        tools_used: List[str] = []
        completed_now: List[str] = []
        stop_reason = ""

        for _ in range(max_steps):
            if time.monotonic() >= deadline:
                stop_reason = "deadline"
                break

            current_pending = current_status.get("pending_steps", []) or []
            if not current_pending:
                break

            current_step = str(current_pending[0]).strip()
            step_reply, step_tools = self._try_fast_notebook_resume(
                user_message="devam et",
                notebook_name=notebook_name,
                notebook_status=current_status,
            )
            if not step_reply:
                break
            tools_used.extend(step_tools)
            if current_step:
                completed_now.append(current_step)

            status_after = execute_tool("notebook_status", {"name": notebook_name})
            tools_used.append("notebook_status")
            if not isinstance(status_after, dict) or status_after.get("error"):
                stop_reason = "status_error"
                break
            current_status = status_after

            if not auto_requested:
                break

        tools_used = list(dict.fromkeys(tools_used))
        done = int(current_status.get("completed_steps", 0) or 0)
        total = max(int(current_status.get("total_steps", 0) or 0), 1)
        pending_steps = current_status.get("pending_steps", []) or []

        if not pending_steps:
            outputs = self._find_latest_notebook_outputs(notebook_name)
            media_files: List[str] = []
            for key in ("pdf", "docx", "txt"):
                out_path = outputs.get(key)
                if out_path and Path(out_path).exists():
                    media_files.append(out_path)

            lines: List[str] = [
                f"Not defteri tamamlandi: `{notebook_name}`",
                f"Ilerleme: {done}/{total} adim tamamlandi.",
            ]
            if completed_now:
                lines.append("Bu turda tamamlanan adimlar:")
                for step in completed_now:
                    lines.append(f"- {step}")
            if outputs:
                lines.append("Uretilen dosyalar:")
                for key in ("txt", "docx", "pdf"):
                    out_path = outputs.get(key)
                    if out_path:
                        lines.append(f"- {key.upper()}: {out_path}")
            return "\n".join(lines), tools_used, media_files

        next_step = str(current_status.get("next_step", pending_steps[0])).strip()
        lines = [
            f"Not defteri guncellendi: `{notebook_name}`",
            f"Ilerleme: {done}/{total} adim tamamlandi.",
        ]
        if completed_now:
            lines.append("Bu turda tamamlanan adimlar:")
            for step in completed_now:
                lines.append(f"- {step}")
        if next_step:
            lines.append(f"Siradaki adim: {next_step}")

        lines.append("")
        if stop_reason == "deadline":
            lines.append("Burada zaman sinirina yaklastik; notlar kaydedildi.")
            lines.append("Devam etmemi isterseniz \"devam et\" yazabilirsiniz.")
        else:
            lines.append("Notlar kaydedildi. Devam etmemi isterseniz \"devam et\" yazabilirsiniz.")
        return "\n".join(lines), tools_used, []

    def _build_notebook_outputs(
        self,
        notebook_name: str,
        notebook_status: Dict[str, Any],
    ) -> Tuple[Dict[str, str], str, List[str], List[str]]:
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

        outputs: Dict[str, str] = {}
        errors: List[str] = []
        tools_used: List[str] = []

        goal = self._clean_text_for_report(str(notebook_status.get("goal", "")).strip()) or notebook_name
        goal_display = self._truncate_text(goal, 260)
        completed_raw = notebook_status.get("completed_list", []) or []
        notes_raw = notebook_status.get("recent_notes", []) or []
        completed = [self._clean_text_for_report(str(step)) for step in completed_raw]
        notes = [self._clean_text_for_report(str(note)) for note in notes_raw]

        source_rows: List[str] = []
        for note in notes:
            if "Kaynak ozeti:" not in note:
                continue
            _, _, tail = note.partition("Kaynak ozeti:")
            for chunk in [c.strip() for c in tail.split("||")]:
                if chunk and chunk not in source_rows:
                    source_rows.append(self._truncate_text(self._clean_text_for_report(chunk), 260))

        report_lines: List[str] = [
            f"Rapor Basligi: {goal_display}",
            "",
            "Yonetici Ozeti:",
            "Bu rapor, not defterinde toplanan acik kaynak akisina dayanarak jeopolitik gelismelerin finansal piyasa kanallarina etkisini siniflandirir.",
            "Sonuclar haber akisinin hizi nedeniyle dinamik olabilir; bu nedenle karar oncesinde tarihler ve birincil kaynak linkleri tekrar dogrulanmalidir.",
            "",
            "1) Kapsam ve Metodoloji",
            f"- Gorev tanimi: {goal_display}",
            "- Yontem: adim adim notebook akisi, kaynak taramasi, tarih-guvenilirlik kontrolu, etki siniflandirma, taslak ve nihai cikti.",
            "- Sinir: Sadece eldeki acik kaynak ve notlara dayali degerlendirme yapilmistir.",
            "",
            "2) Tamamlanan Is Akisi",
        ]
        for idx, step in enumerate(completed, start=1):
            report_lines.append(f"{idx}. {step}")

        report_lines.extend(
            [
                "",
                "3) Kaynak Ozetleri",
            ]
        )
        if source_rows:
            for row in source_rows[:12]:
                report_lines.append(f"- {row}")
        else:
            report_lines.append("- Kaynak ozeti notu bulunamadi; manuel kaynak eklemesi onerilir.")

        title_blob = " ".join(source_rows).lower()
        signal_lines: List[str] = []
        if any(k in title_blob for k in ("petrol", "enerji", "hormuz", "bogaz", "gaz", "arz")):
            signal_lines.append("- Enerji akisi ve lojistik hatlara dair haber yogunlugu yuksek; fiyat oynakligi kanali guclu.")
        if any(k in title_blob for k in ("ateskes", "muzakere", "diplomasi", "gorusme", "anlasma")):
            signal_lines.append("- Diplomasi/ateskes basliklari kisa vadede risk primini yumusatabilecek bir kanal olusturuyor.")
        if any(k in title_blob for k in ("saldiri", "misilleme", "fuze", "catisma", "gerilim")):
            signal_lines.append("- Askeri gerilim basliklari riskten kacis davranisini ve guvenli liman talebini destekleyebilir.")
        if not signal_lines:
            signal_lines.append("- Baslik akisi heterojen; net yonlu fiyatlama yerine yuksek frekansli dalgalanma riski one cikiyor.")

        report_lines.extend(["", "3b) Basliklardan One Cikan Sinyaller"])
        report_lines.extend(signal_lines)

        report_lines.extend(
            [
                "",
                "4) Finansal Etki Cercevesi",
                "- Enerji/Petrol: Arz-endiseleri ve tasima riskleri Brent/WTI oynakligini yukseltebilir.",
                "- Hisse Senetleri: Jeopolitik risk artisi savunma/enerji hisselerini desteklerken genis endekslerde riskten kacis gorulebilir.",
                "- Tahvil/FX: Guvenli liman talebi ABD tahvili, altin ve rezerv para birimlerine yonelebilir; gelisen ulke varliklarinda spread artisi gorulebilir.",
                "- Emtia ve Tasima: Sigorta, navlun ve lojistik maliyetlerindeki artis enflasyon geciskenligini guclendirebilir.",
                "",
                "5) Kisa Vade Senaryo Seti (24-72 saat)",
                "- Temel Senaryo: Catisma alan olarak sinirli kalir; piyasalarda yuksek ama yonlu olmayan oynaklik surer.",
                "- Riskli Senaryo: Cografi/genisleme ve kritik altyapi riski artisiyla enerji ve guvenli liman varliklarinda sert hareketler gorulur.",
                "- Olumlu Senaryo: Diplomatik yumusama ve ateskes sinyaliyle risk primi geri cekilir.",
                "",
                "6) Izlenecek Gostergeler",
                "- Resmi aciklamalarin tarih/saat sirasi ve teyitli kaynak zinciri",
                "- Enerji akislari: Bogazlar, boru hatlari, rafineri haberleri",
                "- VIX/volatilite, CDS spreadleri, tahvil getirileri, altin ve petrol korelasyonu",
                "",
                "7) Son Notlar",
            ]
        )
        if notes:
            for note in notes[-10:]:
                report_lines.append(f"- {self._truncate_text(note, 220)}")
        else:
            report_lines.append("- Not bulunamadi.")

        report_lines.extend(
            [
                "",
                "Sonuc:",
                "Not defteri adimlari tamamlanmis ve dokuman ciktilari uretilmistir. Nihai kullanim oncesinde kritik bulgularin birincil kaynaklardan tekrar teyidi onerilir.",
            ]
        )
        content = "\n".join(report_lines)

        from datetime import datetime
        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        reports_dir = settings.workspace_path / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        base = f"{notebook_name}_{stamp}"
        txt_path = str((reports_dir / f"{base}.txt").resolve())
        docx_path = str((reports_dir / f"{base}.docx").resolve())
        pdf_path = str((reports_dir / f"{base}.pdf").resolve())

        def _run_tool(name: str, args: Dict[str, Any], timeout_sec: float) -> Dict[str, Any]:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(execute_tool, name, args)
                try:
                    result = future.result(timeout=timeout_sec)
                    if isinstance(result, dict):
                        return result
                    return {"error": f"{name} beklenmeyen sonuc dondurdu."}
                except FuturesTimeoutError:
                    return {"error": f"{name} zaman asimi ({int(timeout_sec)}sn)."}
                except Exception as exc:
                    return {"error": str(exc)}

        txt_result = _run_tool("write_file", {"path": txt_path, "content": content}, 12.0)
        tools_used.append("write_file")
        if isinstance(txt_result, dict) and txt_result.get("error"):
            errors.append(f"TXT olusturulamadi: {txt_result.get('error')}")
        else:
            outputs["txt"] = txt_path

        docx_result = _run_tool(
            "create_docx",
            {"output_path": docx_path, "title": goal[:120], "paragraphs": content.split("\n")},
            25.0,
        )
        tools_used.append("create_docx")
        if isinstance(docx_result, dict) and docx_result.get("error"):
            fallback_docx_result = _run_tool(
                "create_docx",
                {
                    "output_path": docx_path,
                    "title": goal[:120],
                    "paragraphs": [line for line in content.split("\n") if line.strip()][:120],
                },
                20.0,
            )
            if isinstance(fallback_docx_result, dict) and fallback_docx_result.get("error"):
                errors.append(f"DOCX olusturulamadi: {fallback_docx_result.get('error')}")
            else:
                outputs["docx"] = str(fallback_docx_result.get("path", docx_path))
        else:
            outputs["docx"] = str(docx_result.get("path", docx_path))

        pdf_result = _run_tool("create_pdf", {"output_path": pdf_path, "title": goal[:120], "content": content}, 25.0)
        tools_used.append("create_pdf")
        if isinstance(pdf_result, dict) and pdf_result.get("error"):
            fallback_pdf_result = _run_tool(
                "create_pdf",
                {"output_path": pdf_path, "title": goal[:120], "content": content[:5000]},
                20.0,
            )
            if isinstance(fallback_pdf_result, dict) and fallback_pdf_result.get("error"):
                errors.append(f"PDF olusturulamadi: {fallback_pdf_result.get('error')}")
            else:
                outputs["pdf"] = str(fallback_pdf_result.get("path", pdf_path))
        else:
            outputs["pdf"] = str(pdf_result.get("path", pdf_path))

        summary = "Nihai cikti olusturma asamasi tamamlandi."
        return outputs, summary, errors, tools_used

    @staticmethod
    def _find_latest_notebook_outputs(notebook_name: str) -> Dict[str, str]:
        reports_dir = settings.workspace_path / "reports"
        if not reports_dir.exists():
            return {}

        latest: Dict[str, Tuple[float, str]] = {}
        for ext in ("txt", "docx", "pdf"):
            pattern = f"{notebook_name}_*.{ext}"
            for path in reports_dir.glob(pattern):
                try:
                    mtime = path.stat().st_mtime
                except Exception:
                    continue
                previous = latest.get(ext)
                candidate = str(path.resolve())
                if previous is None or mtime > previous[0]:
                    latest[ext] = (mtime, candidate)
        return {ext: value for ext, (_, value) in latest.items()}

    def _complete_notebook_step_best_effort(self, notebook_name: str, step_text: str, finding: str) -> Dict[str, Any]:
        candidates: List[str] = []
        raw = (step_text or "").strip()
        if raw:
            candidates.append(raw)
            candidates.append(raw.replace("(", " ").replace(")", " ").replace("/", " "))
            candidates.append(raw.replace("-", " "))
            candidates.append(self._step_keyword(raw))
            words = [w for w in re.findall(r"[^\W_]+", raw, flags=re.UNICODE) if len(w) > 1]
            if len(words) >= 2:
                candidates.append(" ".join(words[:2]))
            if words:
                candidates.append(words[0])

        seen: set[str] = set()
        for candidate in candidates:
            key = candidate.strip()
            if not key:
                continue
            normalized = self._normalize_text_for_match(key)
            if normalized in seen:
                continue
            seen.add(normalized)
            result = execute_tool(
                "notebook_complete_step",
                {"name": notebook_name, "step_keyword": key, "finding": finding},
            )
            if isinstance(result, dict) and not result.get("error"):
                return result
        return {"error": f"Adim anahtar kelimesi eslesmedi: {step_text}"}

    @staticmethod
    def _derive_news_query(goal: str) -> str:
        words = re.findall(r"[^\W_]+", goal, flags=re.UNICODE)
        filtered = [w for w in words if len(w) > 2][:8]
        if not filtered:
            return "dunya gundem"
        return " ".join(filtered)
    def _try_auto_notebook_kickoff(
        self,
        user_message: str,
        notebook_resume: Optional[Tuple[str, Dict[str, Any]]],
    ) -> Tuple[str, List[str], List[str]]:
        # Hardcoded auto-pilot is disabled to allow the LLM to use the
        # new asynchronous `tool_research_async`.
        return "", [], []

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
                return "", [], []

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
            return "", [], []

        total = int(status_result.get("total_steps", len(steps)) or len(steps))
        done = int(status_result.get("completed_steps", 1) or 1)
        next_step = status_result.get("next_step", "Kaynak toplama")

        if isinstance(complete_result, dict) and complete_result.get("error"):
            # Adim anahtar kelimesi eslesmediyse fallback: ilerlemeyi yansitmadan devam mesaji ver.
            done = max(done, 0)

        auto_reply, auto_tools, auto_media = self._run_fast_notebook_autopilot(
            user_message="devam et",
            notebook_name=notebook_name,
            notebook_status=status_result if isinstance(status_result, dict) else {},
            force_auto=True,
        )
        if auto_reply:
            tools_used.extend(auto_tools)
            tools_used = list(dict.fromkeys(tools_used))
            reply = (
                f"Not defteri olusturuldu: `{notebook_name}`\n"
                "Kickoff adimi tamamlandi ve otomatik ilerleme baslatildi.\n\n"
                f"{auto_reply}"
            )
            return reply, tools_used, auto_media

        reply = (
            f"Not defteri olusturuldu: `{notebook_name}`\n"
            f"Ilerleme: {done}/{max(total, 1)} adim tamamlandi.\n"
            f"Siradaki adim: {next_step}\n\n"
            f"Devam etmek icin: \"{notebook_name} raporuna devam et\" yazabilirsiniz."
        )
        return reply, tools_used, []

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
        words = re.findall(r"[^\W_]+", goal, flags=re.UNICODE)
        keep = [w for w in words if len(w) > 2][:4]
        base = "_".join(keep) if keep else "Arastirma_Notu"
        safe = re.sub(r"[^A-Za-z0-9_]+", "_", AgentService._normalize_text_for_match(base))
        safe = re.sub(r"_+", "_", safe).strip("_")
        return (safe or "arastirma_notu")[:60]

    @staticmethod
    def _step_keyword(step_text: str) -> str:
        words = re.findall(r"[^\W_]+", step_text, flags=re.UNICODE)
        key = " ".join(words[:4]).strip()
        return key or step_text[:24]

    @staticmethod
    def _build_tool_summary(step_results: List[Tuple[str, Dict[str, Any]]]) -> str:
        if not step_results:
            return "Islem tamamlandi."

        async_started = None
        for name, result in step_results:
            if name == "research_async" and isinstance(result, dict) and result.get("status") == "started":
                async_started = result
                break

        if async_started is not None:
            lines = [
                "Araştırmayı başlattım. Arka planda çalışıyor.",
                "Bitince özet ve PDF raporu buradan göndereceğim.",
            ]
            notebook = str(async_started.get("notebook") or "").strip()
            if notebook:
                lines.append(f"Not defteri: `{notebook}`")
            message = str(async_started.get("message") or "").strip()
            if message:
                lines.append(message)

            errors: List[str] = []
            for name, result in step_results:
                if not isinstance(result, dict):
                    continue
                err = result.get("error")
                if err:
                    errors.append(f"- `{name}`: {err}")
            if errors:
                lines.append("")
                lines.append("Uyarı/Hata notları:")
                lines.extend(errors[:3])
            return "\n".join(lines)

        lines = ["İşlem tamamlandı. Sonuçlar:"]
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

        message = result.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()[:240]

        for key in ("path", "output_path", "file_path", "opened", "url"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return f"tamamlandi ({key}: {value})"

        status = result.get("status")
        if isinstance(status, str) and status.strip():
            status_text = status.strip().lower()
            if status_text == "started":
                return "arka planda başlatıldı"
            return status.strip()

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
            "vscode",
            "vs code",
            "code",
            "openworld",
            "proje",
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

    @staticmethod
    def _detect_vscode_agent_targets(normalized: str) -> List[str]:
        targets: List[str] = []
        if re.search(r"\b(?:kimicode|kimi\s*code)\b", normalized):
            targets.append("kimicode")
        if re.search(r"\bcodex\b", normalized):
            targets.append("codex")
        if re.search(r"\b(?:claudecode|claude\s*code)\b", normalized):
            targets.append("claudecode")
        return list(dict.fromkeys(targets))

    @staticmethod
    def _vscode_extension_roots() -> List[Path]:
        home = Path.home()
        return [
            home / ".vscode" / "extensions",
            home / ".vscode-insiders" / "extensions",
        ]

    def _is_vscode_extension_installed(self, prefixes: List[str], cache_key: str) -> bool:
        if cache_key in self._vscode_extension_presence_cache:
            return self._vscode_extension_presence_cache[cache_key]

        lowered_prefixes = tuple((p or "").strip().lower() for p in prefixes if p)
        if not lowered_prefixes:
            self._vscode_extension_presence_cache[cache_key] = False
            return False

        found = False
        for root in self._vscode_extension_roots():
            if not root.exists():
                continue
            try:
                for child in root.iterdir():
                    if not child.is_dir():
                        continue
                    name = child.name.lower()
                    if any(name.startswith(prefix) for prefix in lowered_prefixes):
                        found = True
                        break
            except Exception:
                continue
            if found:
                break

        self._vscode_extension_presence_cache[cache_key] = found
        return found

    @staticmethod
    def _extract_vscode_agent_write_request(user_message: str) -> Optional[Dict[str, Any]]:
        normalized = AgentService._normalize_text_for_match(user_message)
        targets = AgentService._detect_vscode_agent_targets(normalized)

        has_vscode_hint = any(
            k in normalized for k in ("vscode", "vs code", "visual studio code", "code ile")
        ) or bool(targets)
        has_open_intent = any(k in normalized for k in ("ac", "open", "baslat", "calistir"))
        has_write_intent = any(k in normalized for k in ("yaz", "gonder", "sor", "de")) or ('"' in user_message)

        # Session/oturum kelimesi zorunlu degil; kullanici dogrudan "X'e sunu yaz" diyebilir.
        if not has_vscode_hint or not has_open_intent:
            return None
        if not has_write_intent:
            return None
        if not targets:
            return None
        if len(targets) > 1:
            return {"error": "ambiguous_target", "targets": targets}

        target = targets[0]

        path = ".."
        if any(k in normalized for k in ("masaustu", "desktop")):
            path = "desktop"
        if any(k in normalized for k in ("openworld", "proje", "project")):
            path = ".."

        write_markers = (
            r"(?is)(?:sunu|su metni|mesaji|promptu)\s+yaz\s*[:\-]?\s*(.+)$",
            r"(?is)ona\s+sunu\s+yaz\s*[:\-]?\s*(.+)$",
            r"(?is)metin\s*[:\-]\s*(.+)$",
        )

        prompt_text = ""
        for pattern in write_markers:
            m = re.search(pattern, user_message, flags=re.IGNORECASE)
            if m:
                prompt_text = m.group(1).strip()
                break

        quoted = re.findall(r'"([^"]{4,4000})"', user_message, flags=re.DOTALL)
        if quoted:
            candidate = max(quoted, key=len).strip()
            if len(candidate) >= len(prompt_text):
                prompt_text = candidate

        prompt_text = prompt_text.strip().strip("'").strip('"').strip()
        if not prompt_text:
            return None

        return {"target": target, "path": path, "prompt": prompt_text}

    @staticmethod
    def _is_ide_approval_help_request(user_message: str) -> bool:
        normalized = AgentService._normalize_text_for_match(user_message)
        ide_markers = ("vscode", "vs code", "visual studio code", "kimicode", "kimi code", "codex", "claude code", "claudecode")
        approval_markers = ("onay", "kabul", "izin", "approve", "allow", "accept", "authorize")
        action_markers = ("ver", "et", "click", "tikla", "kabul et", "onayla", "izin ver")
        return any(k in normalized for k in ide_markers) and any(k in normalized for k in approval_markers) and any(k in normalized for k in action_markers)

    @staticmethod
    def _infer_approval_profile_from_text(user_message: str) -> str:
        normalized = AgentService._normalize_text_for_match(user_message)
        if "claudecode" in normalized or "claude code" in normalized:
            return "claudecode"
        if "codex" in normalized:
            return "codex"
        if "kimicode" in normalized or "kimi code" in normalized:
            return "kimicode"
        if "gemini" in normalized:
            return "gemini"
        return "generic"

    @staticmethod
    def _watch_and_accept_ide_prompt(
        timeout: int = 25,
        allow_keyboard_fallback: bool = False,
        profile: str = "generic",
    ) -> Dict[str, Any]:
        try:
            from .tools.super_agent import tool_wait_and_accept_approval
        except Exception as exc:
            return {"error": str(exc)}

        try:
            return tool_wait_and_accept_approval(
                window_pattern="Visual Studio Code|Code - Insiders",
                timeout=max(5, min(int(timeout), 90)),
                interval=0.8,
                min_confidence=30.0,
                lang="tur+eng",
                allow_keyboard_fallback=bool(allow_keyboard_fallback),
                profile=AgentService._normalize_text_for_match(profile or "generic") or "generic",
            )
        except Exception as exc:
            return {"error": str(exc)}

    def _try_fast_ide_approval_unblock(self, user_message: str) -> Tuple[str, List[str]]:
        if not self._is_ide_approval_help_request(user_message):
            return "", []

        result = self._watch_and_accept_ide_prompt(
            timeout=35,
            allow_keyboard_fallback=True,
            profile=self._infer_approval_profile_from_text(user_message),
        )
        if result.get("error"):
            return f"Hata: IDE onay kontrolu basarisiz: {result['error']}", []
        if result.get("success"):
            return (
                "Onay penceresi bulundu ve kabul edildi. Islem devam edebilir.",
                ["wait_and_accept_approval"],
            )
        return (
            "Su an gorunen bir IDE onay penceresi tespit edilemedi. "
            "Isterseniz tekrar denemem icin \"vscode onay penceresini kabul et\" yazin.",
            ["wait_and_accept_approval"],
        )

    @staticmethod
    def _extract_approval_watcher_action(user_message: str) -> str:
        normalized = AgentService._normalize_text_for_match(user_message)
        if not normalized:
            return ""

        stop_markers = ("kapat", "durdur", "devre disi", "iptal", "stop", "disable", "birak")
        status_markers = ("durum", "acik mi", "calisiyor mu", "status", "ne durumda")
        start_markers = ("ac", "baslat", "aktif et", "etkinlestir", "enable", "start", "devam et")

        # Daha dogal ifadeler: "izlemeyi durdur", "kontrolu birak", "takibi kapat" vb.
        generic_watch_markers = (
            "izle", "izleme", "izlemeyi", "izleyici",
            "watcher",
            "takip", "takibi",
            "kontrol", "kontrolu",
        )
        if any(marker in normalized for marker in stop_markers) and any(marker in normalized for marker in generic_watch_markers):
            return "stop"
        if any(marker in normalized for marker in status_markers) and any(marker in normalized for marker in generic_watch_markers):
            return "status"
        if any(marker in normalized for marker in start_markers) and any(marker in normalized for marker in generic_watch_markers):
            return "start"

        watcher_markers = (
            "onay izle", "onay izleme", "onay izleyici", "onay watcher",
            "otomatik onay", "onaylari otomatik", "approval watcher", "approval watch",
        )
        if not any(marker in normalized for marker in watcher_markers):
            return ""

        if any(marker in normalized for marker in stop_markers):
            return "stop"
        if any(marker in normalized for marker in status_markers):
            return "status"
        if any(marker in normalized for marker in start_markers):
            return "start"
        return "status"

    @staticmethod
    def _classify_watcher_confirmation_answer(user_message: str) -> str:
        normalized = AgentService._normalize_text_for_match(user_message)
        words = [w for w in re.findall(r"[^\W_]+", normalized, flags=re.UNICODE) if w]
        if not words or len(words) > 5:
            return ""

        joined = " ".join(words)
        yes_phrases = {
            "evet", "olur", "tamam", "ac", "baslat", "aktif et", "etkinlestir",
            "acabilirsin", "onayliyorum",
            "devam et", "izlemeye devam et", "izleyici devam etsin",
            "acik birak", "acik birak lutfen", "acik kalsin",
        }
        no_phrases = {
            "hayir", "gerek yok", "acma", "kapat", "durdur", "istemiyorum", "iptal", "olmasin",
            "izlemeyi kapat", "izleyiciyi kapat",
        }
        if joined in yes_phrases:
            return "yes"
        if joined in no_phrases:
            return "no"

        yes_tokens = {
            "evet", "olur", "tamam", "ac", "baslat", "aktif", "et", "etkinlestir", "lutfen",
            "devam", "izlemeye", "izleyici", "acik", "birak", "kalsin",
        }
        no_tokens = {
            "hayir", "gerek", "yok", "acma", "kapat", "durdur", "istemiyorum", "iptal", "olmasin", "lutfen",
            "izlemeyi", "izleyiciyi",
        }
        if all(w in yes_tokens for w in words):
            return "yes"
        if all(w in no_tokens for w in words):
            return "no"
        return ""

    @staticmethod
    def _watcher_profile_for_target(target: str) -> str:
        key = AgentService._normalize_text_for_match(target or "")
        if key in {"claudecode", "codex", "kimicode", "gemini"}:
            return key
        return "generic"

    def _set_pending_watcher_confirmation(self, session_id: str, profile: str = "generic") -> None:
        self._pending_watcher_confirmation[session_id] = {
            "created_at": time.time(),
            "kind": "watcher_confirmation",
            "profile": self._watcher_profile_for_target(profile),
        }

    def _try_handle_pending_watcher_confirmation(self, session_id: str, user_message: str) -> Tuple[str, List[str], bool]:
        pending = self._pending_watcher_confirmation.get(session_id)
        if not pending:
            return "", [], False

        decision = self._classify_watcher_confirmation_answer(user_message)
        if not decision:
            # Kullanici baska bir komuta gecti; bekleyen soruyu dusur.
            self._pending_watcher_confirmation.pop(session_id, None)
            return "", [], False

        self._pending_watcher_confirmation.pop(session_id, None)
        if decision == "yes":
            profile = str(pending.get("profile", "generic") or "generic")
            reply, tools = self._run_approval_watcher_action("start", profile=profile)
            return reply, tools, True

        reply, tools = self._run_approval_watcher_action("stop")
        return reply, tools, True

    def _try_handle_completion_prompt_answer(self, user_message: str) -> Tuple[str, List[str], bool]:
        required_tools = {"approval_watcher_status", "stop_approval_watcher", "ack_approval_completion_prompt"}
        if not required_tools.issubset(self._known_tool_names):
            return "", [], False

        try:
            status = execute_tool("approval_watcher_status", {})
        except Exception:
            return "", [], False

        if not isinstance(status, dict):
            return "", [], False
        if not bool(status.get("running")):
            return "", [], False
        if not bool(status.get("completion_prompt_sent")):
            return "", [], False

        decision = self._classify_watcher_confirmation_answer(user_message)
        if not decision:
            return (
                "Onay izleyici, IDE gorevinin tamamlandigini algiladi. "
                "Izleyiciyi kapatayim mi? (evet/hayir)",
                ["approval_watcher_status"],
                True,
            )

        if decision == "yes":
            reply, tools = self._run_approval_watcher_action("stop")
            return f"Tamam. {reply}", tools, True

        try:
            execute_tool("ack_approval_completion_prompt", {"keep_running": True})
        except Exception:
            pass
        return "Tamam. Onay izleyici acik birakildi.", ["approval_watcher_status", "ack_approval_completion_prompt"], True

    def _try_fast_approval_watcher_control(self, user_message: str) -> Tuple[str, List[str]]:
        action = self._extract_approval_watcher_action(user_message)
        if not action:
            return "", []
        profile = self._infer_approval_profile_from_text(user_message)
        return self._run_approval_watcher_action(action, profile=profile)

    def _run_approval_watcher_action(self, action: str, profile: str = "generic") -> Tuple[str, List[str]]:
        action = (action or "").strip().lower() or "status"
        profile = self._watcher_profile_for_target(profile)

        required_tools = {"start_approval_watcher", "stop_approval_watcher", "approval_watcher_status"}
        if not required_tools.issubset(self._known_tool_names):
            return "Onay izleyici araclari su an aktif degil.", []

        tool_map = {
            "start": "start_approval_watcher",
            "stop": "stop_approval_watcher",
            "status": "approval_watcher_status",
        }
        tool_name = tool_map.get(action, "approval_watcher_status")
        try:
            params: Dict[str, Any] = {}
            if action == "start":
                params["profile"] = profile
            result = execute_tool(tool_name, params)
        except Exception as exc:
            return f"Hata: onay izleyici islemi basarisiz: {exc}", [tool_name]

        if isinstance(result, dict) and result.get("error"):
            error = str(result.get("error", "")).strip()
            detail = str(result.get("detail", "")).strip()
            install_path = str(result.get("install_path", "")).strip()
            install_url = str(result.get("install_url", "")).strip()
            lines = [f"Hata: {error or 'Onay izleyici baslatilamadi.'}"]
            if detail:
                lines.append(f"Detay: {detail}")
            if install_path:
                lines.append(f"Kurulum yolu: {install_path}")
            if install_url:
                lines.append(f"Indirme: {install_url}")
            return "\n".join(lines), [tool_name]

        if action == "start":
            profile_note = ""
            if isinstance(result, dict):
                active_profile = str(result.get("profile", profile)).strip() or profile
                profile_note = f" Profil: {active_profile}."
            return (
                "Onay izleyici acildi. VS Code acik oldugu surece onay pencerelerini otomatik takip edip kabul etmeye calisacagim."
                + profile_note,
                [tool_name],
            )
        if action == "stop":
            return "Onay izleyici kapatildi.", [tool_name]

        running = bool(result.get("running")) if isinstance(result, dict) else False
        checks = int(result.get("checks", 0)) if isinstance(result, dict) else 0
        accepted = int(result.get("accepted", 0)) if isinstance(result, dict) else 0
        last_event = str(result.get("last_event", "")).strip() if isinstance(result, dict) else ""
        completion_prompt_sent = bool(result.get("completion_prompt_sent")) if isinstance(result, dict) else False
        last_notification_at = str(result.get("last_notification_at", "")).strip() if isinstance(result, dict) else ""
        notification_error = str(result.get("notification_error", "")).strip() if isinstance(result, dict) else ""
        status_text = "acik" if running else "kapali"
        parts = [f"Onay izleyici durumu: {status_text}.", f"Kontrol: {checks}", f"kabul edilen onay: {accepted}"]
        if last_event:
            parts.append(f"son olay: {last_event}")
        if completion_prompt_sent:
            parts.append("tamamlanma bildirimi bekliyor")
        if last_notification_at:
            parts.append(f"son bildirim: {last_notification_at}")
        if notification_error:
            parts.append(f"bildirim hatasi: {notification_error}")
        return " | ".join(parts), [tool_name]

    def _try_fast_vscode_agent_chat_write(self, session_id: str, user_message: str) -> Tuple[str, List[str]]:
        request = self._extract_vscode_agent_write_request(user_message)
        if not request:
            return "", []

        if request.get("error") == "ambiguous_target":
            targets = request.get("targets", [])
            options = ", ".join(str(t) for t in targets) if targets else "kimicode/codex/claudecode"
            return (
                f"Hedef asistan belirsiz ({options}). Lutfen sadece birini secin ve tekrar yazin.",
                [],
            )

        required_tools = {"open_in_vscode", "activate_window", "hotkey", "type_text", "press_key"}
        if not required_tools.issubset(self._known_tool_names):
            return (
                "Bu islem icin gereken otomasyon araclari eksik: "
                "open_in_vscode, activate_window, hotkey, type_text, press_key."
            ), []

        target = str(request["target"])
        path = str(request["path"])
        prompt = str(request["prompt"])
        tools_used: List[str] = []

        target_extensions = {
            "kimicode": ["moonshot-ai.kimi-code-"],
            "codex": ["openai.chatgpt-"],
            "claudecode": ["anthropic.claude-code-", "andrepimenta.claude-code-chat-"],
        }
        extension_ok = self._is_vscode_extension_installed(
            target_extensions.get(target, []),
            cache_key=f"ext:{target}",
        )
        if not extension_ok:
            return (
                f"Hata: `{target}` icin VS Code eklentisi bulunamadi. "
                "Yanlis komut acilip web/Copilot'a kaymamak icin otomasyon durduruldu."
            ), []

        target_command_sequences = {
            "kimicode": [
                "Kimi Code: Open in Side Panel",
                "Kimi Code: New Conversation",
                "Kimi Code: Focus Input",
            ],
            "codex": [
                "New Codex Agent",
            ],
            "claudecode": [
                "Claude Code: Open in Side Bar",
                "Claude Code: New Conversation",
                "Claude Code: Focus input",
            ],
        }
        command_sequence = target_command_sequences.get(target, [])
        if not command_sequence:
            return f"Hata: `{target}` icin komut akisi tanimli degil.", []

        def _run_gui_tool(name: str, args: Dict[str, Any], *, require_success: bool = True) -> Dict[str, Any]:
            result = execute_tool(name, args)
            if name not in tools_used:
                tools_used.append(name)
            if isinstance(result, dict):
                if result.get("error"):
                    raise RuntimeError(str(result.get("error")))
                if require_success and "success" in result and result.get("success") is False:
                    raise RuntimeError(f"{name} basarisiz")
            return result if isinstance(result, dict) else {}

        try:
            _run_gui_tool("open_in_vscode", {"path": path})
            time.sleep(0.9)

            _run_gui_tool(
                "activate_window",
                {"title_pattern": "Visual Studio Code|Code - Insiders"},
                require_success=True,
            )
            time.sleep(0.2)

            _run_gui_tool("press_key", {"key": "esc"}, require_success=False)
            time.sleep(0.08)

            for command_text in command_sequence:
                _run_gui_tool("hotkey", {"keys_list": ["ctrl", "shift", "p"]})
                time.sleep(0.22)
                _run_gui_tool("type_text", {"text": command_text, "interval": 0.004})
                _run_gui_tool("press_key", {"key": "enter"})
                time.sleep(0.45)

            safe_prompt = prompt[:3500]
            _run_gui_tool("type_text", {"text": safe_prompt, "interval": 0.0035})
            _run_gui_tool("press_key", {"key": "enter"})
        except RuntimeError as exc:
            self._pending_watcher_confirmation.pop(session_id, None)
            return f"Hata: {exc}", list(dict.fromkeys(tools_used))

        tools_used = list(dict.fromkeys(tools_used))
        watcher_profile = self._watcher_profile_for_target(target)
        self._set_pending_watcher_confirmation(session_id, profile=watcher_profile)
        reply = f"Islem tamamlandi: VS Code acildi, {target} icin yeni session komutu gonderildi ve mesaj yazildi."
        reply += "\nBu gorevde IDE onaylarini otomatik izleyip onaylamami ister misiniz (evet/hayir)"
        return (reply, tools_used)

    async def _handle_audio_recording_fast(self, session_id: str, messages: List[ChatMessage], user_message: str) -> Tuple[str, int, List[str], List[str]]:
        """Ses kaydi icin fast mode handler - start, bekle, stop yapar."""
        import logging
        import asyncio
        import re
        logger = logging.getLogger(__name__)
        
        # Kullanicidan sure al (varsayilan 5 saniye)
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
            # 1. Kaydi baslat
            from .tools.registry import execute_tool
            start_result = execute_tool("start_audio_recording", {})
            logger.info(f"[AUDIO FAST] Start result: {start_result}")
            
            if isinstance(start_result, dict) and start_result.get("error"):
                error_msg = f"Hata: Ses kaydi baslatilamadi: {start_result['error']}"
                messages.append(ChatMessage(role="assistant", content=error_msg))
                self.store.save(session_id, messages)
                return error_msg, 1, ["start_audio_recording"], []
            
            # 2. Kullaniciya bilgi ver
            info_msg = f"Ses kaydi basladi ({duration} saniye)..."
            messages.append(ChatMessage(role="assistant", content=info_msg))
            self.store.save(session_id, messages)
            
            # 3. Bekle
            await asyncio.sleep(duration)
            
            # 4. Kaydi durdur
            stop_result = execute_tool("stop_audio_recording", {})
            logger.info(f"[AUDIO FAST] Stop result: {stop_result}")
            
            # 5. Hata kontrolu
            if isinstance(stop_result, dict) and stop_result.get("error"):
                error_msg = f"Hata: Ses kaydi kaydedilemedi: {stop_result['error']}"
                messages.append(ChatMessage(role="assistant", content=error_msg))
                self.store.save(session_id, messages)
                return error_msg, 1, ["start_audio_recording", "stop_audio_recording"], []
            
            # 6. Medya dosyasini topla
            media_files: List[str] = []
            self._collect_media(stop_result, media_files)
            
            # 7. Basari mesaji
            success_msg = self._build_success_message("stop_audio_recording", stop_result)
            messages.append(ChatMessage(role="assistant", content=success_msg))
            self.store.save(session_id, messages)
            
            logger.info(f"[AUDIO FAST] Success! Media: {media_files}")
            return success_msg, 2, ["start_audio_recording", "stop_audio_recording"], media_files
            
        except Exception as exc:
            logger.error(f"[AUDIO FAST] Exception: {exc}")
            error_msg = f"Hata: Ses kaydi hatasi: {exc}"
            messages.append(ChatMessage(role="assistant", content=error_msg))
            self.store.save(session_id, messages)
            return error_msg, 1, ["start_audio_recording"], []

    @staticmethod
    def _build_success_message(tool_name: str, result: Dict[str, Any]) -> str:
        """Basari mesaji olustur."""
        success_msg = f"Islem tamamlandi: `{tool_name}`"
        
        if isinstance(result, dict):
            if "path" in result:
                success_msg += f"\nDosya: {result['path']}"
            if "resolution" in result:
                success_msg += f"\nCozunurluk: {result['resolution']}"
            if "size" in result:
                size = result['size']
                if isinstance(size, int):
                    if size > 1024 * 1024:
                        success_msg += f"\nBoyut: {size / (1024 * 1024):.2f} MB"
                    elif size > 1024:
                        success_msg += f"\nBoyut: {size / 1024:.2f} KB"
                    else:
                        success_msg += f"\nBoyut: {size} bytes"
            if "duration" in result:
                success_msg += f"\nSure: {result['duration']} sn"
            if "text" in result and len(result['text']) < 100:
                success_msg += f"\nMetin: {result['text']}"
        
        return success_msg
