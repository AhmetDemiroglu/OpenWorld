"""
notifier.py — Arka plan thread'lerinden Telegram'a guvenli mesaj/dosya gondermek icin
thread-safe singleton. Ana event loop'a run_coroutine_threadsafe ile gorev iletir.

Kullanim:
    # telegram_bridge.py'de:
    from .notifier import set_context
    set_context(app.bot, chat_id, loop)

    # Background thread'den:
    from .notifier import notify
    notify("Arastirma tamamlandi!", file_path="/path/to/report.pdf")
"""
from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_bot = None
_chat_id: Optional[str] = None
_loop: Optional[asyncio.AbstractEventLoop] = None


def set_context(bot, chat_id: str, loop: asyncio.AbstractEventLoop) -> None:
    """telegram_bridge.main() icinden cagrilir; notifier'i hazir hale getirir."""
    global _bot, _chat_id, _loop
    with _lock:
        _bot = bot
        _chat_id = str(chat_id)
        _loop = loop
    logger.info("[Notifier] Telegram bildirim kanali hazir. chat_id=%s", chat_id)


def _is_ready() -> bool:
    with _lock:
        return _bot is not None and _chat_id is not None and _loop is not None


async def _send_text(text: str) -> None:
    """Async: sadece metin gonder."""
    try:
        # Telegram mesaj limiti 4096 karakter
        chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
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


def notify(text: str, file_path: Optional[str] = None) -> None:
    """
    Herhangi bir thread'den cagirilir; mesaji ve/veya dosyayi Telegram'a iletir.
    Bloklamaz — fire-and-forget olarak cagirilir.
    """
    if not _is_ready():
        logger.warning("[Notifier] Henuz hazir degil. Mesaj atilamadi: %s", text[:80])
        return

    with _lock:
        bot = _bot
        chat_id = _chat_id
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
        asyncio.run_coroutine_threadsafe(_task(), loop)
    except Exception as exc:
        logger.error("[Notifier] Coroutine iletilemedi: %s", exc)
