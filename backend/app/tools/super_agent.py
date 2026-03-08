"""
SUPER AGENT TOOLS
Gercek bir ajan icin gelismis yetenekler
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import tempfile
import threading
import time
import socket
import ipaddress
import unicodedata
import urllib.parse
import urllib.request
import usb.core
import usb.util
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import cv2
import httpx
import numpy as np
import pyautogui
import sounddevice as sd
import scipy.io.wavfile as wav
from PIL import Image, ImageGrab

from ..config import settings
from ..secrets import decrypt_text
from .vscode_automation import run_vscode_agent_prompt

logger = logging.getLogger(__name__)

_WORKSPACE_ROOT = settings.workspace_path.resolve()
_VIRTUAL_DESKTOP = (_WORKSPACE_ROOT / "desktop").resolve()
_USER_DESKTOP_RE = re.compile(r"^(?P<drive>[a-zA-Z]):\\users\\[^\\]+\\desktop(?:\\(?P<tail>.*))?$", re.IGNORECASE)
_PUBLIC_DESKTOP_RE = re.compile(r"^(?P<drive>[a-zA-Z]):\\users\\public\\desktop(?:\\(?P<tail>.*))?$", re.IGNORECASE)

_TR_TRANSLATION = str.maketrans({
    "\u00e7": "c",
    "\u011f": "g",
    "\u0131": "i",
    "\u00f6": "o",
    "\u015f": "s",
    "\u00fc": "u",
    "\u00c7": "c",
    "\u011e": "g",
    "\u0130": "i",
    "\u00d6": "o",
    "\u015e": "s",
    "\u00dc": "u",
})

_BASE_APPROVAL_CONTEXT_TERMS = {
    "permission", "permissions", "authorize", "authorization", "access",
    "trust", "secure", "safety", "agent", "extension", "approval",
    "requires input", "step requires input", "run command", "session", "conversation",
    "onay", "izin", "guven", "yetki", "erisim", "oturum", "komut",
}

_BASE_APPROVAL_BUTTON_TERMS = {
    "approve", "allow", "accept", "authorize", "grant", "yes", "ok",
    "onayla", "onay", "izinver", "kabulet", "kabul", "devam", "evet",
    "proceed",
    # NOT: "expand" cikarildi — sadece Gemini/Codex gibi profillerde eklenir.
    # Claude Code'da "Expand All" kod blogu acar, onay degil.
}

_BASE_APPROVAL_BUTTON_TERMS_MULTI = {
    "allow access",
    "allow once",
    "allow this conversation",
    "allow for this conversation",
    "allow this chat",
    "allow anyway",
    "yes continue",
    "yes for this session",
    "yes for this run",
    "yes always",
    "accept all",
    "accept changes",
    "izin ver",
    "kabul et",
    "devam et",
    "onay ver",
}

_BASE_CONTEXT_FREE_ACTION_TERMS = {
    "accept",
    "accept all",
    "accept changes",
    "expand",
    "devam et",
    "kabul et",
    "onayla",
}
_BASE_CONTEXT_FREE_HINT_TERMS = {
    "permission",
    "approve",
    "agent",
    "extension",
    "codex",
    "claude",
    "kimi",
    "onay",
    "izin",
}

_APPROVAL_NEGATIVE_TERMS = {
    "no", "reject", "cancel", "deny", "decline", "dismiss", "block", "skip", "stop",
    "hayir", "reddet", "iptal", "engelle", "vazgec", "dur",
}

_APPROVAL_NEGATIVE_TERMS_MULTI = {
    "no for this session",
    "no for this run",
    "do not allow",
    "dont allow",
    "do not run",
    "dont run",
    "reject all",
    "cancel run",
}

_APPROVAL_PROFILE_OVERRIDES: Dict[str, Dict[str, set[str]]] = {
    "generic": {},
    "claudecode": {
        "context": {"claude", "bash", "allow this bash command", "requires input", "step requires input"},
        "button_single": {"yes"},
        "button_multi": {"yes for this session", "yes for this run", "allow this bash command"},
        "context_hints": {"bash", "command", "allow", "yes"},
    },
    "codex": {
        "context": {"codex", "requires input", "run command"},
        "button_single": {"run", "expand"},
        "button_multi": {"run alt j", "run anyway", "run command", "expand all"},
        "context_hints": {"codex", "run", "accept", "expand"},
    },
    "kimicode": {
        "context": {"kimi", "requires input", "run command"},
        "button_single": {"run", "continue"},
        "context_hints": {"kimi", "run", "continue", "accept"},
    },
    "gemini": {
        "context": {"gemini", "requires input", "1 step requires input", "allow directory access",
                     "steps require approval", "step requires approval"},
        "button_single": {"run", "expand"},
        "button_multi": {"allow once", "allow this conversation", "allow access",
                         "allow for this conversation", "expand all", "run command"},
        "context_hints": {"gemini", "allow", "conversation", "expand", "approval"},
    },
    "copilot": {
        "context": {"copilot", "requires input"},
        "button_single": {"accept"},
        "button_multi": {"accept all", "accept changes"},
        "context_hints": {"copilot", "accept", "suggestion"},
    },
}

_FORBIDDEN_APPROVAL_TERMS_COMPACT = {
    "runwithoutdebugging",
    "startdebugging",
    "stopdebugging",
    "restartdebugging",
    "openconfigurations",
    "addconfiguration",
    "installadditionaldebuggers",
}
_RUN_PROMPT_CONTEXT_TERMS = {
    "1 step requires input",
    "step requires input",
    "requires input",
    "run command",
}

_STRICT_APPROVAL_CONTEXT_TERMS = {
    "permission", "permissions", "approve", "authorize",
    "requires input", "step requires input", "allow this bash command", "run command",
    "onay", "izin", "yetki",
}

_MENU_BAR_TERMS_COMPACT = {
    "file", "edit", "selection", "view", "go", "run", "terminal", "help",
    "startdebugging", "runwithoutdebugging", "stopdebugging", "restartdebugging",
    "openconfigurations", "addconfiguration", "stepover", "stepinto", "stepout",
    "continue", "togglebreakpoint", "newbreakpoint", "enableallbreakpoints",
    "disableallbreakpoints", "removeallbreakpoints", "installadditionaldebuggers",
}
_DEBUG_MENU_COMMAND_TERMS_COMPACT = {
    "startdebugging", "runwithoutdebugging", "stopdebugging", "restartdebugging",
    "openconfigurations", "addconfiguration",
    "stepover", "stepinto", "stepout", "continue",
    "togglebreakpoint", "newbreakpoint", "enableallbreakpoints",
    "disableallbreakpoints", "removeallbreakpoints", "installadditionaldebuggers",
}
_AMBIGUOUS_APPROVAL_TERMS_COMPACT = {
    "allow", "accept", "approve", "yes", "ok", "run", "continue", "proceed",
    "evet", "tamam", "devam", "onay", "kabul",
}
_QUESTION_SIGNAL_TERMS = (
    "which", "choose", "pick one", "pick", "select", "selection", "decide",
    "would you like", "do you want", "should i", "which option", "confirm which",
    "hangi", "sec", "secenek", "birini sec", "hangisini", "tercih", "karar ver",
    "ne yapayim", "devam etmemi ister misin", "hangisini istersin",
)

_IDE_COMPLETION_TERMS = (
    "done", "completed", "finished", "all done", "all set", "task completed",
    "islem tamamlandi", "gorev tamamlandi", "tamamlandi", "bitti", "sonuc",
    "result ready", "response complete", "good bad", "thumbs up",
    "summary of what was done", "here is a summary of what was done",
    "execution summary", "what was done", "modified files", "next steps",
    "next steps test", "bugs fixed", "syntax ok", "all imports ok",
    "fully complete", "everything is wired up correctly",
    "rapor tamamlandi", "islem basariyla tamamlandi", "tamamlandi ve kaydedildi",
    # Gemini patterns
    "i can help with", "is there anything else", "let me know if",
    "feel free to ask", "hope this helps", "anything else i can help",
    # Codex patterns
    "changes applied", "all changes have been applied", "applied successfully",
    # Claude Code patterns
    "ive completed", "all changes have been made", "changes are complete",
    "implementation is complete", "task is done",
    # KimiCode patterns
    "code has been updated", "modifications complete",
)
_IDE_COMPLETION_STRONG_TERMS = (
    "execution summary",
    "what was done",
    "modified files",
    "next steps",
    "syntax ok",
    "all imports ok",
    "summary of what was done",
    "everything is wired up correctly",
    "fully complete",
    "changes applied",
    "all changes have been applied",
    "all changes have been made",
    "implementation is complete",
    "i can help with",
)
_IDE_COMPLETION_DIRECT_TERMS = (
    "done",
    "completed",
    "finished",
    "all done",
    "task completed",
    "response complete",
    "islem tamamlandi",
    "gorev tamamlandi",
    "tamamlandi",
    "bitti",
    "rapor tamamlandi",
    "islem basariyla tamamlandi",
    "tamamlandi ve kaydedildi",
    "changes applied",
    "task is done",
    "ive completed",
)
_IDE_BUSY_TERMS = (
    "thinking", "generating", "processing", "in progress", "loading", "analyzing",
    "synthesizing",
    "dusunuyor", "calisiyor", "hazirlaniyor", "bekleniyor",
)

_IDE_INPUT_REQUIRED_TERMS = (
    "step requires input",
    "requires input",
    "1 step requires input",
    "allow once",
    "allow this conversation",
    "allow access",
    "allow directory access",
    "run command",
    "permission",
    "authorize",
    "onay",
    "izin",
    "yetki",
    "steps require approval",
    "step requires approval",
    # NOT: "expand all" cikarildi — bu kod blogu acma UI elemani,
    # input required gostergesi degil. Ozellikle Claude Code'da yanlis pozitif uretiyordu.
    "allow for this conversation",
)

_APPROVAL_WATCHER_LOCK = threading.Lock()
_APPROVAL_WATCHER_STATE: Dict[str, Any] = {
    "running": False,
    "thread": None,
    "stop_event": None,
    "started_at": "",
    "last_error": "",
    "checks": 0,
    "accepted": 0,
    "last_event": "",
    "window_pattern": "Visual Studio Code|Code - Insiders",
    "profile": "generic",
    "interval": 1.0,
    "notify_on_completion": True,
    "auto_stop_on_completion": False,
    "completion_detected": False,
    "completion_prompt_sent": False,
    "completion_hits": 0,
    "last_completion_text": "",
    "completion_reason": "",
    "last_notification_at": "",
    "notification_error": "",
    "last_busy_at": "",
    "last_activity_at": "",
    "idle_clear_hits": 0,
    "idle_stable_hits": 0,
}

_TESSERACT_INSTALL_URL = "https://github.com/UB-Mannheim/tesseract/wiki"
_TESSERACT_INSTALL_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def _approval_watcher_status_snapshot_unlocked() -> Dict[str, Any]:
    thread = _APPROVAL_WATCHER_STATE.get("thread")
    running = bool(_APPROVAL_WATCHER_STATE.get("running"))
    alive = bool(isinstance(thread, threading.Thread) and thread.is_alive())
    return {
        "running": running and alive,
        "started_at": _APPROVAL_WATCHER_STATE.get("started_at", ""),
        "checks": int(_APPROVAL_WATCHER_STATE.get("checks", 0)),
        "accepted": int(_APPROVAL_WATCHER_STATE.get("accepted", 0)),
        "last_event": _APPROVAL_WATCHER_STATE.get("last_event", ""),
        "last_error": _APPROVAL_WATCHER_STATE.get("last_error", ""),
        "window_pattern": _APPROVAL_WATCHER_STATE.get("window_pattern", ""),
        "profile": _APPROVAL_WATCHER_STATE.get("profile", "generic"),
        "interval": _APPROVAL_WATCHER_STATE.get("interval", 1.0),
        "notify_on_completion": bool(_APPROVAL_WATCHER_STATE.get("notify_on_completion", True)),
        "auto_stop_on_completion": bool(_APPROVAL_WATCHER_STATE.get("auto_stop_on_completion", False)),
        "completion_detected": bool(_APPROVAL_WATCHER_STATE.get("completion_detected", False)),
        "completion_prompt_sent": bool(_APPROVAL_WATCHER_STATE.get("completion_prompt_sent", False)),
        "completion_hits": int(_APPROVAL_WATCHER_STATE.get("completion_hits", 0)),
        "last_completion_text": _APPROVAL_WATCHER_STATE.get("last_completion_text", ""),
        "completion_reason": _APPROVAL_WATCHER_STATE.get("completion_reason", ""),
        "last_notification_at": _APPROVAL_WATCHER_STATE.get("last_notification_at", ""),
        "notification_error": _APPROVAL_WATCHER_STATE.get("notification_error", ""),
        "last_busy_at": _APPROVAL_WATCHER_STATE.get("last_busy_at", ""),
        "last_activity_at": _APPROVAL_WATCHER_STATE.get("last_activity_at", ""),
        "idle_clear_hits": int(_APPROVAL_WATCHER_STATE.get("idle_clear_hits", 0)),
        "idle_stable_hits": int(_APPROVAL_WATCHER_STATE.get("idle_stable_hits", 0)),
        "watcher_state": _APPROVAL_WATCHER_STATE.get("watcher_state", "watching"),
        "llm_state": _APPROVAL_WATCHER_STATE.get("llm_state", ""),
        "llm_confidence": float(_APPROVAL_WATCHER_STATE.get("llm_confidence", 0.0)),
        "llm_reasoning": _APPROVAL_WATCHER_STATE.get("llm_reasoning", ""),
    }


def _map_desktop_tail_to_workspace(tail: str) -> Optional[Path]:
    normalized = tail.replace("/", "\\").lstrip("\\/")
    if not normalized:
        return None
    lowered = normalized.lower()
    if lowered.startswith("data\\"):
        return (_WORKSPACE_ROOT / normalized[len("data\\"):]).resolve()
    project_prefix = f"{_WORKSPACE_ROOT.parent.name.lower()}\\data\\"
    if lowered.startswith(project_prefix):
        return (_WORKSPACE_ROOT / normalized[len(project_prefix):]).resolve()
    return None


def _resolve_generated_output_path(output_path: str, default_filename: str, category: str = "media") -> Path:
    raw = (output_path or "").strip().strip('"').strip("'")
    if not raw:
        return (_WORKSPACE_ROOT / category / default_filename).resolve()

    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        resolved = candidate.resolve()
        try:
            resolved.relative_to(_WORKSPACE_ROOT)
            return resolved
        except ValueError:
            normalized = raw.replace("/", "\\")
            for pattern in (_PUBLIC_DESKTOP_RE, _USER_DESKTOP_RE):
                match = pattern.match(normalized)
                if not match:
                    continue
                tail = (match.group("tail") or "").lstrip("\\/")
                mapped_workspace = _map_desktop_tail_to_workspace(tail)
                if mapped_workspace is not None:
                    return mapped_workspace
                if not tail:
                    return (_VIRTUAL_DESKTOP / default_filename).resolve()
                return (_VIRTUAL_DESKTOP / tail).resolve()
            return (_WORKSPACE_ROOT / category / resolved.name).resolve()

    lowered = raw.lower().replace("/", "\\")
    if lowered in {"desktop", "masaustu"}:
        return (_VIRTUAL_DESKTOP / default_filename).resolve()

    for prefix in ("desktop\\", "masaustu\\"):
        if lowered.startswith(prefix):
            tail = raw[len(prefix):].lstrip("\\/")
            if not tail:
                return (_VIRTUAL_DESKTOP / default_filename).resolve()
            return (_VIRTUAL_DESKTOP / tail).resolve()

    return (_WORKSPACE_ROOT / candidate).resolve()

def _host_resolves_to_private(hostname: str) -> bool:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return True
    for info in infos:
        ip = info[4][0]
        try:
            obj = ipaddress.ip_address(ip)
        except ValueError:
            return True
        if obj.is_private or obj.is_loopback or obj.is_link_local or obj.is_reserved or obj.is_multicast:
            return True
    return False


def _validate_web_url(url: str) -> None:
    if not settings.web_allow_internet:
        raise ValueError("Agent offline modda calisiyor. Internet istekleri engellendi.")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http/https URLs are allowed.")
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("Invalid URL host.")
    if settings.web_allowed_domains_list:
        allowed = settings.web_allowed_domains_list
        if not any(host == d or host.endswith("." + d) for d in allowed):
            raise ValueError("Host not in WEB_ALLOWED_DOMAINS policy.")
    if settings.web_block_private_hosts and _host_resolves_to_private(host):
        raise ValueError("Private/local network hosts are blocked.")


# =============================================================================
# SCREENSHOT ARACLARI
# =============================================================================

def tool_screenshot_desktop(output_path: str = "", region: List[int] = None) -> Dict[str, Any]:
    """Masaustu ekran goruntusu al."""
    try:
        if region and len(region) == 4:
            # Belirli bolge: [x, y, width, height]
            x, y, w, h = region
            screenshot = pyautogui.screenshot(region=(x, y, w, h))
        else:
            # Tam ekran
            screenshot = pyautogui.screenshot()
        
        # Kaydet
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"desktop_{timestamp}.png"
        target = _resolve_generated_output_path(output_path, default_name, "media")
        target.parent.mkdir(parents=True, exist_ok=True)
        screenshot.save(target)
        
        return {
            "path": str(target),
            "size": target.stat().st_size,
            "resolution": screenshot.size,
            "region": region or "full"
        }
    except Exception as e:
        return {"error": str(e)}


def tool_screenshot_webpage(url: str, output_path: str = "", wait_time: int = 3) -> Dict[str, Any]:
    """Web sayfasi ekran goruntusu al."""
    try:
        _validate_web_url(url)
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        
        # Chrome options
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        
        # Driver
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=chrome_options
        )
        
        try:
            driver.get(url)
            time.sleep(max(1, min(wait_time, 20)))  # Sayfanin yuklenmesini bekle
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            domain = url.replace("https://", "").replace("http://", "").replace("/", "_")[:30]
            default_name = f"web_{domain}_{timestamp}.png"
            target = _resolve_generated_output_path(output_path, default_name, "media")
            target.parent.mkdir(parents=True, exist_ok=True)
            
            driver.save_screenshot(str(target))
            
            return {
                "path": str(target),
                "url": url,
                "size": target.stat().st_size if target.exists() else 0
            }
        finally:
            driver.quit()
            
    except Exception as e:
        return {"error": str(e), "note": "Chrome kurulu oldugundan emin olun"}


def tool_find_image_on_screen(image_path: str, confidence: float = 0.9) -> Dict[str, Any]:
    """Ekranda bir goruntu ara ve konumunu bul."""
    try:
        target = Path(image_path)
        if not target.exists():
            return {"error": "Goruntu dosyasi bulunamadi", "path": image_path}
        
        location = pyautogui.locateOnScreen(str(target), confidence=confidence)
        
        if location:
            center = pyautogui.center(location)
            return {
                "found": True,
                "location": {"left": location.left, "top": location.top, 
                           "width": location.width, "height": location.height},
                "center": {"x": center.x, "y": center.y}
            }
        else:
            return {"found": False, "message": "Goruntu ekranda bulunamadi"}
            
    except Exception as e:
        return {"error": str(e)}


def tool_click_on_screen(x: int, y: int, clicks: int = 1, button: str = "left") -> Dict[str, Any]:
    """Ekranda belirli bir koordinata tikla."""
    try:
        pyautogui.click(x, y, clicks=clicks, button=button)
        return {"success": True, "x": x, "y": y, "clicks": clicks, "button": button}
    except Exception as e:
        return {"error": str(e)}


def tool_type_text(text: str, interval: float = 0.01) -> Dict[str, Any]:
    """Klavyeden metin yaz (Türkçe ve Unicode destekli)."""
    try:
        # ASCII-only text: typewrite (daha güvenilir, karakter karakter)
        if text.isascii():
            pyautogui.typewrite(text, interval=interval)
            return {"success": True, "typed": text, "length": len(text), "method": "typewrite"}

        # Non-ASCII (Türkçe, Unicode vs.): clipboard + paste
        import subprocess as _sp
        import platform
        _sys = platform.system()
        if _sys == "Windows":
            p = _sp.Popen(["clip.exe"], stdin=_sp.PIPE)
            p.communicate(text.encode("utf-16-le"))
        elif _sys == "Darwin":
            p = _sp.Popen(["pbcopy"], stdin=_sp.PIPE)
            p.communicate(text.encode("utf-8"))
        else:
            p = _sp.Popen(["xclip", "-selection", "clipboard"], stdin=_sp.PIPE)
            p.communicate(text.encode("utf-8"))

        import time
        time.sleep(0.05)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.05)
        return {"success": True, "typed": text, "length": len(text), "method": "clipboard_paste"}
    except Exception as e:
        return {"error": str(e)}


def tool_press_key(key: str, presses: int = 1) -> Dict[str, Any]:
    """Klavye tusuna bas."""
    try:
        pyautogui.press(key, presses=presses)
        return {"success": True, "key": key, "presses": presses}
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# SES KAYIT ARACLARI
# =============================================================================

class AudioRecorder:
    """Ses kaydedici sinif."""
    def __init__(self):
        self.recording = False
        self.frames = []
        self.samplerate = 44100
        self.channels = 2
        
    def start_recording(self):
        self.recording = True
        self.frames = []
        
        def callback(indata, frames, time, status):
            if self.recording:
                self.frames.append(indata.copy())
        
        self.stream = sd.InputStream(
            samplerate=self.samplerate,
            channels=self.channels,
            callback=callback
        )
        self.stream.start()
        
    def stop_recording(self):
        self.recording = False
        self.stream.stop()
        self.stream.close()
        
    def save(self, path: str):
        if not self.frames:
            return False
        
        audio_data = np.concatenate(self.frames, axis=0)
        wav.write(path, self.samplerate, audio_data)
        return True


# Global kaydedici
_audio_recorder = None


def tool_start_audio_recording() -> Dict[str, Any]:
    """Ses kaydina basla."""
    global _audio_recorder
    try:
        _audio_recorder = AudioRecorder()
        _audio_recorder.start_recording()
        return {"success": True, "message": "Ses kaydi basladi", "sample_rate": 44100}
    except Exception as e:
        return {"error": str(e)}


def tool_stop_audio_recording(output_path: str = "") -> Dict[str, Any]:
    """Ses kaydini durdur ve kaydet."""
    global _audio_recorder
    try:
        if not _audio_recorder:
            return {"error": "Aktif ses kaydi yok"}
        
        _audio_recorder.stop_recording()
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"recording_{timestamp}.wav"
        target = _resolve_generated_output_path(output_path, default_name, "media")
        target.parent.mkdir(parents=True, exist_ok=True)
        
        if _audio_recorder.save(str(target)):
            return {
                "success": True,
                "path": str(target),
                "size": target.stat().st_size
            }
        else:
            return {"error": "Kayit bos veya kaydedilemedi"}
            
    except Exception as e:
        return {"error": str(e)}


def tool_play_audio(audio_path: str) -> Dict[str, Any]:
    """Ses dosyasini cal."""
    try:
        from scipy.io import wavfile
        import sounddevice as sd
        
        samplerate, data = wavfile.read(audio_path)
        sd.play(data, samplerate)
        sd.wait()
        
        return {"success": True, "played": audio_path}
    except Exception as e:
        return {"error": str(e)}


def tool_text_to_speech(text: str, output_path: str = "", lang: str = "tr") -> Dict[str, Any]:
    """Metni sese cevir."""
    try:
        # Windows TTS
        if platform.system() == "Windows":
            import win32com.client
            
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            
            if not output_path:
                # Dogrudan konus
                speaker.Speak(text)
                return {"success": True, "spoken": text, "mode": "direct"}
            else:
                # Dosyaya kaydet
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                default_name = f"tts_{timestamp}.wav"
                target = _resolve_generated_output_path(output_path, default_name, "media")
                target.parent.mkdir(parents=True, exist_ok=True)
                
                # WAV olarak kaydet
                stream = win32com.client.Dispatch("SAPI.SpFileStream")
                stream.Open(str(target), 3)  # 3 = SSFMCreateForWrite
                speaker.AudioOutputStream = stream
                speaker.Speak(text)
                stream.Close()
                
                return {
                    "success": True,
                    "path": str(target),
                    "text": text,
                    "size": target.stat().st_size if target.exists() else 0
                }
        else:
            return {"error": "TTS su anda sadece Windows'da destekleniyor"}
            
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# WEBCAM ARACLARI
# =============================================================================

def tool_webcam_capture(output_path: str = "", camera_index: int = 0) -> Dict[str, Any]:
    """Webcam'den fotograf cek."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"[WEBCAM] Opening camera {camera_index}")
        cap = cv2.VideoCapture(camera_index)
        
        if not cap.isOpened():
            logger.error(f"[WEBCAM] Camera {camera_index} could not be opened")
            return {"error": f"Kamera {camera_index} acilamadi. Kamera baska bir uygulama tarafindan kullaniliyor olabilir."}
        
        # Birkac kare bekle (oto focus)
        logger.info("[WEBCAM] Warming up camera...")
        for i in range(10):
            ret, _ = cap.read()
            if not ret:
                logger.warning(f"[WEBCAM] Warmup frame {i} failed")
        
        # Gercek kareyi yakala
        ret, frame = cap.read()
        cap.release()
        
        if not ret or frame is None or frame.size == 0:
            logger.error(f"[WEBCAM] Frame capture failed")
            return {"error": "Kare yakalanamadi. Kamera baska bir uygulama tarafindan kullaniliyor olabilir."}
        
        logger.info(f"[WEBCAM] Frame captured: shape={frame.shape}")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"capture_{timestamp}.jpg"
        target = _resolve_generated_output_path(output_path, default_name, "media")
        
        logger.info(f"[WEBCAM] Target: {target}")
        
        # Klasoru olustur
        target.parent.mkdir(parents=True, exist_ok=True)
        
        # BGR -> RGB cevir (PIL icin)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(frame_rgb)
        
        # PIL ile kaydet (cv2.imwrite yerine)
        try:
            image.save(str(target), "JPEG", quality=95)
            logger.info(f"[WEBCAM] PIL save success")
        except Exception as pil_err:
            logger.error(f"[WEBCAM] PIL save failed: {pil_err}")
            # PIL basarisiz olursa cv2 dene
            write_success = cv2.imwrite(str(target), frame)
            if not write_success:
                return {"error": f"Fotograf kaydedilemedi: {pil_err}"}
        
        # Dosya kontrol
        if not target.exists():
            return {"error": "Dosya olusturulamadi"}
        
        file_size = target.stat().st_size
        if file_size == 0:
            target.unlink()
            return {"error": "Fotograf bos (0 byte)"}
        
        logger.info(f"[WEBCAM] Success! {file_size} bytes")
        
        return {
            "success": True,
            "path": str(target),
            "size": file_size,
            "resolution": f"{frame.shape[1]}x{frame.shape[0]}"
        }
        
    except Exception as e:
        logger.exception("[WEBCAM] Exception")
        return {"error": f"Webcam hatasi: {str(e)}"}


