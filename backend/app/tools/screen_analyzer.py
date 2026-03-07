"""
screen_analyzer.py - LLM-powered ekran analizi motoru.

Approval watcher thread'inden senkron olarak Ollama'ya OCR metni gonderir,
ekran durumunu analiz ettirir. Throttle/cache mekanizmasi icerir.

Kullanim (background thread'den):
    from .screen_analyzer import analyze_screen
    result = analyze_screen(ocr_text, profile="gemini")
    # result.state == "completed" / "approval" / "question" / ...
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import httpx

from ..config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Ekran durumu turleri
# ---------------------------------------------------------------------------
class ScreenState(str, Enum):
    IDLE = "idle"
    APPROVAL = "approval"
    COMPLETED = "completed"
    QUESTION = "question"
    BUSY = "busy"
    EXPAND = "expand"
    ERROR = "error"
    INPUT_NEEDED = "input_needed"
    UNKNOWN = "unknown"


class ActionNeeded(str, Enum):
    CLICK_BUTTON = "click_button"
    CLICK_TEXT = "click_text"
    TYPE_TEXT = "type_text"
    SCROLL_DOWN = "scroll_down"
    WAIT = "wait"
    NOTIFY_USER = "notify_user"
    NONE = "none"


@dataclass
class ScreenAnalysis:
    state: ScreenState = ScreenState.UNKNOWN
    action: ActionNeeded = ActionNeeded.NONE
    target_text: str = ""
    confidence: float = 0.0
    reasoning: str = ""
    options: List[str] = field(default_factory=list)
    completion_summary: str = ""
    raw_llm_response: str = ""

    @property
    def is_actionable(self) -> bool:
        return self.action not in (ActionNeeded.NONE, ActionNeeded.WAIT)


# ---------------------------------------------------------------------------
# Profil bazli system prompt parcalari
# ---------------------------------------------------------------------------
_PROFILE_HINTS: Dict[str, str] = {
    "generic": "",
    "gemini": (
        "Bu ekran Google Gemini (VS Code eklentisi) arayuzune ait. "
        "Gemini'de onay butonlari genellikle ekranin alt kisminda olur: 'Allow once', 'Allow this conversation', 'Allow access'. "
        "Bazen 'Expand' veya 'Expand all' butonu gorunur, buna tiklaninca 'Run' butonu cikar. "
        "Gorev bittiginde Gemini genellikle 'I can help with...', 'Is there anything else...', 'Let me know if...' gibi ifadeler kullanir. "
        "Bazen alt kisimda 'N steps require approval' veya '1 step requires input' yazar."
    ),
    "codex": (
        "Bu ekran OpenAI Codex (VS Code eklentisi) arayuzune ait. "
        "Codex'te onay butonlari: 'Run', 'Run Alt+J', 'Reject'. "
        "Gorev bittiginde genellikle 'Changes applied', 'Done', ozet listesi (modified files, next steps) gosterir. "
        "'Expand all' tiklaninca komut detaylari ve 'Run' butonu gorunur."
    ),
    "claudecode": (
        "Bu ekran Claude Code (VS Code eklentisi) arayuzune ait. "
        "Claude Code'da onay ekrani: 'Allow this bash command?', 'Yes', 'Yes for this session', 'Yes for this run'. "
        "Gorev bittiginde genellikle 'I've completed...', 'Done!', 'All changes have been made', ozet gosterir."
    ),
    "kimicode": (
        "Bu ekran KimiCode (VS Code eklentisi) arayuzune ait. "
        "KimiCode'da onay ve devam butonlari: 'Run', 'Continue', 'Accept'. "
        "Gorev bittiginde genellikle ozet ve 'next steps' gosterir."
    ),
    "copilot": (
        "Bu ekran GitHub Copilot (VS Code eklentisi) arayuzune ait. "
        "Copilot'ta onay ve islem butonlari: 'Accept', 'Accept All', 'Discard'. "
        "Gorev bittiginde genellikle sonuc ozeti gosterir."
    ),
}

_SYSTEM_PROMPT = """\
Sen bir ekran analiz uzmanissin. Sana VS Code IDE'den alinan OCR metni verilecek.
Gorevlerin:
1. Ekranin mevcut durumunu tespit et
2. Yapilmasi gereken aksiyonu belirle
3. Varsa tiklanmasi gereken buton/metin hedefini belirt

{profile_hint}

Ekran durumlari:
- "approval": Bir onay/izin ekrani gorunuyor (Allow, Run, Accept, Yes butonu var)
- "completed": Ajan gorevi TAMAMLAMIS. Asagidaki isaretlerden HERHANGI BIRI varsa completed:
  * Ajan "Done", "Completed", "Finished", "Tamamladim", "Bitirdim", "Tamamlandi", "Bitti" gibi ifadeler kullanmis
  * Ajan ozet/rapor yazarak islemi bitirmis ("Summary", "What was done", "Modified files", "Next steps")
  * Ajan "I've completed", "All changes have been made", "Task is done", "Implementation is complete" yazmis
  * Ajan "Is there anything else?", "Let me know if", "Hope this helps" gibi kapanIS cumlesi yazmis
  * Ajan artik CALISIYOR DEGIL ve son mesajinda tamamlama ifadesi var
  NOT: Ajan "thinking/generating/processing" GOSTERMIYORSA ve yukardaki ifadelerden biri varsa, KESINLIKLE "completed" de. Busy olmamasi + tamamlama ifadesi = completed.
