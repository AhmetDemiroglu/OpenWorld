from __future__ import annotations

import asyncio
import html as html_lib
import os
import re

import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from .config import settings
from .secrets import decrypt_text


def markdown_to_telegram_html(text: str) -> str:
    """Convert markdown output to Telegram-safe HTML."""
    # Escape HTML entities first
    text = html_lib.escape(text)

    # Code blocks (before inline processing)
    text = re.sub(
        r"```[\w]*\n(.*?)```",
        r"<pre>\1</pre>",
        text,
        flags=re.DOTALL,
    )

    # Inline code
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)

    # Headers -> bold
    text = re.sub(r"^#{1,3}\s+(.+)$", r"\n<b>\1</b>", text, flags=re.MULTILINE)

    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)

    # Italic (single * not preceded/followed by *)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", text)

    # Links
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)

    # Convert markdown table blocks to monospace
    lines = text.split("\n")
    result = []
    in_table = False
    table_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if "|" in stripped and stripped.startswith("|"):
            if not in_table:
                in_table = True
                table_lines = []
            # Skip separator rows (|---|---|)
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

    # Clean up excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


async def call_agent(session_id: str, text: str) -> str:
    url = f"http://{settings.host}:{settings.port}/chat"
    payload = {"session_id": session_id, "message": text, "source": "telegram"}
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(url, json=payload)
        if resp.is_error:
            detail = ""
            try:
                body = resp.json()
                detail = str(body.get("detail", ""))
            except Exception:  # noqa: BLE001
                detail = resp.text[:500]
            raise RuntimeError(detail or f"HTTP {resp.status_code}")
        data = resp.json()
    return data.get("reply", "")


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
    await update.message.reply_text("OpenWorld aktif. Mesaj at, agent cevap versin.")


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    if update.message is None or not update.message.text:
        return
    session_id = f"telegram_{update.effective_user.id}"
    try:
        reply = await call_agent(session_id, update.message.text)
    except Exception as exc:  # noqa: BLE001
        reply = f"Hata: {exc}"
    formatted = markdown_to_telegram_html(reply)
    if len(formatted) > 4000:
        formatted = formatted[:4000] + "..."

    try:
        await update.message.reply_text(
            formatted,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception:  # noqa: BLE001
        # Fallback to plain text if HTML parsing fails
        await update.message.reply_text(reply[:4000])


async def main() -> None:
    token = settings.telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token and settings.telegram_bot_token_enc:
        token = decrypt_text(settings.telegram_bot_token_enc)
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN missing in backend/.env")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