def tool_webcam_record_video(duration: int = 10, output_path: str = "", camera_index: int = 0) -> Dict[str, Any]:
    """Webcam'den video kaydet."""
    try:
        cap = cv2.VideoCapture(camera_index)
        
        if not cap.isOpened():
            return {"error": f"Kamera {camera_index} acilamadi"}
        
        # Video ozellikleri
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = 20.0
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"video_{timestamp}.avi"
        target = _resolve_generated_output_path(output_path, default_name, "media")
        target.parent.mkdir(parents=True, exist_ok=True)
        
        # Video writer
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        out = cv2.VideoWriter(str(target), fourcc, fps, (width, height))
        
        start_time = time.time()
        frames = 0
        
        while time.time() - start_time < duration:
            ret, frame = cap.read()
            if ret:
                out.write(frame)
                frames += 1
        
        cap.release()
        out.release()
        
        return {
            "success": True,
            "path": str(target),
            "duration": duration,
            "frames": frames,
            "fps": fps,
            "size": target.stat().st_size
        }
        
    except Exception as e:
        return {"error": str(e)}


def tool_list_cameras() -> Dict[str, Any]:
    """Kullanilabilir kameralari listele."""
    try:
        cameras = []
        
        for i in range(10):  # Ilk 10 kamerayi dene
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                cameras.append({
                    "index": i,
                    "resolution": f"{width}x{height}",
                    "available": True
                })
                cap.release()
        
        return {"cameras": cameras, "count": len(cameras)}
        
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# USB CIHAZ ARACLARI
# =============================================================================

