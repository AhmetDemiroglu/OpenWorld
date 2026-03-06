from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from ..config import settings

_VSCODE_WINDOW_PATTERN = "Visual Studio Code|Code - Insiders"
_DEFAULT_READY_TIMEOUT_SEC = 55.0
_OCR_POLL_INTERVAL_SEC = 1.2


@dataclass(frozen=True)
class AgentStrategy:
    key: str
    display_name: str
    extension_prefixes: tuple[str, ...]
    command_palette_sequence: tuple[str, ...]
    panel_shortcut: tuple[str, ...]
    warmup_timeout_sec: float
    ready_markers: tuple[str, ...]
    busy_markers: tuple[str, ...]
    blocked_markers: tuple[str, ...]


_AGENT_STRATEGIES: dict[str, AgentStrategy] = {
    "codex": AgentStrategy(
        key="codex",
        display_name="Codex",
        extension_prefixes=("openai.chatgpt-",),
        command_palette_sequence=("New Codex Agent",),
        panel_shortcut=("ctrl", "n"),
        warmup_timeout_sec=45.0,
        ready_markers=("codex", "new codex agent", "ask", "message", "chatgpt"),
        busy_markers=("thinking", "generating", "loading", "working"),
        blocked_markers=("copilot", "github copilot", "search", "extensions"),
    ),
    "claudecode": AgentStrategy(
        key="claudecode",
        display_name="Claude Code",
        extension_prefixes=("anthropic.claude-code-", "andrepimenta.claude-code-chat-"),
        command_palette_sequence=(
            "Claude Code: Open in Side Bar",
            "Claude Code: New Conversation",
            "Claude Code: Focus input",
        ),
        panel_shortcut=("ctrl", "escape"),
        warmup_timeout_sec=50.0,
        ready_markers=("claude", "conversation", "message", "input", "ask"),
        busy_markers=("thinking", "generating", "loading", "analyzing"),
        blocked_markers=("copilot", "github copilot", "extensions"),
    ),
    "kimicode": AgentStrategy(
        key="kimicode",
        display_name="Kimi Code",
        extension_prefixes=("moonshot-ai.kimi-code-",),
        command_palette_sequence=(
            "Kimi Code: Open in Side Panel",
            "Kimi Code: New Conversation",
            "Kimi Code: Focus Input",
        ),
        panel_shortcut=("ctrl", "shift", "k"),
        warmup_timeout_sec=45.0,
        ready_markers=("kimi", "kimi code", "message", "input", "conversation"),
        busy_markers=("thinking", "generating", "loading", "processing"),
        blocked_markers=("copilot", "github copilot", "extensions"),
    ),
}


def normalize_agent_key(agent: str) -> str:
    value = (agent or "").strip().lower()
    aliases = {
        "kimi": "kimicode",
        "kimi code": "kimicode",
        "kimicode": "kimicode",
        "claude": "claudecode",
        "claude code": "claudecode",
        "claudecode": "claudecode",
        "codex": "codex",
    }
    return aliases.get(value, value)


def get_agent_strategy(agent: str) -> AgentStrategy:
    key = normalize_agent_key(agent)
    if key not in _AGENT_STRATEGIES:
        supported = ", ".join(sorted(_AGENT_STRATEGIES))
        raise ValueError(f"Bilinmeyen ajan: {agent}. Desteklenen: {supported}")
    return _AGENT_STRATEGIES[key]


def resolve_workspace_path(path: str) -> str:
    if not path or path == ".":
        return str(settings.workspace_path)
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return str(candidate)
    return str((settings.workspace_path / candidate).resolve())