- "question": Ajan kullaniciya soru soruyor veya secenekler sunuyor (A mi B mi? secim yap vb.)
- "busy": Ajan AKTIF OLARAK calisiyor/dusunuyor. SADECE "thinking", "generating", "processing", "loading", "analyzing" gibi CANLI gostergeler varsa busy de. Eger ajan yazmis bitirmis ve duruyorsa bu busy DEGIL.
- "expand": Expand/Expand All butonu gorunuyor, tiklanmasi gerekiyor
- "input_needed": Ajan kullanicidan metin girdisi bekliyor (input alani aktif)
- "idle": Hicbir ozel durum yok, bos ekran
- "error": Bir hata mesaji gorunuyor
- "unknown": Belirsiz durum

Aksiyon turleri:
- "click_button": Belirli bir butona tikla (target_text = buton metni)
- "click_text": Belirli bir metne tikla
- "scroll_down": Asagi kaydir (buton gorunmuyor olabilir)
- "wait": Bekle (ajan calisiyor)
- "notify_user": Kullaniciyi bilgilendir (gorev bitti, soru var vb.)
- "none": Aksiyon gerekmiyor

SADECE asagidaki JSON formatinda yanit ver, baska hicbir sey yazma:
{{"state": "...", "action": "...", "target_text": "...", "confidence": 0.0-1.0, "reasoning": "...", "options": [], "completion_summary": ""}}