def tool_list_usb_devices() -> Dict[str, Any]:
    """Bagli USB cihazlarini listele."""
    try:
        devices = []
        
        # pyusb ile listele
        for device in usb.core.find(find_all=True):
            try:
                devices.append({
                    "vendor_id": hex(device.idVendor) if device.idVendor else None,
                    "product_id": hex(device.idProduct) if device.idProduct else None,
                    "manufacturer": usb.util.get_string(device, device.iManufacturer) if device.iManufacturer else None,
                    "product": usb.util.get_string(device, device.iProduct) if device.iProduct else None,
                    "serial_number": usb.util.get_string(device, device.iSerialNumber) if device.iSerialNumber else None
                })
            except:
                # Bazi cihazlar string alanlarini desteklemez
                devices.append({
                    "vendor_id": hex(device.idVendor) if device.idVendor else None,
                    "product_id": hex(device.idProduct) if device.idProduct else None,
                    "manufacturer": None,
                    "product": None,
                    "serial_number": None
                })
        
        # Windows'ta ek bilgi
        if platform.system() == "Windows":
            try:
                import wmi
                c = wmi.WMI()
                wmi_devices = []
                for usb in c.Win32_USBHub():
                    wmi_devices.append({
                        "name": usb.Name,
                        "device_id": usb.DeviceID,
                        "status": usb.Status,
                        "pnp_device_id": usb.PNPDeviceID
                    })
                return {"usb_devices": devices, "wmi_usb_info": wmi_devices, "count": len(devices)}
            except:
                pass
        
        return {"usb_devices": devices, "count": len(devices)}
        
    except Exception as e:
        return {"error": str(e)}


def tool_eject_usb_drive(drive_letter: str) -> Dict[str, Any]:
    """USB surucusunu guvenli cikar."""
    try:
        if platform.system() == "Windows":
            # PowerShell ile cikar
            ps_command = f"(New-Object -comObject Shell.Application).Namespace(17).ParseName('{drive_letter}:').InvokeVerb('Eject')"
            result = subprocess.run(["powershell", "-Command", ps_command], 
                                  capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                return {"success": True, "drive": drive_letter, "message": "Surucu guvenli cikarildi"}
            else:
                return {"error": result.stderr or "Cikarma basarisiz"}
        else:
            return {"error": "Bu ozellik su anda sadece Windows'da destekleniyor"}
            
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# GELIŞMIŞ OTOMASYON
# =============================================================================

def tool_mouse_position() -> Dict[str, Any]:
    """Fare pozisyonunu al."""
    try:
        x, y = pyautogui.position()
        screen_size = pyautogui.size()
        return {
            "x": x,
            "y": y,
            "screen_width": screen_size.width,
            "screen_height": screen_size.height
        }
    except Exception as e:
        return {"error": str(e)}


def tool_mouse_move(x: int, y: int, duration: float = 0.5) -> Dict[str, Any]:
    """Fareyi hareket ettir."""
    try:
        pyautogui.moveTo(x, y, duration=duration)
        return {"success": True, "x": x, "y": y, "duration": duration}
    except Exception as e:
        return {"error": str(e)}


def tool_drag_to(x: int, y: int, duration: float = 0.5, button: str = "left") -> Dict[str, Any]:
    """Surukle-birak yap."""
    try:
        pyautogui.dragTo(x, y, duration=duration, button=button)
        return {"success": True, "to_x": x, "to_y": y}
    except Exception as e:
        return {"error": str(e)}


def tool_scroll(amount: int, x: int = None, y: int = None) -> Dict[str, Any]:
    """Fare tekerlegi kaydir."""
    try:
        if x is not None and y is not None:
            pyautogui.scroll(amount, x=x, y=y)
        else:
            pyautogui.scroll(amount)
        return {"success": True, "amount": amount}
    except Exception as e:
        return {"error": str(e)}


def tool_hotkey(*keys: str, keys_list: Optional[List[str]] = None) -> Dict[str, Any]:
    """Klavye kisayolu calistir.
    
    Args:
        *keys: Pozisyonel tus argumanlari (ornegin: "ctrl", "c")
        keys_list: Alternatif olarak tus listesi (ornegin: ["ctrl", "c"])
    """
    try:
        # Eger keys_list verilmisse onu kullan, yoksa *keys'i kullan
        key_sequence = keys_list if keys_list else list(keys)
        if not key_sequence:
            return {"error": "En az bir tus belirtilmeli. Ornek: hotkey('ctrl', 'c') veya hotkey(keys_list=['ctrl', 'c'])"}
        
        pyautogui.hotkey(*key_sequence)
        return {"success": True, "keys": key_sequence}
    except Exception as e:
        return {"error": str(e)}


def tool_alert(message: str, title: str = "OpenWorld Agent") -> Dict[str, Any]:
    """Ekranda uyari penceresi goster."""
    try:
        pyautogui.alert(text=message, title=title, button='Tamam')
        return {"success": True, "message": message}
    except Exception as e:
        return {"error": str(e)}


def tool_confirm(message: str, title: str = "OpenWorld Agent") -> Dict[str, Any]:
    """Onay penceresi goster."""
    try:
        result = pyautogui.confirm(text=message, title=title, buttons=['Evet', 'Hayir'])
        return {"success": True, "result": result}
    except Exception as e:
        return {"error": str(e)}


def tool_prompt(message: str, title: str = "OpenWorld Agent", default: str = "") -> Dict[str, Any]:
    """Kullanicidan giris iste."""
    try:
        result = pyautogui.prompt(text=message, title=title, default=default)
        return {"success": True, "result": result}
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# WINDOWS OZEL ARACLAR
# =============================================================================

def tool_get_window_list() -> Dict[str, Any]:
    """Acik penceleri listele."""
    try:
        if platform.system() == "Windows":
            import win32gui
            
            windows = []
            
            def callback(hwnd, extra):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if title:
                        rect = win32gui.GetWindowRect(hwnd)
                        windows.append({
                            "handle": hwnd,
                            "title": title,
                            "rect": {
                                "left": rect[0],
                                "top": rect[1],
                                "right": rect[2],
                                "bottom": rect[3],
                                "width": rect[2] - rect[0],
                                "height": rect[3] - rect[1]
                            }
                        })
            
            win32gui.EnumWindows(callback, None)
            return {"windows": windows, "count": len(windows)}
        else:
            return {"error": "Bu ozellik su anda sadece Windows'da destekleniyor"}
            
    except Exception as e:
        return {"error": str(e)}


def tool_activate_window(title_pattern: str) -> Dict[str, Any]:
    """Belirli bir pencereyi one getir."""
    try:
        if platform.system() == "Windows":
            import re

            try:
                import win32gui

                matched: Dict[str, Any] = {"hwnd": None, "title": ""}

                def callback(hwnd, extra):
                    if matched["hwnd"] is not None:
                        return
                    if not win32gui.IsWindowVisible(hwnd):
                        return
                    title = win32gui.GetWindowText(hwnd) or ""
                    if not title:
                        return
                    if re.search(title_pattern, title, re.IGNORECASE):
                        matched["hwnd"] = hwnd
                        matched["title"] = title

                win32gui.EnumWindows(callback, None)

                hwnd = matched.get("hwnd")
                if hwnd is None:
                    return {"success": False, "pattern": title_pattern, "error": "Pencere bulunamadi"}

                if win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, 9)  # SW_RESTORE
                win32gui.SetForegroundWindow(hwnd)
                return {"success": True, "pattern": title_pattern, "title": matched.get("title", "")}
            except Exception:
                # pywin32 olmayan ortamlarda pygetwindow fallback'i kullan.
                import pygetwindow as gw

                windows = gw.getAllWindows()
                for win in windows:
                    title = getattr(win, "title", "") or ""
                    if not title:
                        continue
                    if re.search(title_pattern, title, re.IGNORECASE):
                        try:
                            if hasattr(win, "isMinimized") and win.isMinimized:
                                win.restore()
                            win.activate()
                            return {"success": True, "pattern": title_pattern, "title": title}
                        except Exception as exc:
                            return {"success": False, "pattern": title_pattern, "error": str(exc)}
                return {"success": False, "pattern": title_pattern, "error": "Pencere bulunamadi"}
        else:
            return {"error": "Bu ozellik su anda sadece Windows'da destekleniyor"}
            
    except Exception as e:
        return {"error": str(e)}


def tool_minimize_all_windows() -> Dict[str, Any]:
    """Tum pencereleri simge durumuna kucult."""
    try:
        if platform.system() == "Windows":
            import win32gui
            win32gui.EnumWindows(lambda hwnd, extra: win32gui.ShowWindow(hwnd, 6) if win32gui.IsWindowVisible(hwnd) else None, None)
            return {"success": True, "message": "Tum pencereler simge durumuna kucultuldu"}
        else:
            return {"error": "Bu ozellik su anda sadece Windows'da destekleniyor"}
    except Exception as e:
        return {"error": str(e)}


def tool_lock_workstation() -> Dict[str, Any]:
    """Is istasyonunu kilitle."""
    try:
        if platform.system() == "Windows":
            import ctypes
            ctypes.windll.user32.LockWorkStation()
            return {"success": True, "message": "Is istasyonu kilitlendi"}
        else:
            return {"error": "Bu ozellik su anda sadece Windows'da destekleniyor"}
    except Exception as e:
        return {"error": str(e)}


def tool_shutdown_system(action: str = "shutdown", timeout: int = 60) -> Dict[str, Any]:
    """Bilgisayari kapat/yeniden baslat."""
    try:
        if action not in ["shutdown", "restart", "logout"]:
            return {"error": "Gecersiz action. shutdown/restart/logout kullanin"}
        
        if platform.system() == "Windows":
            if action == "shutdown":
                subprocess.run(["shutdown", "/s", "/t", str(timeout), "/c", "OpenWorld Agent tarafindan kapatiliyor"])
            elif action == "restart":
                subprocess.run(["shutdown", "/r", "/t", str(timeout), "/c", "OpenWorld Agent tarafindan yeniden baslatiliyor"])
            elif action == "logout":
                subprocess.run(["shutdown", "/l"])
            
            return {"success": True, "action": action, "timeout": timeout}
        else:
            return {"error": "Bu ozellik su anda sadece Windows'da destekleniyor"}
            
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# IDE ONAY BEKLEME VE KABUL
# =============================================================================

def _normalize_for_ocr_match(text: str) -> str:
    normalized = (text or "").translate(_TR_TRANSLATION).lower()
    normalized = unicodedata.normalize("NFKD", normalized)
    normalized = "".join(ch for ch in normalized if ch.isalnum() or ch.isspace())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _compact_normalized(text: str) -> str:
    return re.sub(r"\s+", "", _normalize_for_ocr_match(text or ""))


def _build_approval_profile_terms(profile: str) -> Dict[str, set[str]]:
    key = _normalize_for_ocr_match(profile or "generic") or "generic"
    if key not in _APPROVAL_PROFILE_OVERRIDES:
        key = "generic"
    override = _APPROVAL_PROFILE_OVERRIDES.get(key, {})

    context_terms = set(_BASE_APPROVAL_CONTEXT_TERMS)
    button_single = set(_BASE_APPROVAL_BUTTON_TERMS)
    button_multi = set(_BASE_APPROVAL_BUTTON_TERMS_MULTI)
    context_actions = set(_BASE_CONTEXT_FREE_ACTION_TERMS)
    context_hints = set(_BASE_CONTEXT_FREE_HINT_TERMS)

    context_terms.update(override.get("context", set()))
    button_single.update(override.get("button_single", set()))
    button_multi.update(override.get("button_multi", set()))
    context_actions.update(override.get("context_actions", set()))
    context_hints.update(override.get("context_hints", set()))

    return {
        "profile": {key},
        "context_terms": {_normalize_for_ocr_match(x) for x in context_terms if x},
        "button_single": {_normalize_for_ocr_match(x) for x in button_single if x},
        "button_multi": {_normalize_for_ocr_match(x) for x in button_multi if x},
        "context_actions": {_normalize_for_ocr_match(x) for x in context_actions if x},
        "context_hints": {_normalize_for_ocr_match(x) for x in context_hints if x},
        "negative_single": {_normalize_for_ocr_match(x) for x in _APPROVAL_NEGATIVE_TERMS if x},
        "negative_multi": {_normalize_for_ocr_match(x) for x in _APPROVAL_NEGATIVE_TERMS_MULTI if x},
    }


