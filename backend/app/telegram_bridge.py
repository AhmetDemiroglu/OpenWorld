from __future__ import annotations

import atexit
import asyncio
import html as html_lib
import os
import re
from pathlib import Path

import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from .config import settings
from .secrets import decrypt_text

_LOCK_PATH = settings.data_path / "telegram_bridge.lock"
_LOCK_FD: int | None = None


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _acquire_single_instance_lock() -> None:
    global _LOCK_FD
    _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            _LOCK_FD = os.open(str(_LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(_LOCK_FD, str(os.getpid()).encode("ascii", errors="ignore"))
            return
        except FileExistsError:
            stale_pid = 0
            try:
                stale_pid = int(_LOCK_PATH.read_text(encoding="utf-8").strip())
            except Exception:
                stale_pid = 0
            if stale_pid and _pid_alive(stale_pid):
                raise RuntimeError(f"telegram_bridge zaten calisiyor (pid={stale_pid}).")
            try:
                _LOCK_PATH.unlink()
            except Exception:
                pass
    raise RuntimeError("telegram_bridge lock olusturulamadi.")


def _release_single_instance_lock() -> None:
    global _LOCK_FD
    try:
        if _LOCK_FD is not None:
            os.close(_LOCK_FD)
    except Exception:
        pass
    _LOCK_FD = None
    try:
        if _LOCK_PATH.exists():
            _LOCK_PATH.unlink()
    except Exception:
        pass


def markdown_to_telegram_html(text: str) -> str:
    """Convert markdown output to Telegram-safe HTML."""
    text = html_lib.escape(text)

    # Code blocks first.
    text = re.sub(
        r"```[\w]*\n(.*?)```",
        r"<pre>\1</pre>",
        text,
        flags=re.DOTALL,
    )

    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"^#{1,3}\s+(.+)$", r"\n<b>\1</b>", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)

    # Markdown table blocks to monospace.
    lines = text.split("\n")
    result: list[str] = []
    in_table = False
    table_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if "|" in stripped and stripped.startswith("|"):
            if not in_table:
                in_table = True
                table_lines = []
            if re.match(r"^\|[\s\-:|]+\|$", stripped):
                continue
            table_lines.append(stripped)
        else:
            if in_table:
                result.append("<pre>" + "\n".join(table_lines) + "</pre>")
                in_table = False
                table_lines = []
            result.append(line)
    if in_table:
        result.append("<pre>" + "\n".join(table_lines) + "</pre>")

    text = "\n".join(result)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


async def call_agent(session_id: str, text: str) -> dict:
    """Call agent API and return full response payload."""
    url = f"http://{settings.host}:{settings.port}/chat"
    payload = {"session_id": session_id, "message": text, "source": "telegram"}
    
    # Dinamik timeout - mesaj uzunluguna ve icerigine gore
    base_timeout = 60.0  # Temel timeout
    
    # Karmasik istekler icin daha uzun timeout
    text_lower = text.lower()
    if any(k in text_lower for k in ["arastir", "rapor", "detayli", "tum kaynak", "haber tara"]):
        base_timeout = 90.0  # Arastirma istekleri icin 90 saniye
    if any(k in text_lower for k in ["pdf", "word", "docx", "excel", "xlsx"]):
        base_timeout = 120.0  # Dosya olusturma icin 120 saniye
    
    try:
        # (connect, read, write, pool) timeout'lari
        timeout = httpx.Timeout(base_timeout, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            if resp.is_error:
                detail = ""
                try:
                    body = resp.json()
                    detail = str(body.get("detail", "")).strip()
                except Exception:
                    detail = resp.text[:1000].strip()
                if not detail:
                    detail = f"HTTP {resp.status_code} - {resp.reason_phrase}"
                raise RuntimeError(detail)
            return resp.json()
    except httpx.TimeoutException as exc:
        timeout_int = int(base_timeout)
        raise RuntimeError(
            f"Islem zaman asimina ugradi ({timeout_int}sn). "
            f"Bu istek turu icin maksimum sure: {timeout_int} saniye. "
            f"Daha kisa ve oz bir istek deneyin veya istegi parcalara bolun."
        ) from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(str(exc).strip() or exc.__class__.__name__) from exc


def _is_allowed(update: Update) -> bool:
    allowed = settings.telegram_allowed_user_id.strip()
    if not allowed:
        return False
    user = update.effective_user
    if user is None:
        return False
    return str(user.id) == allowed


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    if update.message is not None:
        await update.message.reply_text("OpenWorld aktif. Mesaj at, agent cevap versin.")


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    if update.message is None or not update.message.text:
        return

    session_id = f"telegram_{update.effective_user.id}"
    try:
        data = await call_agent(session_id, update.message.text)
        reply = data.get("reply", "")
        media_list = data.get("media") or []
    except Exception as exc:
        err_text = str(exc).strip()
        exc_type = type(exc).__name__
        if not err_text:
            err_text = exc_type
        # Yaygin hata turleri icin aciklayici Turkce mesajlar
        if "timeout" in err_text.lower() or "Timeout" in exc_type:
            err_text = f"Islem zaman asimina ugradi (420sn). Daha kisa bir istek deneyin. ({exc_type})"
        elif "ConnectError" in exc_type or "ConnectionRefused" in exc_type:
            err_text = "Agent sunucusuna baglanilamiyor. Backend calismiyor olabilir."
        elif "RSS" in err_text or "parse" in err_text.lower() or "XML" in err_text:
            err_text = f"Haber kaynagi hatasi: {err_text[:200]}"
        reply = f"Hata: {err_text[:500]}"
        media_list = []

    # Send media first.
    base_url = f"http://{settings.host}:{settings.port}"
    for m in media_list:
        media_url = m.get("url", "")
        media_type = m.get("type", "")
        caption = m.get("caption", m.get("filename", ""))
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=15.0)) as client:
                file_resp = await client.get(f"{base_url}{media_url}")
                if file_resp.status_code != 200:
                    continue
                file_bytes = file_resp.content

            filename = m.get("filename", "file")

            if media_type == "image":
                await update.message.reply_photo(photo=file_bytes, caption=caption[:1024], filename=filename)
            elif media_type == "audio":
                await update.message.reply_audio(audio=file_bytes, caption=caption[:1024], filename=filename)
            elif media_type == "video":
                await update.message.reply_video(video=file_bytes, caption=caption[:1024], filename=filename)
            else:
                await update.message.reply_document(document=file_bytes, caption=caption[:1024], filename=filename)
        except Exception:
            # Ignore media-send errors and continue with text.
            pass

    # Remove media links from text reply, since media already sent.
    if media_list:
        separator_idx = reply.find("\n\n---\n**Medya Dosyalari:**")
        if separator_idx != -1:
            reply = reply[:separator_idx].strip()

    if not reply.strip():
        return

    formatted = markdown_to_telegram_html(reply)
    if len(formatted) > 4000:
        formatted = formatted[:4000] + "..."

    try:
        await update.message.reply_text(
            formatted,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception:
        await update.message.reply_text(reply[:4000])


async def main() -> None:
    _acquire_single_instance_lock()
    atexit.register(_release_single_instance_lock)

    token = settings.telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token and settings.telegram_bot_token_enc:
        token = decrypt_text(settings.telegram_bot_token_enc)
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN missing in backend/.env")

    try:
        app = Application.builder().token(token).build()
        app.add_handler(CommandHandler("start", start_cmd))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        await asyncio.Event().wait()
    finally:
        _release_single_instance_lock()


if __name__ == "__main__":
    asyncio.run(main())
