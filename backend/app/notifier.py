"""
notifier.py - Arka plan thread'lerinden Telegram'a guvenli mesaj/dosya gondermek icin
thread-safe singleton. Ana event loop'a run_coroutine_threadsafe ile gorev iletir.

Kullanim:
    # telegram_bridge.py'de:
    from .notifier import set_context
    set_context(app.bot, chat_id, loop)

    # Background thread'den:
    from .notifier import notify
    notify("Arastirma tamamlandi!", file_path="/path/to/report.pdf")

    # Inline butonlu bildirim:
    from .notifier import notify_with_buttons
    future = notify_with_buttons("Gorev bitti. Durdurayim mi?", buttons=[
        [("Durdur", "watcher_stop"), ("Devam", "watcher_continue")],
    ], photo_path="/path/to/screenshot.png")

    # Screenshot foto olarak gonder:
    from .notifier import notify_photo
    notify_photo("/path/to/screenshot.png", caption="Ekran goruntusu")
"""
from __future__ import annotations

import asyncio
import io
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_bot = None
_chat_id: Optional[str] = None
_loop: Optional[asyncio.AbstractEventLoop] = None
_pending_messages: list[tuple[str, Optional[str]]] = []
_MAX_PENDING_MESSAGES = 100


def set_context(bot, chat_id: str, loop: asyncio.AbstractEventLoop) -> None:
    """telegram_bridge.main() icinden cagrilir; notifier'i hazir hale getirir."""
    global _bot, _chat_id, _loop
    pending: list[tuple[str, Optional[str]]] = []
    with _lock:
        _bot = bot
        _chat_id = str(chat_id)
        _loop = loop
        if _pending_messages:
            pending = list(_pending_messages)
            _pending_messages.clear()

    logger.info("[Notifier] Telegram bildirim kanali hazir. chat_id=%s", chat_id)

    if pending:
        logger.info("[Notifier] Bekleyen bildirimler gonderiliyor: %d", len(pending))
        for text, file_path in pending:
            _dispatch(text, file_path)


def _is_ready() -> bool:
    with _lock:
        return _bot is not None and _chat_id is not None and _loop is not None