def _is_negative_decision(
    text: str,
    negative_single: set[str],
    negative_multi: set[str],
    negative_compact: set[str],
) -> bool:
    normalized = _normalize_for_ocr_match(text or "")
    if not normalized:
        return False
    if normalized in negative_single or normalized in negative_multi:
        return True
    compact = _compact_normalized(normalized)
    if compact in negative_compact:
        return True
    if compact.startswith(("reject", "cancel", "deny", "decline", "dismiss", "reddet", "iptal", "hayir")):
        return True
    return False


def _score_approval_candidate(
    candidate: Dict[str, Any],
    *,
    active_profile: str,
    has_context: bool,
    hint_hit: bool,
    run_prompt_context_hit: bool,
    button_terms_multi: set[str],
    button_terms_multi_compact: set[str],
) -> float:
    token = _normalize_for_ocr_match(str(candidate.get("norm", "")))
    compact = _compact_normalized(token)
    conf = float(candidate.get("conf", 0.0))
    score = conf
    if has_context:
        score += 14.0
    if hint_hit:
        score += 8.0
    run_friendly_profiles = {"codex", "claudecode", "gemini"}
    run_friendly = active_profile in run_friendly_profiles
    if run_prompt_context_hit and run_friendly and ("run" in token or compact.startswith("run")):
        score += 28.0
    if token in button_terms_multi or compact in button_terms_multi_compact:
        score += 22.0
    if token in {"yes", "evet"} or token == "allow" or token == "accept" or token.startswith("yes ") or token.startswith("allow ") or token.startswith("accept "):
        score += 16.0
    if run_prompt_context_hit and run_friendly and (token.startswith("run") or "continue" in token):
        score += 12.0
    if not run_friendly and (token.startswith("run") or compact.startswith("run")):
        score -= 22.0
    # Buttons are usually lower-right in modal dialogs.
    score += float(candidate.get("top", 0)) * 0.0012
    score += float(candidate.get("left", 0)) * 0.0008
    return score


def _is_button_like_token(
    token: str,
    button_terms_single: set[str],
    context_free_action_terms: set[str],
    button_terms_compact: set[str],
) -> bool:
    if not token:
        return False
    if token in button_terms_single or token in context_free_action_terms:
        return True

    compact = re.sub(r"\s+", "", token)
    if compact in button_terms_compact:
        return True

    # Shortcut etiketleri: RunAltJ / AcceptAll / ContinueWithoutDebugging gibi birlesik OCR ciktisi.
    if compact.startswith("run") and (compact == "run" or "alt" in compact or "without" in compact):
        return True
    if compact in {"accept", "approve", "allow"}:
        return True
    if compact.startswith("continuewithout"):
        return True
    if compact.startswith("onay") or compact.startswith("kabul") or compact.startswith("devam"):
        return True
    return False


def _is_button_like_phrase(
    phrase: str,
    button_terms_multi: set[str],
    button_terms_multi_compact: set[str],
    button_terms_compact: set[str],
) -> bool:
    if not phrase:
        return False
    if phrase in button_terms_multi:
        return True
    compact = re.sub(r"\s+", "", phrase)
    if compact in button_terms_multi_compact or compact in button_terms_compact:
        return True
    if compact.startswith("acceptall") or compact.startswith("acceptchanges"):
        return True
    if compact.startswith("runwithoutdebugging") or compact.startswith("continuewithoutdebugging"):
        return True
    return False


def _is_likely_menu_term(token: str) -> bool:
    compact = _compact_normalized(token or "")
    if not compact:
        return False
    if compact in _MENU_BAR_TERMS_COMPACT:
        return True
    if compact.startswith("runwithoutdebugging") or compact.startswith("startdebugging"):
        return True
    if compact.startswith("restartdebugging") or compact.startswith("openconfigurations"):
        return True
    return False


def _is_ambiguous_approval_candidate(token: str) -> bool:
    compact = _compact_normalized(token or "")
    return compact in _AMBIGUOUS_APPROVAL_TERMS_COMPACT


def _is_yes_like_candidate(text: str) -> bool:
    norm = _normalize_for_ocr_match(text or "")
    if not norm:
        return False
    if norm in {"yes", "evet"}:
        return True
    if norm.startswith("yes ") or norm.startswith("evet "):
        return True
    if norm.startswith("1 yes") or norm.startswith("1 evet"):
        return True
    return False


def _in_modal_action_zone(candidate: Dict[str, Any], image_width: int, image_height: int) -> bool:
    left = int(candidate.get("left", 0) or 0)
    top = int(candidate.get("top", 0) or 0)
    width = int(candidate.get("width", 0) or 0)
    height = int(candidate.get("height", 0) or 0)
    center_x = left + max(1, width) / 2
    center_y = top + max(1, height) / 2
    if image_height > 0 and center_y >= image_height * 0.55:
        return True
    if image_width > 0 and center_x >= image_width * 0.62:
        return True
    return False


def _looks_like_question_text(ocr_blob: str) -> bool:
    blob = _normalize_for_ocr_match(ocr_blob or "")
    if not blob:
        return False
    if _looks_like_ide_completion_text(blob) or _looks_like_ide_busy_text(blob):
        return False
    hits = sum(1 for term in _QUESTION_SIGNAL_TERMS if _normalize_for_ocr_match(term) in blob)
    has_choice_shape = any(
        phrase in blob for phrase in (
            "a or b", "1 or 2", "yes or no",
            "a mi b mi", "evet mi hayir mi", "bu mu su mu",
        )
    )
    return hits >= 2 or (hits >= 1 and has_choice_shape)


def _in_top_menu_zone(candidate: Dict[str, Any], image_height: int) -> bool:
    if image_height <= 0:
        return False
    top = int(candidate.get("top", 0))
    threshold = max(64, min(140, int(image_height * 0.14)))
    return top <= threshold


def _get_window_region(title_pattern: str) -> Optional[Tuple[int, int, int, int]]:
    if platform.system() != "Windows" or not title_pattern:
        return None
    try:
        import win32gui

        matched: Dict[str, Tuple[int, int, int, int]] = {}

        def callback(hwnd, _):
            if matched:
                return
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd) or ""
            if not title:
                return
            if not re.search(title_pattern, title, re.IGNORECASE):
                return
            rect = win32gui.GetWindowRect(hwnd)
            left, top, right, bottom = rect
            width = max(1, right - left)
            height = max(1, bottom - top)
            if width < 200 or height < 120:
                return
            matched["region"] = (max(0, left), max(0, top), width, height)

        win32gui.EnumWindows(callback, None)
        return matched.get("region")
    except Exception:
        return None


def _build_tesseract_error(
    detail: str = "",
    attempted_path: str = "",
    configured_path: str = "",
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "error": "Tesseract OCR bulunamadı veya çalışmıyor.",
        "install_path": _TESSERACT_INSTALL_CMD,
        "install_url": _TESSERACT_INSTALL_URL,
    }
    if detail:
        payload["detail"] = str(detail)[:260]
    if attempted_path:
        payload["attempted_path"] = attempted_path
    if configured_path:
        payload["configured_path"] = configured_path
    return payload


def _resolve_tesseract_binary() -> Tuple[Optional[str], Dict[str, Any]]:
    configured_raw = str(getattr(settings, "tesseract_cmd", "") or "").strip().strip('"').strip("'")
    if configured_raw:
        configured_candidate = Path(configured_raw).expanduser()
        if configured_candidate.is_dir():
            configured_candidate = configured_candidate / ("tesseract.exe" if os.name == "nt" else "tesseract")
        if configured_candidate.exists() and configured_candidate.is_file():
            return str(configured_candidate.resolve()), {}
        return None, _build_tesseract_error(
            detail="TESSERACT_CMD yolu geçersiz.",
            attempted_path=str(configured_candidate),
            configured_path=configured_raw,
        )

    from_path = shutil.which("tesseract")
    if from_path:
        return from_path, {}

    return None, _build_tesseract_error(detail="PATH üzerinde tesseract bulunamadı.")


def _configure_tesseract_runtime(pytesseract_module: Any) -> Dict[str, Any]:
    resolved_cmd, err_payload = _resolve_tesseract_binary()
    if not resolved_cmd:
        return {"ok": False, **err_payload}

    try:
        pytesseract_module.pytesseract.tesseract_cmd = resolved_cmd
        _ = pytesseract_module.get_tesseract_version()
    except Exception as exc:
        return {
            "ok": False,
            **_build_tesseract_error(
                detail=str(exc),
                attempted_path=resolved_cmd,
                configured_path=str(getattr(settings, "tesseract_cmd", "") or "").strip(),
            ),
        }

    return {"ok": True, "resolved_cmd": resolved_cmd}


def _resolve_telegram_bot_token() -> str:
    token = str(getattr(settings, "telegram_bot_token", "") or "").strip()
    if token:
        return token
    token_enc = str(getattr(settings, "telegram_bot_token_enc", "") or "").strip()
    if not token_enc:
        return ""
    try:
        return decrypt_text(token_enc).strip()
    except Exception:
        return ""


def _send_telegram_notification(
    text: str,
    *,
    photo_path: str = "",
    buttons: Optional[List[List[Tuple[str, str]]]] = None,
    parse_mode: str = "HTML",
) -> Tuple[bool, str]:
    token = _resolve_telegram_bot_token()
    chat_id = str(getattr(settings, "telegram_allowed_user_id", "") or "").strip()
    if not token or not chat_id:
        return False, "Telegram token veya allowed user id eksik."
    try:
        reply_markup = ""
        if buttons:
            reply_markup = json.dumps(
                {
                    "inline_keyboard": [
                        [{"text": label, "callback_data": callback_data} for label, callback_data in row]
                        for row in buttons
                    ]
                },
                ensure_ascii=False,
            )

        api_base = f"https://api.telegram.org/bot{token}"
        with httpx.Client(timeout=httpx.Timeout(15.0, connect=10.0)) as client:
            if photo_path:
                photo = Path(photo_path)
                if photo.exists() and photo.is_file():
                    with open(photo, "rb") as fh:
                        photo_resp = client.post(
                            f"{api_base}/sendPhoto",
                            data={"chat_id": chat_id},
                            files={"photo": (photo.name, fh, "image/png")},
                        )
                        photo_resp.raise_for_status()

            payload = {
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": "true",
            }
            if parse_mode:
                payload["parse_mode"] = parse_mode
            if reply_markup:
                payload["reply_markup"] = reply_markup

            resp = client.post(f"{api_base}/sendMessage", data=payload)
            resp.raise_for_status()
            body = resp.text
        return True, body[:240]
    except Exception as exc:
        return False, str(exc)


def _watcher_ocr_scan(
    window_pattern: str = "",
    lang: str = "tur+eng",
    min_confidence: float = 25.0,
) -> Dict[str, Any]:
    """
    Watcher icin sadece OCR okuma — TIKLAMAZ.
    Dondurur: {ocr_blob, busy, input_required, error}
    """
    try:
        import pytesseract
        from pytesseract import Output
    except ImportError:
        return {"ocr_blob": "", "busy": False, "input_required": False, "error": "pytesseract yok"}

    tesseract_runtime = _configure_tesseract_runtime(pytesseract)
    if not tesseract_runtime.get("ok"):
        return {"ocr_blob": "", "busy": False, "input_required": False, "error": "tesseract hazir degil"}

    try:
        if window_pattern:
            tool_activate_window(window_pattern)
        region = _get_window_region(window_pattern) if window_pattern else None
        screenshot = pyautogui.screenshot(region=region) if region else pyautogui.screenshot()

        data = pytesseract.image_to_data(
            screenshot, lang=lang, output_type=Output.DICT, config="--oem 3 --psm 6",
        )

        blob_parts = []
        count = len(data.get("text", []))
        for i in range(count):
            raw = str(data["text"][i] or "").strip()
            if not raw:
                continue
            norm = _normalize_for_ocr_match(raw)
            if norm:
                blob_parts.append(norm)

        blob = " ".join(blob_parts)
        return {
            "ocr_blob": blob[:2000],
            "busy": _looks_like_ide_busy_text(blob),
            "input_required": _looks_like_input_required_text(blob),
            "error": "",
        }
    except Exception as exc:
        return {"ocr_blob": "", "busy": False, "input_required": False, "error": str(exc)[:200]}