def find_code_executable() -> str:
    code_cmd = shutil.which("code") or shutil.which("code-insiders")
    if code_cmd:
        return code_cmd
    candidates = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Microsoft VS Code", "Code.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Microsoft VS Code Insiders", "Code - Insiders.exe"),
        os.path.join(os.environ.get("ProgramFiles", ""), "Microsoft VS Code", "Code.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Microsoft VS Code", "Code.exe"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return ""


def is_vscode_extension_installed(prefixes: Iterable[str]) -> bool:
    home = Path.home()
    roots = [
        home / ".vscode" / "extensions",
        home / ".vscode-insiders" / "extensions",
    ]
    normalized_prefixes = tuple(prefix.lower() for prefix in prefixes if prefix)
    if not normalized_prefixes:
        return False
    for root in roots:
        if not root.exists():
            continue
        for child in root.iterdir():
            name = child.name.lower()
            if any(name.startswith(prefix) for prefix in normalized_prefixes):
                return True
    return False


def _import_pyautogui():
    try:
        import pyautogui  # type: ignore
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("pyautogui kurulu değil.") from exc
    pyautogui.FAILSAFE = True
    return pyautogui


def _try_import_pytesseract():
    try:
        import pytesseract  # type: ignore
    except Exception:
        return None
    return pytesseract


def _activate_vscode_window() -> Dict[str, Any]:
    from .super_agent import tool_activate_window

    result = tool_activate_window(_VSCODE_WINDOW_PATTERN)
    if isinstance(result, dict) and result.get("success") is False:
        return result
    return {"success": True}


def _ocr_window_text(lang: str = "tur+eng") -> Dict[str, Any]:
    pyautogui = _import_pyautogui()
    pytesseract = _try_import_pytesseract()
    if pytesseract is None:
        return {
            "success": False,
            "ocr_available": False,
            "error": "OCR hazır değil. Tesseract/pytesseract bulunamadı.",
            "text": "",
        }
    try:
        screenshot = pyautogui.screenshot()
        text = pytesseract.image_to_string(screenshot, lang=lang)
        return {"success": True, "ocr_available": True, "text": text}
    except Exception as exc:
        return {
            "success": False,
            "ocr_available": True,
            "error": f"OCR başarısız: {str(exc)[:200]}",
            "text": "",
        }


def _normalize_for_match(text: str) -> str:
    translation = str.maketrans({
        "ç": "c",
        "ğ": "g",
        "ı": "i",
        "ö": "o",
        "ş": "s",
        "ü": "u",
        "Ç": "c",
        "Ğ": "g",
        "İ": "i",
        "Ö": "o",
        "Ş": "s",
        "Ü": "u",
    })
    return " ".join((text or "").lower().translate(translation).split())


def _window_looks_ready(text: str, strategy: AgentStrategy) -> bool:
    normalized = _normalize_for_match(text)
    if not normalized:
        return False
    has_ready = any(marker in normalized for marker in strategy.ready_markers)
    has_busy = any(marker in normalized for marker in strategy.busy_markers)
    has_blocked = any(marker in normalized for marker in strategy.blocked_markers)
    return has_ready and not has_blocked and not (has_busy and strategy.key != "codex")


def _wait_for_agent_ready(strategy: AgentStrategy, timeout_sec: float) -> Dict[str, Any]:
    pyautogui = _import_pyautogui()
    deadline = time.time() + max(5.0, timeout_sec)
    last_ocr: Dict[str, Any] = {"success": False, "ocr_available": False, "text": ""}
    while time.time() < deadline:
        _activate_vscode_window()
        last_ocr = _ocr_window_text()
        if last_ocr.get("success") and _window_looks_ready(str(last_ocr.get("text", "")), strategy):
            return {
                "success": True,
                "ocr_available": bool(last_ocr.get("ocr_available")),
                "ocr_text": str(last_ocr.get("text", ""))[:1000],
            }
        pyautogui.hotkey("ctrl", "1")
        time.sleep(0.2)
        pyautogui.hotkey(*strategy.panel_shortcut)
        time.sleep(_OCR_POLL_INTERVAL_SEC)
    error = str(last_ocr.get("error", "")).strip() or "Hedef ajan input alanı doğrulanamadı."
    return {
        "success": False,
        "ocr_available": bool(last_ocr.get("ocr_available")),
        "ocr_text": str(last_ocr.get("text", ""))[:1000],
        "error": error,
    }


def _copy_text_to_clipboard(text: str) -> None:
    import subprocess as _subprocess

    if os.name == "nt":
        proc = _subprocess.Popen(["clip.exe"], stdin=_subprocess.PIPE)
        proc.communicate(text.encode("utf-16-le"))
        return
    raise RuntimeError("Bu platform için clipboard desteği tanımlı değil.")


def _inject_text(text: str) -> Dict[str, Any]:
    pyautogui = _import_pyautogui()
    content = text.strip()
    if not content:
        return {"success": False, "error": "Gönderilecek metin boş."}
    try:
        if content.isascii() and len(content) <= 120 and "\n" not in content:
            pyautogui.typewrite(content, interval=0.01)
            method = "typewrite"
        else:
            _copy_text_to_clipboard(content)
            time.sleep(0.05)
            pyautogui.hotkey("ctrl", "v")
            method = "clipboard"
        return {"success": True, "method": method}
    except Exception as exc:
        return {"success": False, "error": f"Metin enjekte edilemedi: {str(exc)[:200]}"}


def open_in_vscode(path: str, goto_line: int = 0) -> Dict[str, Any]:
    code_exe = find_code_executable()
    if not code_exe:
        return {"success": False, "error": "VS Code bulunamadı. Kurulumu veya PATH ayarını kontrol edin."}

    resolved = resolve_workspace_path(path)
    target = Path(resolved)
    if not target.exists():
        return {"success": False, "error": "Dosya veya klasör bulunamadı.", "path": resolved}

    cmd = [code_exe]
    if goto_line > 0 and target.is_file():
        cmd.extend(["--goto", f"{resolved}:{goto_line}"])
    else:
        cmd.append(resolved)
    subprocess.Popen(cmd, shell=False)
    return {"success": True, "path": resolved, "code_exe": code_exe}


def run_vscode_agent_prompt(
    *,
    path: str,
    agent: str,
    prompt: str,
    press_enter: bool = True,
    timeout_sec: float = _DEFAULT_READY_TIMEOUT_SEC,
) -> Dict[str, Any]:
    strategy = get_agent_strategy(agent)
    if not is_vscode_extension_installed(strategy.extension_prefixes):
        return {
            "success": False,
            "error": "eklenti yok",
            "detail": f"{strategy.display_name} eklentisi bulunamadı.",
            "agent": strategy.key,
        }

    open_result = open_in_vscode(path)
    if not open_result.get("success"):
        return {
            "success": False,
            "error": "yanlış pencere",
            "detail": str(open_result.get("error", "VS Code açılamadı.")),
            "agent": strategy.key,
        }

    pyautogui = _import_pyautogui()
    time.sleep(1.0)
    activated = _activate_vscode_window()
    if activated.get("success") is False:
        return {
            "success": False,
            "error": "yanlış pencere",
            "detail": str(activated.get("error", "VS Code penceresi bulunamadı.")),
            "agent": strategy.key,
        }

    pyautogui.press("esc")
    time.sleep(0.1)

    for command_text in strategy.command_palette_sequence:
        pyautogui.hotkey("ctrl", "shift", "p")
        time.sleep(0.25)
        inject_result = _inject_text(command_text)
        if not inject_result.get("success"):
            return {
                "success": False,
                "error": "gönderim doğrulanamadı",
                "detail": str(inject_result.get("error", "Komut paleti metni yazılamadı.")),
                "agent": strategy.key,
            }
        pyautogui.press("enter")
        time.sleep(0.8)

    ready_result = _wait_for_agent_ready(strategy, timeout_sec=max(strategy.warmup_timeout_sec, timeout_sec))
    if not ready_result.get("success"):
        error = "OCR hazır değil" if not ready_result.get("ocr_available") else "input bulunamadı"
        return {
            "success": False,
            "error": error,
            "detail": str(ready_result.get("error", "Ajan input alanı doğrulanamadı.")),
            "agent": strategy.key,
            "ocr_text": ready_result.get("ocr_text", ""),
        }

    inject_result = _inject_text(prompt[:3500])
    if not inject_result.get("success"):
        return {
            "success": False,
            "error": "gönderim doğrulanamadı",
            "detail": str(inject_result.get("error", "Mesaj yazılamadı.")),
            "agent": strategy.key,
        }

    if press_enter:
        pyautogui.press("enter")

    return {
        "success": True,
        "agent": strategy.key,
        "display_name": strategy.display_name,
        "path": open_result.get("path", ""),
        "injection_method": inject_result.get("method", ""),
        "ocr_text": ready_result.get("ocr_text", ""),
        "press_enter": press_enter,
    }