async def _send_text(text: str) -> None:
    """Async: sadece metin gonder."""
    try:
        chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)]
        for chunk in chunks:
            await _bot.send_message(
                chat_id=_chat_id,
                text=chunk,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
    except Exception as exc:
        logger.error("[Notifier] Metin gonderme hatasi: %s", exc)


async def _send_file(file_path: Path, caption: str) -> None:
    """Async: dosya gonder (PDF, DOCX, TXT vs.)."""
    try:
        with open(file_path, "rb") as fh:
            await _bot.send_document(
                chat_id=_chat_id,
                document=fh,
                filename=file_path.name,
                caption=caption[:1024] if caption else file_path.name,
            )
    except Exception as exc:
        logger.error("[Notifier] Dosya gonderme hatasi (%s): %s", file_path, exc)


def _dispatch(text: str, file_path: Optional[str] = None) -> None:
    with _lock:
        loop = _loop

    async def _task():
        await _send_text(text)
        if file_path:
            p = Path(file_path)
            if p.exists() and p.is_file():
                await _send_file(p, caption=f"📎 {p.name}")
            else:
                logger.warning("[Notifier] Dosya bulunamadi: %s", file_path)

    try:
        if loop is None:
            raise RuntimeError("Notifier loop hazir degil")
        asyncio.run_coroutine_threadsafe(_task(), loop)
    except Exception as exc:
        logger.error("[Notifier] Coroutine iletilemedi: %s", exc)


def notify(text: str, file_path: Optional[str] = None) -> bool:
    """
    Herhangi bir thread'den cagirilir; mesaji ve/veya dosyayi Telegram'a iletir.
    Bloklamaz - fire-and-forget olarak cagirilir.
    """
    if not _is_ready():
        with _lock:
            if len(_pending_messages) >= _MAX_PENDING_MESSAGES:
                _pending_messages.pop(0)
            _pending_messages.append((text, file_path))
        logger.warning("[Notifier] Henuz hazir degil. Mesaj kuyruga alindi: %s", text[:80])
        return False

    _dispatch(text, file_path)
    return True


# ---------------------------------------------------------------------------
# Foto gonderme (screenshot icin)
# ---------------------------------------------------------------------------
async def _send_photo(photo_path: Path, caption: str = "") -> None:
    """Async: foto olarak gonder (screenshot icin ideal)."""
    try:
        with open(photo_path, "rb") as fh:
            await _bot.send_photo(
                chat_id=_chat_id,
                photo=fh,
                caption=caption[:1024] if caption else "",
            )
    except Exception as exc:
        logger.error("[Notifier] Foto gonderme hatasi (%s): %s", photo_path, exc)


def notify_photo(photo_path: str, caption: str = "") -> bool:
    """Background thread'den screenshot/foto gonder (fire-and-forget)."""
    if not _is_ready():
        logger.warning("[Notifier] Henuz hazir degil. Foto gonderilemedi: %s", photo_path)
        return False

    p = Path(photo_path)
    if not p.exists() or not p.is_file():
        logger.warning("[Notifier] Foto bulunamadi: %s", photo_path)
        return False

    with _lock:
        loop = _loop

    try:
        if loop is None:
            raise RuntimeError("Notifier loop hazir degil")
        asyncio.run_coroutine_threadsafe(_send_photo(p, caption), loop)
        return True
    except Exception as exc:
        logger.error("[Notifier] Foto coroutine iletilemedi: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Inline butonlu bildirim (watcher completion, soru/secenek icin)
# ---------------------------------------------------------------------------
async def _send_with_buttons(
    text: str,
    buttons: List[List[Tuple[str, str]]],
    photo_path: Optional[Path] = None,
) -> None:
    """Async: inline keyboard butonlu mesaj gonder, opsiyonel olarak once foto gonder."""
    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    except ImportError:
        logger.error("[Notifier] python-telegram-bot kurulu degil, butonlu mesaj gonderilemedi.")
        await _send_text(text)
        return

    # Once foto gonder
    if photo_path and photo_path.exists() and photo_path.is_file():
        await _send_photo(photo_path, caption="")

    # Inline keyboard olustur
    keyboard_rows = []
    for row in buttons:
        keyboard_rows.append([
            InlineKeyboardButton(label, callback_data=cb_data)
            for label, cb_data in row
        ])
    markup = InlineKeyboardMarkup(keyboard_rows)

    chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)]
    for i, chunk in enumerate(chunks):
        # Sadece son chunk'a buton ekle
        rm = markup if i == len(chunks) - 1 else None
        await _bot.send_message(
            chat_id=_chat_id,
            text=chunk,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=rm,
        )


def notify_with_buttons(
    text: str,
    buttons: List[List[Tuple[str, str]]],
    photo_path: Optional[str] = None,
) -> bool:
    """
    Background thread'den inline butonlu mesaj gonder.

    Args:
        text: Mesaj metni (HTML)
        buttons: [[("Buton Metni", "callback_data"), ...], ...]  (satir satir)
        photo_path: Opsiyonel screenshot/foto yolu (once foto, sonra butonlu mesaj)
    """
    if not _is_ready():
        logger.warning("[Notifier] Henuz hazir degil. Butonlu mesaj gonderilemedi.")
        return False

    pp = Path(photo_path) if photo_path else None

    with _lock:
        loop = _loop

    try:
        if loop is None:
            raise RuntimeError("Notifier loop hazir degil")
        future = asyncio.run_coroutine_threadsafe(
            _send_with_buttons(text, buttons, photo_path=pp),
            loop,
        )
        future.add_done_callback(lambda f: f.exception())
        return True
    except Exception as exc:
        logger.error("[Notifier] Butonlu mesaj coroutine iletilemedi: %s", exc)
        return False