def _click_text_on_active_window(
    target_text: str,
    window_pattern: str = "",
    lang: str = "tur+eng",
    min_confidence: float = 25.0,
) -> Dict[str, Any]:
    """
    Ekranda belirtilen metni OCR ile bul ve tikla.
    Fuzzy matching destekler (SequenceMatcher >= 0.75).
    """
    import pytesseract
    from pytesseract import Output

    if window_pattern:
        tool_activate_window(window_pattern)
    region = _get_window_region(window_pattern) if window_pattern else None
    screenshot = pyautogui.screenshot(region=region) if region else pyautogui.screenshot()

    data = pytesseract.image_to_data(
        screenshot, lang=lang, output_type=Output.DICT, config="--oem 3 --psm 6",
    )

    target_norm = _normalize_for_ocr_match(target_text)
    target_compact = _compact_normalized(target_norm)
    best_match = None
    best_ratio = 0.0

    count = len(data.get("text", []))
    words_info = []
    for i in range(count):
        raw = str(data["text"][i] or "").strip()
        if not raw:
            continue
        try:
            conf = float(data["conf"][i])
        except Exception:
            conf = -1.0
        if conf < min_confidence:
            continue
        words_info.append({
            "raw": raw,
            "norm": _normalize_for_ocr_match(raw),
            "left": int(data["left"][i]),
            "top": int(data["top"][i]),
            "width": int(data["width"][i]),
            "height": int(data["height"][i]),
            "conf": conf,
        })

    # Exact match (tek kelime veya compact)
    for w in words_info:
        if _compact_normalized(w["norm"]) == target_compact:
            best_match = w
            best_ratio = 1.0
            break

    # Multi-word sliding window
    if not best_match and len(target_norm.split()) > 1:
        target_words = target_norm.split()
        n = len(target_words)
        for start in range(len(words_info) - n + 1):
            group = words_info[start:start + n]
            joined = " ".join(g["norm"] for g in group)
            ratio = SequenceMatcher(None, joined, target_norm).ratio()
            if ratio > best_ratio and ratio >= 0.75:
                best_ratio = ratio
                left = min(g["left"] for g in group)
                top = min(g["top"] for g in group)
                right = max(g["left"] + g["width"] for g in group)
                bottom = max(g["top"] + g["height"] for g in group)
                best_match = {
                    "raw": " ".join(g["raw"] for g in group),
                    "norm": joined,
                    "left": left, "top": top,
                    "width": max(1, right - left),
                    "height": max(1, bottom - top),
                    "conf": min(g["conf"] for g in group),
                }

    # Fuzzy single word
    if not best_match:
        for w in words_info:
            ratio = SequenceMatcher(None, w["norm"], target_norm).ratio()
            if ratio > best_ratio and ratio >= 0.75:
                best_ratio = ratio
                best_match = w

    if not best_match:
        return {"success": False, "target_text": target_text, "message": "Metin ekranda bulunamadi."}

    click_x = int(best_match["left"] + best_match["width"] / 2)
    click_y = int(best_match["top"] + best_match["height"] / 2)
    if region:
        click_x += int(region[0])
        click_y += int(region[1])

    pyautogui.click(click_x, click_y)
    return {
        "success": True,
        "target_text": target_text,
        "matched_text": best_match["raw"],
        "match_ratio": round(best_ratio, 3),
        "x": click_x, "y": click_y,
    }


def capture_notification_screenshot(prefix: str = "approval_completion") -> str:
    try:
        workspace = Path(getattr(settings, "workspace_path", Path.cwd()))
        media_dir = workspace / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        safe_prefix = re.sub(r"[^a-zA-Z0-9_-]+", "_", prefix).strip("_") or "notification"
        target = media_dir / f"{safe_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        result = tool_screenshot_desktop(output_path=str(target))
        if isinstance(result, dict) and not result.get("error") and result.get("path"):
            path = Path(str(result["path"]))
            if path.exists() and path.is_file():
                return str(path)
    except Exception:
        pass
    return ""


def _capture_completion_screenshot() -> str:
    return capture_notification_screenshot("approval_completion")


def _looks_like_ide_completion_text(ocr_blob: str) -> bool:
    blob = _normalize_for_ocr_match(ocr_blob or "")
    if len(blob) < 4:
        return False
    completion_hits = sum(1 for term in _IDE_COMPLETION_TERMS if _normalize_for_ocr_match(term) in blob)
    strong_hits = sum(1 for term in _IDE_COMPLETION_STRONG_TERMS if _normalize_for_ocr_match(term) in blob)
    direct_hits = sum(1 for term in _IDE_COMPLETION_DIRECT_TERMS if _normalize_for_ocr_match(term) in blob)
    busy_hit = any(_normalize_for_ocr_match(term) in blob for term in _IDE_BUSY_TERMS)
    if busy_hit and strong_hits == 0 and direct_hits == 0:
        return False
    return strong_hits >= 1 or direct_hits >= 1 or completion_hits >= 2


def _looks_like_ide_busy_text(ocr_blob: str) -> bool:
    blob = _normalize_for_ocr_match(ocr_blob or "")
    if len(blob) < 4:
        return False
    return any(_normalize_for_ocr_match(term) in blob for term in _IDE_BUSY_TERMS)


def _looks_like_input_required_text(ocr_blob: str) -> bool:
    blob = _normalize_for_ocr_match(ocr_blob or "")
    if len(blob) < 4:
        return False
    return any(_normalize_for_ocr_match(term) in blob for term in _IDE_INPUT_REQUIRED_TERMS)


def _ocr_state_key(text: str) -> str:
    blob = _normalize_for_ocr_match(text or "")
    if not blob:
        return ""
    blob = re.sub(r"\b\d+\b", " ", blob)
    blob = re.sub(r"\s+", " ", blob).strip()
    return blob[:700]


def _ocr_state_similarity(left: str, right: str) -> float:
    left_key = _ocr_state_key(left)
    right_key = _ocr_state_key(right)
    if not left_key or not right_key:
        return 0.0
    if left_key == right_key:
        return 1.0
    return SequenceMatcher(None, left_key, right_key).ratio()


def _reset_completion_signal_unlocked(last_event: str = "") -> None:
    _APPROVAL_WATCHER_STATE["completion_detected"] = False
    _APPROVAL_WATCHER_STATE["completion_prompt_sent"] = False
    _APPROVAL_WATCHER_STATE["completion_hits"] = 0
    _APPROVAL_WATCHER_STATE["last_completion_text"] = ""
    _APPROVAL_WATCHER_STATE["completion_reason"] = ""
    if last_event:
        _APPROVAL_WATCHER_STATE["last_event"] = last_event