Kurallar:
- confidence: 0.0 (emin degilim) ile 1.0 (kesinlikle) arasi
- ONEMLI: Ajan gorevi tamamladiginda yuksek confidence ver (0.85+). "Done", "Tamamladim", "Bitti" gibi acik ifadeler varsa 0.95 ver.
- options: sadece question durumunda, ekranda gordugun secenekleri listele
- completion_summary: sadece completed durumunda, ajanin ne yaptiginin kisa ozetini yaz
- target_text: tiklanmasi gereken butonun TAM metni (OCR'dan gordugun sekilde)
- Turkce ve Ingilizce metinleri analiz edebilmelisin
- "Run Without Debugging", "Start Debugging" gibi VS Code menu ogelerini ASLA onay butonu olarak gorme
- Ekranin ust kismindaki menu cubugu ogelerini (File, Edit, View, Run, Terminal, Help) GORMEZDEN GEL
- Kod blogu, terminal ciktilari, loglar, patch/diff metni veya komut satirinda gecen "allow", "run", "accept", "yes" kelimelerini BUTON sanma
- Bir ajan kullaniciya secim soruyorsa veya alternatif sunuyorsa bunu approval degil question olarak siniflandir
"""


# ---------------------------------------------------------------------------
# Throttle / Cache
# ---------------------------------------------------------------------------
_cache_lock = threading.Lock()
_last_analysis: Optional[ScreenAnalysis] = None
_last_ocr_hash: str = ""
_last_call_ts: float = 0.0
_MIN_CALL_INTERVAL: float = 3.0  # ayni durumdaysa en az 3sn bekle
_CHANGE_CALL_INTERVAL: float = 0.5  # durum degistiyse hemen cagir
_consecutive_same: int = 0


def _ocr_fingerprint(text: str) -> str:
    """OCR metninin kisa parmak izi (degisiklik algilamak icin)."""
    cleaned = re.sub(r"\s+", " ", (text or "").strip().lower())
    cleaned = re.sub(r"\d+", "#", cleaned)  # sayilari normalize et
    return cleaned[:500]


def _texts_similar(fp1: str, fp2: str) -> bool:
    """Iki fingerprint benzer mi (kuyruk degisiklikleri icin tolerans)."""
    if fp1 == fp2:
        return True
    if not fp1 or not fp2:
        return False
    shorter = min(len(fp1), len(fp2))
    if shorter < 10:
        return fp1 == fp2
    common = sum(1 for a, b in zip(fp1, fp2) if a == b)
    return (common / shorter) > 0.85


# ---------------------------------------------------------------------------
# Ollama senkron cagri
# ---------------------------------------------------------------------------
def _call_ollama_sync(
    ocr_text: str,
    profile: str = "generic",
    timeout: float = 30.0,
) -> str:
    """Background thread'den senkron Ollama cagrisi."""
    base_url = settings.ollama_base_url.rstrip("/")
    model = settings.ollama_model

    profile_hint = _PROFILE_HINTS.get(profile, _PROFILE_HINTS["generic"])
    system_content = _SYSTEM_PROMPT.format(profile_hint=profile_hint)

    user_content = (
        f"Profil: {profile}\n"
        f"OCR Metni:\n---\n{ocr_text[:3000]}\n---\n"
        "Yukaridaki ekran durumunu analiz et."
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ],
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 400,
        },
    }

    try:
        with httpx.Client(timeout=httpx.Timeout(timeout, connect=10.0)) as client:
            resp = client.post(f"{base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return str(data.get("message", {}).get("content", "")).strip()
    except httpx.TimeoutException:
        logger.warning("[ScreenAnalyzer] Ollama timeout (%.1fs)", timeout)
        return ""
    except Exception as exc:
        logger.error("[ScreenAnalyzer] Ollama hatasi: %s", exc)
        return ""


def _parse_llm_response(raw: str) -> ScreenAnalysis:
    """LLM yanitini ScreenAnalysis'e cevir."""
    analysis = ScreenAnalysis(raw_llm_response=raw)
    if not raw:
        return analysis

    data = None

    # 1) Dogrudan JSON parse dene (LLM sadece JSON dondurduyse)
    stripped = raw.strip()
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            pass

    # 2) Greedy regex ile JSON bul (LLM aciklama eklediyse)
    if data is None:
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
            except json.JSONDecodeError:
                cleaned = json_match.group()
                cleaned = re.sub(r",\s*}", "}", cleaned)
                cleaned = re.sub(r",\s*]", "]", cleaned)
                try:
                    data = json.loads(cleaned)
                except json.JSONDecodeError:
                    pass

    # 3) Non-greedy (ic ice olmayan) JSON dene
    if data is None:
        json_match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

    if data is None:
        logger.warning("[ScreenAnalyzer] JSON parse basarisiz: %s", raw[:200])
        return analysis

    # State
    state_str = str(data.get("state", "unknown")).lower().strip()
    try:
        analysis.state = ScreenState(state_str)
    except ValueError:
        analysis.state = ScreenState.UNKNOWN

    # Action
    action_str = str(data.get("action", "none")).lower().strip()
    try:
        analysis.action = ActionNeeded(action_str)
    except ValueError:
        analysis.action = ActionNeeded.NONE

    analysis.target_text = str(data.get("target_text", "")).strip()
    analysis.confidence = max(0.0, min(1.0, float(data.get("confidence", 0.0))))
    analysis.reasoning = str(data.get("reasoning", "")).strip()
    analysis.completion_summary = str(data.get("completion_summary", "")).strip()

    options = data.get("options", [])
    if isinstance(options, list):
        analysis.options = [str(o).strip() for o in options if str(o).strip()]

    return analysis


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def analyze_screen(
    ocr_text: str,
    profile: str = "generic",
    force: bool = False,
    timeout: float = 30.0,
) -> Optional[ScreenAnalysis]:
    """
    OCR metnini LLM ile analiz et.

    Throttle: ayni ekranda cok sik cagirmayi onler.
    force=True ile throttle atlanir.

    Returns None eger throttle nedeniyle atlandiysa (cache'den donmez,
    caller mevcut keyword-based logic'i kullanmaya devam eder).
    """
    global _last_analysis, _last_ocr_hash, _last_call_ts, _consecutive_same

    fp = _ocr_fingerprint(ocr_text)
    now = time.time()

    with _cache_lock:
        if not force:
            is_similar = _texts_similar(fp, _last_ocr_hash)
            elapsed = now - _last_call_ts

            if is_similar:
                _consecutive_same += 1
                # Ekran degismemisse hafif backoff (max 6sn = 3*2)
                min_interval = _MIN_CALL_INTERVAL * min(_consecutive_same, 2)
                if elapsed < min_interval and _last_analysis is not None:
                    return _last_analysis
            else:
                _consecutive_same = 0
                if elapsed < _CHANGE_CALL_INTERVAL and _last_analysis is not None:
                    return _last_analysis  # ekran degisiyor ama henuz LLM cagrilamaz, son analizi don

    # LLM cagrisi (lock disinda - blocking IO)
    raw = _call_ollama_sync(ocr_text, profile=profile, timeout=timeout)
    result = _parse_llm_response(raw)

    with _cache_lock:
        _last_analysis = result
        _last_ocr_hash = fp
        _last_call_ts = time.time()

    if result.state != ScreenState.UNKNOWN:
        logger.info(
            "[ScreenAnalyzer] state=%s action=%s target=%s conf=%.2f | %s",
            result.state.value,
            result.action.value,
            result.target_text[:40],
            result.confidence,
            result.reasoning[:80],
        )

    return result


def reset_cache() -> None:
    """Cache'i sifirla (watcher yeniden basladiginda)."""
    global _last_analysis, _last_ocr_hash, _last_call_ts, _consecutive_same
    with _cache_lock:
        _last_analysis = None
        _last_ocr_hash = ""
        _last_call_ts = 0.0
        _consecutive_same = 0