def tool_wait_and_accept_approval(
    window_pattern: str = "Visual Studio Code|Code - Insiders",
    timeout: int = 25,
    interval: float = 0.8,
    min_confidence: float = 30.0,
    lang: str = "tur+eng",
    allow_keyboard_fallback: bool = False,
    profile: str = "generic",
) -> Dict[str, Any]:
    """Bekleyen IDE onay penceresini OCR ile bulup kabul etmeye calis."""
    resolved_tesseract_cmd = ""
    try:
        import pytesseract
        from pytesseract import Output
    except Exception as exc:
        if allow_keyboard_fallback:
            try:
                if window_pattern:
                    activation = tool_activate_window(window_pattern)
                    if isinstance(activation, dict) and not activation.get("success"):
                        return {
                            "success": False,
                            "window_pattern": window_pattern,
                            "method": "keyboard_fallback",
                            "note": "OCR yok; fallback denemesi yapilmadi cunku hedef pencere bulunamadi.",
                        }
                pyautogui.hotkey("alt", "y")
                time.sleep(0.1)
                pyautogui.press("enter")
                return {
                    "success": True,
                    "window_pattern": window_pattern,
                    "method": "keyboard_fallback",
                    "note": "OCR yoktu, Alt+Y + Enter denendi.",
                }
            except Exception as fallback_exc:
                return {"error": str(fallback_exc)}
        return _build_tesseract_error(detail=f"pytesseract modülü yüklü değil: {exc}")

    tesseract_runtime = _configure_tesseract_runtime(pytesseract)
    if not tesseract_runtime.get("ok"):
        if allow_keyboard_fallback:
            try:
                if window_pattern:
                    activation = tool_activate_window(window_pattern)
                    if isinstance(activation, dict) and not activation.get("success"):
                        return {
                            "success": False,
                            "window_pattern": window_pattern,
                            "method": "keyboard_fallback",
                            "note": "OCR hazır değil; fallback denemesi yapılmadı çünkü hedef pencere bulunamadı.",
                            **{k: v for k, v in tesseract_runtime.items() if k != "ok"},
                        }
                pyautogui.hotkey("alt", "y")
                time.sleep(0.1)
                pyautogui.press("enter")
                return {
                    "success": True,
                    "window_pattern": window_pattern,
                    "method": "keyboard_fallback",
                    "note": "OCR hazır değildi, Alt+Y + Enter denendi.",
                    **{k: v for k, v in tesseract_runtime.items() if k != "ok"},
                }
            except Exception as fallback_exc:
                return {"error": str(fallback_exc), **{k: v for k, v in tesseract_runtime.items() if k != "ok"}}
        return {k: v for k, v in tesseract_runtime.items() if k != "ok"}

    resolved_tesseract_cmd = str(tesseract_runtime.get("resolved_cmd", "")).strip()

    timeout = max(2, min(int(timeout), 180))
    interval = max(0.25, min(float(interval), 3.0))
    min_confidence = max(0.0, min(float(min_confidence), 100.0))

    profile_terms = _build_approval_profile_terms(profile)
    active_profile = next(iter(profile_terms.get("profile", {"generic"})))
    context_terms = set(profile_terms.get("context_terms", set()))
    button_terms_single = set(profile_terms.get("button_single", set()))
    button_terms_multi = set(profile_terms.get("button_multi", set()))
    context_free_action_terms = set(profile_terms.get("context_actions", set()))
    context_free_hint_terms = set(profile_terms.get("context_hints", set()))
    negative_terms_single = set(profile_terms.get("negative_single", set()))
    negative_terms_multi = set(profile_terms.get("negative_multi", set()))
    run_prompt_context_terms = {_normalize_for_ocr_match(x) for x in _RUN_PROMPT_CONTEXT_TERMS}
    strict_context_terms = {_normalize_for_ocr_match(x) for x in _STRICT_APPROVAL_CONTEXT_TERMS}
    button_terms_multi_compact = {_compact_normalized(x) for x in button_terms_multi}
    button_terms_compact = {_compact_normalized(x) for x in (button_terms_single | context_free_action_terms | button_terms_multi)}
    negative_terms_compact = {_compact_normalized(x) for x in (negative_terms_single | negative_terms_multi)}
    button_hint_confidence = max(18.0, min_confidence - 15.0)

    end_time = time.time() + timeout
    checks = 0
    last_blob = ""
    last_input_required = False
    last_busy = False
    region = None

    while time.time() < end_time:
        checks += 1

        if window_pattern:
            tool_activate_window(window_pattern)
            region = _get_window_region(window_pattern)

        screenshot = pyautogui.screenshot(region=region) if region else pyautogui.screenshot()
        try:
            data = pytesseract.image_to_data(
                screenshot,
                lang=lang,
                output_type=Output.DICT,
                config="--oem 3 --psm 6",
            )
        except Exception as exc:
            if allow_keyboard_fallback:
                try:
                    if window_pattern:
                        activation = tool_activate_window(window_pattern)
                        if isinstance(activation, dict) and not activation.get("success"):
                            return {
                                "success": False,
                                "checks": checks,
                                "window_pattern": window_pattern,
                                "method": "keyboard_fallback",
                                "note": "OCR calismadi; fallback denemesi yapilmadi cunku hedef pencere bulunamadi.",
                            }
                    pyautogui.hotkey("alt", "y")
                    time.sleep(0.1)
                    pyautogui.press("enter")
                    return {
                        "success": True,
                        "checks": checks,
                        "window_pattern": window_pattern,
                        "method": "keyboard_fallback",
                        "note": "OCR calismadigi icin klavye fallback denendi.",
                    }
                except Exception as fallback_exc:
                    return {"error": str(fallback_exc), "attempted_path": resolved_tesseract_cmd}
            return _build_tesseract_error(
                detail=str(exc),
                attempted_path=resolved_tesseract_cmd,
                configured_path=str(getattr(settings, "tesseract_cmd", "") or "").strip(),
            )

        words: List[Dict[str, Any]] = []
        blob_parts: List[str] = []
        raw_blob_parts: List[str] = []
        count = len(data.get("text", []))
        for i in range(count):
            raw = str(data["text"][i] or "").strip()
            if not raw:
                continue
            norm = _normalize_for_ocr_match(raw)
            if not norm:
                continue
            raw_blob_parts.append(norm)
            try:
                conf = float(data["conf"][i])
            except Exception:
                conf = -1.0
            token_is_button_like = _is_button_like_token(
                norm,
                button_terms_single=button_terms_single,
                context_free_action_terms=context_free_action_terms,
                button_terms_compact=button_terms_compact,
            )
            if conf < min_confidence and not (token_is_button_like and conf >= button_hint_confidence):
                continue
            words.append(
                {
                    "norm": norm,
                    "raw": raw,
                    "left": int(data["left"][i]),
                    "top": int(data["top"][i]),
                    "width": int(data["width"][i]),
                    "height": int(data["height"][i]),
                    "conf": conf,
                }
            )
            blob_parts.append(norm)

        blob = " ".join(blob_parts)
        raw_blob = " ".join(raw_blob_parts)
        compact_blob = re.sub(r"\s+", "", blob)
        last_blob = (raw_blob or blob)[:1800]
        last_input_required = _looks_like_input_required_text(last_blob)
        last_busy = _looks_like_ide_busy_text(last_blob)
        image_width = int(getattr(screenshot, "width", 0) or 0)
        image_height = int(getattr(screenshot, "height", 0) or 0)
        has_context = any(term in blob for term in context_terms)
        has_strict_context = any(term in blob for term in strict_context_terms)
        run_prompt_context_hit = any(term in blob for term in run_prompt_context_terms)
        if not words:
            time.sleep(interval)
            continue

        candidates: List[Dict[str, Any]] = []
        for i, current in enumerate(words):
            token = current["norm"]
            if _is_negative_decision(
                token,
                negative_single=negative_terms_single,
                negative_multi=negative_terms_multi,
                negative_compact=negative_terms_compact,
            ):
                continue
            if _is_button_like_token(
                token,
                button_terms_single=button_terms_single,
                context_free_action_terms=context_free_action_terms,
                button_terms_compact=button_terms_compact,
            ):
                candidates.append(current)

            if i + 1 < len(words):
                pair = f"{token} {words[i + 1]['norm']}"
                if _is_negative_decision(
                    pair,
                    negative_single=negative_terms_single,
                    negative_multi=negative_terms_multi,
                    negative_compact=negative_terms_compact,
                ):
                    continue
                if _is_button_like_phrase(
                    pair,
                    button_terms_multi=button_terms_multi,
                    button_terms_multi_compact=button_terms_multi_compact,
                    button_terms_compact=button_terms_compact,
                ):
                    left = min(current["left"], words[i + 1]["left"])
                    top = min(current["top"], words[i + 1]["top"])
                    right = max(current["left"] + current["width"], words[i + 1]["left"] + words[i + 1]["width"])
                    bottom = max(current["top"] + current["height"], words[i + 1]["top"] + words[i + 1]["height"])
                    candidates.append(
                        {
                            "norm": pair,
                            "raw": f"{current['raw']} {words[i + 1]['raw']}",
                            "left": left,
                            "top": top,
                            "width": max(1, right - left),
                            "height": max(1, bottom - top),
                            "conf": min(current["conf"], words[i + 1]["conf"]),
                        }
                    )

            if i + 2 < len(words):
                phrase3 = f"{token} {words[i + 1]['norm']} {words[i + 2]['norm']}"
                if _is_negative_decision(
                    phrase3,
                    negative_single=negative_terms_single,
                    negative_multi=negative_terms_multi,
                    negative_compact=negative_terms_compact,
                ):
                    continue
                if _is_button_like_phrase(
                    phrase3,
                    button_terms_multi=button_terms_multi,
                    button_terms_multi_compact=button_terms_multi_compact,
                    button_terms_compact=button_terms_compact,
                ):
                    left = min(current["left"], words[i + 1]["left"], words[i + 2]["left"])
                    top = min(current["top"], words[i + 1]["top"], words[i + 2]["top"])
                    right = max(
                        current["left"] + current["width"],
                        words[i + 1]["left"] + words[i + 1]["width"],
                        words[i + 2]["left"] + words[i + 2]["width"],
                    )
                    bottom = max(
                        current["top"] + current["height"],
                        words[i + 1]["top"] + words[i + 1]["height"],
                        words[i + 2]["top"] + words[i + 2]["height"],
                    )
                    candidates.append(
                        {
                            "norm": phrase3,
                            "raw": f"{current['raw']} {words[i + 1]['raw']} {words[i + 2]['raw']}",
                            "left": left,
                            "top": top,
                            "width": max(1, right - left),
                            "height": max(1, bottom - top),
                            "conf": min(current["conf"], words[i + 1]["conf"], words[i + 2]["conf"]),
                        }
                    )

        filtered_candidates: List[Dict[str, Any]] = []
        run_friendly_profiles = {"codex", "claudecode"}
        run_friendly = active_profile in run_friendly_profiles
        for c in candidates:
            norm_text = _normalize_for_ocr_match(str(c.get("norm", "")))
            if not norm_text:
                continue
            is_menu_term = _is_likely_menu_term(norm_text)
            compact_text = _compact_normalized(norm_text)
            if compact_text in _FORBIDDEN_APPROVAL_TERMS_COMPACT:
                continue
            if compact_text in _DEBUG_MENU_COMMAND_TERMS_COMPACT:
                continue
            if (compact_text.startswith("run") or "withoutdebugging" in compact_text) and not run_friendly:
                continue
            # VS Code ust menu / debug dropdown elemanlarini asla buton adayi yapma.
            # "1 Step Requires Input" aktifken bile menuye tiklama yanlisi olabiliyor.
            if is_menu_term and _in_top_menu_zone(c, image_height):
                continue
            if _in_top_menu_zone(c, image_height):
                # Ust menu/toolbar bolgesindeki adimlara tiklamak pratikte yanlis pozitif urettigi icin
                # bu bolgedeki tum adaylari disla.
                continue
            if (
                _is_ambiguous_approval_candidate(norm_text)
                and not has_strict_context
                and not run_prompt_context_hit
                and not _in_modal_action_zone(c, image_width, image_height)
            ):
                continue
            filtered_candidates.append(c)
        candidates = filtered_candidates

        # Claude Code "Allow this bash command?" ekraninda dogru secim birinci "Yes" opsiyonudur.
        # "Allow ..." secenegine tiklamak siklikla etkisiz kalabildigi icin yes adayini zorunlu onceliklendir.
        claude_bash_prompt_hit = (
            "allowthisbashcommand" in compact_blob
            or ("allowpython" in compact_blob and "forthisproject" in compact_blob)
        )
        if claude_bash_prompt_hit and candidates:
            yes_candidates = [c for c in candidates if _is_yes_like_candidate(str(c.get("norm", "")))]
            if yes_candidates:
                best_yes = sorted(
                    yes_candidates,
                    key=lambda c: (int(c.get("top", 0)), int(c.get("left", 0)), -float(c.get("conf", 0.0))),
                )[0]
                click_x = int(best_yes["left"] + (best_yes["width"] / 2))
                click_y = int(best_yes["top"] + (best_yes["height"] / 2))
                if region:
                    click_x += int(region[0])
                    click_y += int(region[1])
                pyautogui.click(click_x, click_y)
                return {
                    "success": True,
                    "checks": checks,
                    "window_pattern": window_pattern,
                    "clicked_text": best_yes["raw"],
                    "x": click_x,
                    "y": click_y,
                    "method": "ocr_click",
                    "profile": active_profile,
                    "score": 999.0,
                    "followup_clicked": False,
                    "followup_text": "",
                    "last_seen_text": last_blob,
                    "input_required_detected": last_input_required,
                    "busy_detected": last_busy,
                }

        should_click = bool(candidates and (has_strict_context or run_prompt_context_hit))
        hint_hit = False
        action_hit = False
        if not should_click and candidates:
            hint_hit = any(h in blob for h in context_free_hint_terms)
            action_hit = any(
                _is_button_like_token(
                    _normalize_for_ocr_match(str(c.get("norm", ""))),
                    button_terms_single=button_terms_single,
                    context_free_action_terms=context_free_action_terms,
                    button_terms_compact=button_terms_compact,
                )
                for c in candidates
            )
            should_click = bool(hint_hit and action_hit)

        if should_click and candidates:
            scored_candidates: List[Dict[str, Any]] = []
            for c in candidates:
                norm_text = _normalize_for_ocr_match(str(c.get("norm", "")))
                if _is_negative_decision(
                    norm_text,
                    negative_single=negative_terms_single,
                    negative_multi=negative_terms_multi,
                    negative_compact=negative_terms_compact,
                ):
                    continue
                c = dict(c)
                c["score"] = _score_approval_candidate(
                    c,
                    active_profile=active_profile,
                    has_context=has_context,
                    hint_hit=hint_hit,
                    run_prompt_context_hit=run_prompt_context_hit,
                    button_terms_multi=button_terms_multi,
                    button_terms_multi_compact=button_terms_multi_compact,
                )
                scored_candidates.append(c)
            if not scored_candidates:
                time.sleep(interval)
                continue
            best = sorted(scored_candidates, key=lambda c: c.get("score", 0.0), reverse=True)[0]

            click_x = int(best["left"] + (best["width"] / 2))
            click_y = int(best["top"] + (best["height"] / 2))
            if region:
                click_x += int(region[0])
                click_y += int(region[1])

            pyautogui.click(click_x, click_y)
            best_norm = _normalize_for_ocr_match(str(best.get("norm", "")))
            followup_clicked = False
            followup_text = ""
            if "expand" in best_norm:
                # Bazi ajanlarda once Expand, sonra Yes/Allow/Run butonu gorunur.
                try:
                    time.sleep(0.25)
                    screenshot2 = pyautogui.screenshot(region=region) if region else pyautogui.screenshot()
                    image2_height = int(getattr(screenshot2, "height", 0) or 0)
                    data2 = pytesseract.image_to_data(
                        screenshot2,
                        lang=lang,
                        output_type=Output.DICT,
                        config="--oem 3 --psm 6",
                    )
                    positives = {
                        "yes", "allow", "accept", "proceed", "ok",
                        "evet", "onay", "onayla", "kabul", "devam",
                        "run",
                    }
                    if not run_friendly:
                        positives.discard("run")
                    second_candidates: List[Dict[str, Any]] = []
                    count2 = len(data2.get("text", []))
                    for j in range(count2):
                        raw2 = str(data2["text"][j] or "").strip()
                        if not raw2:
                            continue
                        norm2 = _normalize_for_ocr_match(raw2)
                        if not norm2:
                            continue
                        if _is_negative_decision(
                            norm2,
                            negative_single=negative_terms_single,
                            negative_multi=negative_terms_multi,
                            negative_compact=negative_terms_compact,
                        ):
                            continue
                        compact2 = _compact_normalized(norm2)
                        if compact2 in _FORBIDDEN_APPROVAL_TERMS_COMPACT:
                            continue
                        candidate2 = {
                            "norm": norm2,
                            "raw": raw2,
                            "left": int(data2["left"][j]),
                            "top": int(data2["top"][j]),
                            "width": int(data2["width"][j]),
                            "height": int(data2["height"][j]),
                            "conf": float(data2["conf"][j]) if str(data2["conf"][j]).strip() else 0.0,
                        }
                        if _is_likely_menu_term(norm2):
                            continue
                        if _in_top_menu_zone(candidate2, image2_height):
                            continue
                        is_positive = norm2 in positives or norm2.startswith("allow") or norm2.startswith("accept")
                        if run_prompt_context_hit and run_friendly and norm2.startswith("run"):
                            is_positive = True
                        if is_positive:
                            second_candidates.append(candidate2)
                    if second_candidates:
                        second = sorted(second_candidates, key=lambda c: (c["top"], c["left"], c["conf"]), reverse=True)[0]
                        sx = int(second["left"] + (second["width"] / 2))
                        sy = int(second["top"] + (second["height"] / 2))
                        if region:
                            sx += int(region[0])
                            sy += int(region[1])
                        pyautogui.click(sx, sy)
                        followup_clicked = True
                        followup_text = str(second.get("raw", "")).strip()
                except Exception:
                    pass
            return {
                "success": True,
                "checks": checks,
                "window_pattern": window_pattern,
                "clicked_text": best["raw"],
                "x": click_x,
                "y": click_y,
                "method": "ocr_click",
                "profile": active_profile,
                "score": round(float(best.get("score", 0.0)), 2),
                "followup_clicked": followup_clicked,
                "followup_text": followup_text,
                "last_seen_text": last_blob,
                "input_required_detected": last_input_required,
                "busy_detected": last_busy,
            }

        # VS Code "1 Step Requires Input" modalinda Run butonu OCR'da kacinabiliyor.
        # Reject butonunu okuyabilirsek, Run butonu genellikle hemen sagindadir.
        if run_prompt_context_hit and words:
            reject_tokens = {"reject", "deny", "decline", "reddet", "iptal", "hayir", "no"}
            reject_candidates = [w for w in words if w.get("norm", "") in reject_tokens]
            if reject_candidates:
                rej = sorted(reject_candidates, key=lambda c: (c["conf"], c["top"], c["left"]), reverse=True)[0]
                rej_right = int(rej["left"] + rej["width"])
                click_x = int(rej_right + max(55, rej["width"] * 1.35))
                click_y = int(rej["top"] + (rej["height"] / 2))
                if region:
                    click_x += int(region[0])
                    click_y += int(region[1])
                try:
                    pyautogui.click(click_x, click_y)
                    return {
                        "success": True,
                        "checks": checks,
                        "window_pattern": window_pattern,
                        "method": "reject_offset_click",
                        "x": click_x,
                        "y": click_y,
                        "profile": active_profile,
                        "note": "Run butonu Reject referansi ile tahmini tiklandi.",
                    }
                except Exception:
                    pass

        # Ozellikle VS Code "Run Alt+J" akisinda OCR buton koordinati kacarsa,
        # gorunen kisayolu klavyeden deneyelim.
        run_altj_seen = ("runaltj" in compact_blob or "runaltj" in compact_blob.replace("+", ""))
        if run_altj_seen and run_friendly and (has_context or hint_hit or "debug" in compact_blob):
            try:
                pyautogui.hotkey("alt", "j")
                return {
                    "success": True,
                    "checks": checks,
                    "window_pattern": window_pattern,
                    "method": "keyboard_shortcut",
                    "shortcut": "alt+j",
                    "profile": active_profile,
                    "note": "OCR metninden Run Alt+J kisayolu algilandi.",
                }
            except Exception:
                pass

        time.sleep(interval)

    return {
        "success": False,
        "checks": checks,
        "window_pattern": window_pattern,
        "profile": active_profile,
        "message": "Onay penceresi tespit edilmedi.",
        "last_seen_text": last_blob,
        "input_required_detected": last_input_required,
        "busy_detected": last_busy,
    }


def _tesseract_ready() -> Tuple[bool, str]:
    try:
        import pytesseract
        status = _configure_tesseract_runtime(pytesseract)
        if status.get("ok"):
            return True, ""
        detail_parts = [
            str(status.get("error", "")).strip(),
            f"Denenen yol: {status.get('attempted_path', '')}".strip(),
            f"Kurulum: {status.get('install_path', '')}".strip(),
            f"Indirme: {status.get('install_url', '')}".strip(),
        ]
        detail = " | ".join(p for p in detail_parts if p and not p.endswith(":"))
        if status.get("detail"):
            detail = f"{detail} | Detay: {status.get('detail')}" if detail else f"Detay: {status.get('detail')}"
        return False, detail
    except Exception as exc:
        return False, str(exc)


def _approval_watcher_worker(
    window_pattern: str,
    interval: float,
    min_confidence: float,
    lang: str,
    profile: str,
    stop_event: threading.Event,
) -> None:
    # --- State Machine ---
    # States: WATCHING -> APPROVAL_CLICKED -> BUSY -> COMPLETED -> QUESTION_DETECTED
    WATCHING = "watching"
    APPROVAL_CLICKED = "approval_clicked"
    BUSY = "busy"
    COMPLETED = "completed"
    QUESTION_DETECTED = "question_detected"

    watcher_state = WATCHING
    question_notified = False

    # LLM screen analyzer import
    try:
        from .screen_analyzer import analyze_screen, ScreenState, ActionNeeded, reset_cache
        reset_cache()
        llm_available = True
    except Exception as exc:
        logger.warning("Approval watcher: screen_analyzer import hatasi: %s", exc)
        llm_available = False

    def _update_state(new_state: str, event_text: str = "") -> None:
        nonlocal watcher_state
        if watcher_state != new_state:
            old = watcher_state
            watcher_state = new_state
            logger.info(
                "Approval watcher state: %s -> %s | profile=%s",
                old, new_state, profile,
            )
        if event_text:
            _APPROVAL_WATCHER_STATE["last_event"] = event_text
        _APPROVAL_WATCHER_STATE["watcher_state"] = watcher_state

    def _send_notification_with_buttons(text: str, screenshot_path: str, buttons: list) -> bool:
        """Inline butonlu bildirim gonder. Basarisizsa fallback dene."""
        try:
            from ..notifier import notify_with_buttons
            if notify_with_buttons(text, buttons=buttons, photo_path=screenshot_path or None):
                return True
        except Exception:
            pass
        # Fallback: butonlar olmadan duz mesaj
        try:
            from ..notifier import notify
            if notify(text, file_path=screenshot_path or None):
                return True
        except Exception:
            pass
        sent, _ = _send_telegram_notification(
            text,
            photo_path=screenshot_path or "",
            buttons=buttons,
            parse_mode="HTML",
        )
        return sent

    # Expand profilleri (claudecode'da expand tiklanmaz)
    expand_profiles = {"gemini", "codex", "copilot", "kimicode"}

    while not stop_event.is_set():
        # ==================================================================
        # 1. OCR — sadece oku, hicbir seye tiklama
        # ==================================================================
        scan = _watcher_ocr_scan(window_pattern, lang, min_confidence)
        ocr_blob = scan.get("ocr_blob", "")

        if scan.get("error"):
            with _APPROVAL_WATCHER_LOCK:
                _APPROVAL_WATCHER_STATE["last_error"] = scan["error"][:240]
                if "tesseract" in scan["error"].lower():
                    stop_event.set()
            time.sleep(interval)
            continue

        with _APPROVAL_WATCHER_LOCK:
            _APPROVAL_WATCHER_STATE["checks"] = int(_APPROVAL_WATCHER_STATE.get("checks", 0)) + 1

        # ==================================================================
        # 2. ERKEN OCR TAMAMLANMA KONTROLU (LLM filtresi oncesi)
        # Strong/direct completion terimleri varsa LLM'e bakmadan bildir.
        # ==================================================================
        now_label = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if ocr_blob and not _looks_like_ide_busy_text(ocr_blob):
            blob_norm = _normalize_for_ocr_match(ocr_blob)
            _early_strong = sum(1 for t in _IDE_COMPLETION_STRONG_TERMS if _normalize_for_ocr_match(t) in blob_norm)
            _early_direct = sum(1 for t in _IDE_COMPLETION_DIRECT_TERMS if _normalize_for_ocr_match(t) in blob_norm)
            if _early_strong >= 1 or _early_direct >= 2:
                with _APPROVAL_WATCHER_LOCK:
                    already_sent = bool(_APPROVAL_WATCHER_STATE.get("completion_prompt_sent"))
                if not already_sent:
                    _update_state(COMPLETED, "OCR tamamlanma sinyali")
                    screenshot_path = _capture_completion_screenshot()
                    text = (
                        "<b>Görev tamamlandı.</b>\n"
                        "Ajan ekranında tamamlanmış yanıt görünüyor (OCR sinyali).\n\n"
                        "Onay izleyiciyi durdurayım mı?"
                    )
                    buttons = [[("Evet, durdur", "watcher_stop"), ("Hayır, devam et", "watcher_continue")]]
                    sent = _send_notification_with_buttons(text, screenshot_path, buttons)
                    with _APPROVAL_WATCHER_LOCK:
                        _APPROVAL_WATCHER_STATE["completion_detected"] = True
                        _APPROVAL_WATCHER_STATE["completion_prompt_sent"] = True
                        _APPROVAL_WATCHER_STATE["completion_reason"] = "ocr_early"
                        if sent:
                            _APPROVAL_WATCHER_STATE["last_notification_at"] = now_label
                    time.sleep(interval)
                    continue

        # ==================================================================
        # 3. LLM ANALIZ
        # ==================================================================
        llm = None
        if llm_available and ocr_blob:
            try:
                llm = analyze_screen(ocr_blob, profile=profile, timeout=30.0)
            except Exception as exc:
                logger.debug("Watcher LLM hatası: %s", exc)

        if not llm or llm.state == ScreenState.UNKNOWN or llm.confidence < 0.5:
            time.sleep(interval)
            continue

        with _APPROVAL_WATCHER_LOCK:
            _APPROVAL_WATCHER_STATE["llm_state"] = llm.state.value
            _APPROVAL_WATCHER_STATE["llm_confidence"] = round(llm.confidence, 2)
            _APPROVAL_WATCHER_STATE["llm_reasoning"] = llm.reasoning[:200]

        # ==================================================================
        # 4. LLM KARARINA GORE HAREKET ET
        # ==================================================================
        completion_by_ocr = _looks_like_ide_completion_text(ocr_blob) and not _looks_like_ide_busy_text(ocr_blob)
        llm_says_completion = llm.state == ScreenState.COMPLETED and llm.confidence >= 0.6
        should_notify_completion = llm_says_completion or (
            completion_by_ocr
            and llm.state not in (ScreenState.APPROVAL, ScreenState.INPUT_NEEDED, ScreenState.EXPAND, ScreenState.QUESTION)
        )

        # --- COMPLETED ---
        if should_notify_completion:
            with _APPROVAL_WATCHER_LOCK:
                already_sent = bool(_APPROVAL_WATCHER_STATE.get("completion_prompt_sent"))
            if not already_sent:
                reason_text = llm.reasoning[:80] if llm.reasoning else "Tamamlanma algilandi"
                _update_state(COMPLETED, reason_text)
                screenshot_path = _capture_completion_screenshot()
                summary = ""
                if llm.completion_summary:
                    summary = f"\n<b>Özet:</b> {llm.completion_summary[:200]}"
                elif completion_by_ocr:
                    summary = "\n<b>Özet:</b> Ajan ekranında tamamlanmış yanıt görünüyor."
                body_text = llm.reasoning[:200] if llm.reasoning else "Ajan artık çalışmıyor; tamamlanmış yanıt görünüyor."
                text = (
                    f"<b>Görev tamamlandı.</b>\n"
                    f"{body_text}{summary}\n\n"
                    "Onay izleyiciyi durdurayım mı?"
                )
                buttons = [[("Evet, durdur", "watcher_stop"), ("Hayır, devam et", "watcher_continue")]]
                sent = _send_notification_with_buttons(text, screenshot_path, buttons)
                with _APPROVAL_WATCHER_LOCK:
                    _APPROVAL_WATCHER_STATE["completion_detected"] = True
                    _APPROVAL_WATCHER_STATE["completion_prompt_sent"] = True
                    _APPROVAL_WATCHER_STATE["last_completion_text"] = ocr_blob[:300]
                    _APPROVAL_WATCHER_STATE["completion_reason"] = "llm" if llm_says_completion else "ocr"
                    if sent:
                        _APPROVAL_WATCHER_STATE["last_notification_at"] = now_label
                        logger.info("Completion bildirimi gonderildi | profile=%s conf=%.2f source=%s", profile, llm.confidence, "llm" if llm_says_completion else "ocr")
                    else:
                        _APPROVAL_WATCHER_STATE["notification_error"] = "Bildirim gonderilemedi"
                        logger.warning("Completion bildirimi basarisiz | profile=%s", profile)
                with _APPROVAL_WATCHER_LOCK:
                    if bool(_APPROVAL_WATCHER_STATE.get("auto_stop_on_completion")):
                        stop_event.set()

        # --- APPROVAL / INPUT_NEEDED ---
        elif llm.state in (ScreenState.APPROVAL, ScreenState.INPUT_NEEDED) and llm.confidence >= 0.65:
            if llm.action in (ActionNeeded.CLICK_BUTTON, ActionNeeded.CLICK_TEXT) and llm.target_text:
                try:
                    result = _click_text_on_active_window(
                        llm.target_text, window_pattern, lang, min_confidence
                    )
                    if result.get("success"):
                        _update_state(APPROVAL_CLICKED, f"LLM: {llm.target_text}")
                        with _APPROVAL_WATCHER_LOCK:
                            _APPROVAL_WATCHER_STATE["accepted"] = int(_APPROVAL_WATCHER_STATE.get("accepted", 0)) + 1
                            _APPROVAL_WATCHER_STATE["last_activity_at"] = now_label
                            _reset_completion_signal_unlocked()
                        question_notified = False
                        logger.info("Approval tıklandı: '%s' (conf=%.2f)", llm.target_text, llm.confidence)
                except Exception as exc:
                    logger.debug("Approval tıklama başarısız: %s", exc)

        # --- EXPAND ---
        elif llm.state == ScreenState.EXPAND and llm.confidence >= 0.65:
            if profile in expand_profiles and llm.target_text:
                try:
                    result = _click_text_on_active_window(
                        llm.target_text, window_pattern, lang, min_confidence
                    )
                    if result.get("success"):
                        _update_state(APPROVAL_CLICKED, f"Expand: {llm.target_text}")
                        with _APPROVAL_WATCHER_LOCK:
                            _APPROVAL_WATCHER_STATE["accepted"] = int(_APPROVAL_WATCHER_STATE.get("accepted", 0)) + 1
                            _APPROVAL_WATCHER_STATE["last_activity_at"] = now_label
                            _reset_completion_signal_unlocked()
                except Exception as exc:
                    logger.debug("Expand tıklama başarısız: %s", exc)

        # --- QUESTION ---
        elif llm.state == ScreenState.QUESTION and llm.confidence >= 0.6:
            if not question_notified:
                _update_state(QUESTION_DETECTED, llm.reasoning[:60])
                screenshot_path = _capture_completion_screenshot()
                q_text = f"<b>Ajan soru soruyor.</b>\n{llm.reasoning[:300]}\n"
                if llm.options:
                    q_text += "\n<b>Seçenekler:</b>\n"
                    for i, opt in enumerate(llm.options[:6], 1):
                        q_text += f"  {i}. {opt}\n"
                q_text += "\nEkran görüntüsüne bakıp seçim yapabilirsin."
                q_buttons = []
                if llm.options:
                    row = []
                    for i, opt in enumerate(llm.options[:4], 1):
                        label = opt[:20] if len(opt) <= 20 else opt[:18] + ".."
                        row.append((label, f"watcher_choice:{opt[:60]}"))
                    q_buttons.append(row)
                q_buttons.append([("Ekranı göster", "watcher_screenshot")])
                _send_notification_with_buttons(q_text, screenshot_path, q_buttons)
                question_notified = True

        # --- BUSY ---
        elif llm.state == ScreenState.BUSY:
            _update_state(BUSY, "Ajan çalışıyor...")
            with _APPROVAL_WATCHER_LOCK:
                _APPROVAL_WATCHER_STATE["last_busy_at"] = now_label
                _APPROVAL_WATCHER_STATE["last_activity_at"] = now_label
                # Ajan tekrar çalışıyorsa önceki completion kararını sıfırla
                if _APPROVAL_WATCHER_STATE.get("completion_prompt_sent"):
                    _reset_completion_signal_unlocked("Ajan tekrar çalışmaya başladı.")
            question_notified = False

        # --- IDLE ---
        elif llm.state == ScreenState.IDLE:
            _update_state(WATCHING, "İzleniyor")

        time.sleep(interval)

    with _APPROVAL_WATCHER_LOCK:
        _APPROVAL_WATCHER_STATE["running"] = False
        _APPROVAL_WATCHER_STATE["thread"] = None
        _APPROVAL_WATCHER_STATE["stop_event"] = None


def tool_start_approval_watcher(
    window_pattern: str = "Visual Studio Code|Code - Insiders",
    interval: float = 1.0,
    min_confidence: float = 30.0,
    lang: str = "tur+eng",
    profile: str = "generic",
    notify_on_completion: bool = True,
    auto_stop_on_completion: bool = False,
) -> Dict[str, Any]:
    """Arka planda IDE onay pencerelerini surekli izleyip otomatik kabul et."""
    interval = max(0.4, min(float(interval), 5.0))
    min_confidence = max(0.0, min(float(min_confidence), 100.0))
    profile_key = _normalize_for_ocr_match(profile or "generic") or "generic"
    if profile_key not in _APPROVAL_PROFILE_OVERRIDES:
        profile_key = "generic"
    notify_on_completion = bool(notify_on_completion)
    auto_stop_on_completion = bool(auto_stop_on_completion)

    ok, err = _tesseract_ready()
    if not ok:
        payload = _build_tesseract_error(detail=err[:260])
        return {"success": False, **payload}

    activation_result: Dict[str, Any] = {}
    if window_pattern:
        try:
            activation_result = tool_activate_window(window_pattern)
        except Exception as exc:
            activation_result = {"success": False, "error": str(exc)}

    with _APPROVAL_WATCHER_LOCK:
        thread = _APPROVAL_WATCHER_STATE.get("thread")
        if _APPROVAL_WATCHER_STATE.get("running") and isinstance(thread, threading.Thread) and thread.is_alive():
            status_snapshot = _approval_watcher_status_snapshot_unlocked()
            return {
                "success": True,
                "running": True,
                "message": "Onay izleyici zaten aktif.",
                "activation": activation_result,
                "status": status_snapshot,
            }

        stop_event = threading.Event()
        worker = threading.Thread(
            target=_approval_watcher_worker,
            args=(window_pattern, interval, min_confidence, lang, profile_key, stop_event),
            daemon=True,
            name="OpenWorldApprovalWatcher",
        )

        _APPROVAL_WATCHER_STATE["running"] = True
        _APPROVAL_WATCHER_STATE["thread"] = worker
        _APPROVAL_WATCHER_STATE["stop_event"] = stop_event
        _APPROVAL_WATCHER_STATE["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _APPROVAL_WATCHER_STATE["last_error"] = ""
        _APPROVAL_WATCHER_STATE["last_event"] = "Başlatıldı"
        _APPROVAL_WATCHER_STATE["window_pattern"] = window_pattern
        _APPROVAL_WATCHER_STATE["profile"] = profile_key
        _APPROVAL_WATCHER_STATE["interval"] = interval
        _APPROVAL_WATCHER_STATE["checks"] = 0
        _APPROVAL_WATCHER_STATE["accepted"] = 0
        _APPROVAL_WATCHER_STATE["notify_on_completion"] = notify_on_completion
        _APPROVAL_WATCHER_STATE["auto_stop_on_completion"] = auto_stop_on_completion
        _APPROVAL_WATCHER_STATE["completion_detected"] = False
        _APPROVAL_WATCHER_STATE["completion_prompt_sent"] = False
        _APPROVAL_WATCHER_STATE["completion_hits"] = 0
        _APPROVAL_WATCHER_STATE["last_completion_text"] = ""
        _APPROVAL_WATCHER_STATE["completion_reason"] = ""
        _APPROVAL_WATCHER_STATE["last_notification_at"] = ""
        _APPROVAL_WATCHER_STATE["notification_error"] = ""
        _APPROVAL_WATCHER_STATE["last_busy_at"] = ""
        _APPROVAL_WATCHER_STATE["last_activity_at"] = ""
        _APPROVAL_WATCHER_STATE["idle_clear_hits"] = 0
        _APPROVAL_WATCHER_STATE["idle_stable_hits"] = 0

        worker.start()

    time.sleep(min(max(interval, 0.6), 1.2))
    with _APPROVAL_WATCHER_LOCK:
        status_snapshot = _approval_watcher_status_snapshot_unlocked()

    return {
        "success": True,
        "running": True,
        "message": "Onay izleyici başlatıldı.",
        "window_pattern": window_pattern,
        "profile": profile_key,
        "interval": interval,
        "notify_on_completion": notify_on_completion,
        "auto_stop_on_completion": auto_stop_on_completion,
        "activation": activation_result,
        "status": status_snapshot,
    }


def tool_stop_approval_watcher() -> Dict[str, Any]:
    """Arka plandaki IDE onay izleyiciyi durdur."""
    thread: Optional[threading.Thread] = None
    stop_event: Optional[threading.Event] = None
    with _APPROVAL_WATCHER_LOCK:
        thread = _APPROVAL_WATCHER_STATE.get("thread")
        stop_event = _APPROVAL_WATCHER_STATE.get("stop_event")
        running = bool(_APPROVAL_WATCHER_STATE.get("running"))

    if not running:
        return {"success": True, "running": False, "message": "Onay izleyici zaten kapalı."}

    if isinstance(stop_event, threading.Event):
        stop_event.set()
    if isinstance(thread, threading.Thread) and thread.is_alive():
        thread.join(timeout=3.0)

    with _APPROVAL_WATCHER_LOCK:
        _APPROVAL_WATCHER_STATE["running"] = False
        _APPROVAL_WATCHER_STATE["thread"] = None
        _APPROVAL_WATCHER_STATE["stop_event"] = None
        _APPROVAL_WATCHER_STATE["last_event"] = "Durduruldu"

    return {"success": True, "running": False, "message": "Onay izleyici durduruldu."}


def tool_approval_watcher_status() -> Dict[str, Any]:
    """IDE onay izleyici durumunu getir."""
    with _APPROVAL_WATCHER_LOCK:
        return _approval_watcher_status_snapshot_unlocked()


def tool_ack_approval_completion_prompt(keep_running: bool = True) -> Dict[str, Any]:
    """Tamamlanma bildirimi sorusunu temizle (watcher acik kalabilir).

    NOT: completion_prompt_sent True olarak KALIR ki ayni ekran durumunda
    tekrar bildirim gonderilmesin. Sadece yeni bir aktivite (onay tiklama,
    busy durum) gorulurse sifirlanir (_reset_completion_signal_unlocked
    result.success icinde zaten cagriliyor).
    """
    with _APPROVAL_WATCHER_LOCK:
        running = bool(_APPROVAL_WATCHER_STATE.get("running"))
        # completion_detected ve completion_hits sifirla ama
        # completion_prompt_sent = True BIRAK → tekrar bildirim gonderilmesin
        _APPROVAL_WATCHER_STATE["completion_detected"] = False
        _APPROVAL_WATCHER_STATE["completion_hits"] = 0
        _APPROVAL_WATCHER_STATE["last_completion_text"] = ""
        _APPROVAL_WATCHER_STATE["completion_reason"] = ""
        # completion_prompt_sent SIFIRLANMIYOR — bu sayede ayni durum
        # tekrar algilandiginda bildirim GONDERILMEZ
        if keep_running and running:
            _APPROVAL_WATCHER_STATE["last_event"] = "Tamamlanma bildirimi geçildi, izleyici açık."
        else:
            _APPROVAL_WATCHER_STATE["last_event"] = "Tamamlanma bildirimi temizlendi."
    return {
        "success": True,
        "running": running,
        "completion_prompt_sent": True,
        "message": "Tamamlanma bildirimi onaylandı, izleyici devam ediyor.",
    }


# =============================================================================
# OCR (OPTIK KARAKTER TANIMA)
# =============================================================================

def tool_ocr_screenshot(region: List[int] = None, lang: str = "tur") -> Dict[str, Any]:
    """Ekran goruntusunden metin oku."""
    try:
        import pytesseract
        runtime = _configure_tesseract_runtime(pytesseract)
        if not runtime.get("ok"):
            return {k: v for k, v in runtime.items() if k != "ok"}

        # Ekran goruntusu al
        if region and len(region) == 4:
            screenshot = pyautogui.screenshot(region=tuple(region))
        else:
            screenshot = pyautogui.screenshot()
        
        # OCR yap
        text = pytesseract.image_to_string(screenshot, lang=lang)
        
        return {
            "text": text,
            "language": lang,
            "character_count": len(text),
            "tesseract_cmd": runtime.get("resolved_cmd", ""),
        }

    except Exception as e:
        err_text = str(e)
        if "tesseract" in err_text.lower():
            return _build_tesseract_error(
                detail=err_text,
                configured_path=str(getattr(settings, "tesseract_cmd", "") or "").strip(),
            )
        return {"error": err_text}


def tool_ocr_image(image_path: str, lang: str = "tur") -> Dict[str, Any]:
    """Goruntu dosyasindan metin oku."""
    try:
        import pytesseract
        from PIL import Image
        runtime = _configure_tesseract_runtime(pytesseract)
        if not runtime.get("ok"):
            return {k: v for k, v in runtime.items() if k != "ok"}

        image = Image.open(image_path)
        text = pytesseract.image_to_string(image, lang=lang)

        return {
            "text": text,
            "language": lang,
            "character_count": len(text),
            "tesseract_cmd": runtime.get("resolved_cmd", ""),
        }

    except Exception as e:
        err_text = str(e)
        if "tesseract" in err_text.lower():
            return _build_tesseract_error(
                detail=err_text,
                configured_path=str(getattr(settings, "tesseract_cmd", "") or "").strip(),
            )
        return {"error": err_text}


# =============================================================================
# EKRANDA METIN ARA VE TIKLA (OCR Click-by-Text)
# =============================================================================

def tool_click_text_on_screen(
    target_text: str,
    window_pattern: str = "Visual Studio Code|Code - Insiders",
    lang: str = "tur+eng",
    min_confidence: float = 25.0,
) -> Dict[str, Any]:
    """Ekranda belirtilen metni OCR ile bul ve ustune tikla. Fuzzy matching destekler.

    Args:
        target_text: Tiklanmasi istenen metin (buton, link, etiket vb.)
        window_pattern: Hedef pencere deseni (regex)
        lang: OCR dil ayari
        min_confidence: Minimum OCR guven esigi
    """
    if not target_text.strip():
        return {"error": "target_text (tiklanacak metin) gerekli."}
    try:
        return _click_text_on_active_window(
            target_text=target_text.strip(),
            window_pattern=window_pattern,
            lang=lang,
            min_confidence=min_confidence,
        )
    except Exception as exc:
        return {"error": f"Tiklama hatasi: {str(exc)[:200]}"}


# =============================================================================
# AJANA MESAJ YAZMA (Input Injection)
# =============================================================================

def tool_type_in_agent_input(
    agent: str = "codex",
    text: str = "",
    press_enter: bool = True,
) -> Dict[str, Any]:
    """VS Code'da çalışan bir AI ajan paneline odaklan ve mesaj yaz."""
    if not text.strip():
        return {"error": "text (yazılacak mesaj) gerekli."}

    try:
        result = run_vscode_agent_prompt(
            path=str(settings.workspace_path),
            agent=agent,
            prompt=text.strip(),
            press_enter=press_enter,
        )
    except ValueError as exc:
        return {"error": str(exc)}

    if not result.get("success"):
        return {
            "error": str(result.get("error", "Ajan girdisi yazılamadı.")),
            "detail": str(result.get("detail", "")),
            "agent": result.get("agent", agent),
            "ocr_text": result.get("ocr_text", ""),
        }

    return {
        "success": True,
        "agent": result.get("agent", agent),
        "text": text.strip()[:100],
        "enter_pressed": press_enter,
        "injection_method": result.get("injection_method", ""),
    }


def _type_unicode_text(text: str) -> None:
    """Clipboard uzerinden Unicode metin yaz."""
    if not text:
        return
    if text.isascii() and len(text) < 50:
        pyautogui.typewrite(text, interval=0.02)
        return
    if platform.system() == "Windows":
        p = subprocess.Popen(["clip.exe"], stdin=subprocess.PIPE)
        p.communicate(text.encode("utf-16-le"))
    elif platform.system() == "Darwin":
        p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        p.communicate(text.encode("utf-8"))
    else:
        p = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
        p.communicate(text.encode("utf-8"))
    time.sleep(0.05)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.05)


# =============================================================================
# EKRAN ANALIZI (LLM-powered)
# =============================================================================

def tool_analyze_screen(
    window_pattern: str = "Visual Studio Code|Code - Insiders",
    lang: str = "tur+eng",
    profile: str = "generic",
) -> Dict[str, Any]:
    """Ekrani OCR + LLM ile analiz et. Durumu, aksiyonu, butonu tanimla.

    Args:
        window_pattern: Hedef pencere deseni
        lang: OCR dil ayari
        profile: Ajan profili (gemini, codex, claudecode, kimicode, copilot, generic)
    """
    try:
        import pytesseract
        runtime = _configure_tesseract_runtime(pytesseract)
        if not runtime.get("ok"):
            return {k: v for k, v in runtime.items() if k != "ok"}
    except Exception as exc:
        return {"error": f"Tesseract bulunamadi: {exc}"}

    if window_pattern:
        tool_activate_window(window_pattern)
    region = _get_window_region(window_pattern) if window_pattern else None
    screenshot = pyautogui.screenshot(region=region) if region else pyautogui.screenshot()

    try:
        ocr_text = pytesseract.image_to_string(screenshot, lang=lang)
    except Exception as exc:
        return {"error": f"OCR hatasi: {exc}"}

    if not ocr_text.strip():
        return {"state": "idle", "action": "none", "ocr_text": "", "message": "Ekranda metin bulunamadi."}

    try:
        from .screen_analyzer import analyze_screen
        analysis = analyze_screen(ocr_text, profile=profile, force=True, timeout=30.0)
        if analysis:
            return {
                "state": analysis.state.value,
                "action": analysis.action.value,
                "target_text": analysis.target_text,
                "confidence": analysis.confidence,
                "reasoning": analysis.reasoning,
                "options": analysis.options,
                "completion_summary": analysis.completion_summary,
                "ocr_text": ocr_text[:1500],
            }
    except Exception as exc:
        logger.warning("tool_analyze_screen LLM analiz hatasi: %s", exc)

    return {
        "state": "unknown",
        "action": "none",
        "ocr_text": ocr_text[:1500],
        "message": "LLM analizi yapilamadi, OCR metni donduruldu.",
    }
