from __future__ import annotations

import atexit
import asyncio
import html as html_lib
import io
import logging
import os
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import settings
from .secrets import decrypt_text

_LOCK_PATH = settings.data_path / "telegram_bridge.lock"
_LOCK_FD: int | None = None
_TIMEOUT_NOTEBOOK_HINT_CACHE: dict[str, str] = {}
_LATEST_REQUEST_TOKENS: dict[str, int] = {}

# ─── Rate limiter (BLOK 8) ───────────────────────────────────────────────────
_rate_window: dict[str, list] = defaultdict(list)
_RATE_MAX = 10  # 60 saniyede max komut


def _check_rate_limit(user_id: str) -> bool:
    now = time.time()
    history = _rate_window[user_id]
    history[:] = [t for t in history if now - t < 60]
    if len(history) >= _RATE_MAX:
        return False
    history.append(now)
    return True


# ─── Audit log (BLOK 8) ──────────────────────────────────────────────────────
_audit_logger = logging.getLogger("openworld.audit")


def _audit(user_id: str, cmd: str, status: str = "ok") -> None:
    _audit_logger.info("[AUDIT] user=%s cmd=%r status=%s", user_id, cmd[:120], status)


# ─── Onay akışı durumu (BLOK 4) ──────────────────────────────────────────────
_pending_approvals: dict[str, "asyncio.Future"] = {}


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
        r"```[\w]*\n(.*...)```",
        r"<pre>\1</pre>",
        text,
        flags=re.DOTALL,
    )

    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"^#{1,3}\s+(.+)$", r"\n<b>\1</b>", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.+...)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(...<!\*)\*([^*]+)\*(...!\*)", r"<i>\1</i>", text)
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


def _normalize_tr(text: str) -> str:
    tr_map = {
        0x00E7: "c",  # ç
        0x011F: "g",  # ş
        0x0131: "i",  # ı
        0x00F6: "o",  # ö
        0x015F: "s",  # ş
        0x00FC: "u",  # ü
        0x00C7: "c",  # Ç
        0x011E: "g",  # Ğ
        0x0130: "i",  # İ
        0x00D6: "o",  # Ö
        0x015E: "s",  # Ş
        0x00DC: "u",  # Ü
    }
    return (text or "").lower().translate(tr_map)


def _build_fast_chat_reply(text: str) -> str:
    normalized = _normalize_tr(text).strip()
    if not normalized:
        return ""

    words = [word for word in normalized.split() if word]
    if len(words) > 8:
        return ""

    greeting_tokens = {
        "selam", "merhaba", "slm", "selamlar", "gunaydin", "iyi aksamlar", "iyi geceler",
    }
    thanks_tokens = {"tesekkurler", "tesekkur ederim", "sag ol", "saol", "eyvallah"}
    doing_patterns = (
        "napiyorsun",
        "ne yapiyorsun",
        "neler yapiyorsun",
        "su an ne yapiyorsun",
        "simdi ne yapiyorsun",
        "sen ne yapiyorsun",
        "bugun ne yapiyorsun",
        "ne yapiyorsun su an",
    )
    status_patterns = (
        "nasilsin",
        "nasil gidiyor",
        "naber",
        "ne haber",
        "iyi misin",
        "keyfin nasil",
    )
    mutual_status_patterns = (
        "iyiyim sen nasilsin",
        "ben iyiyim sen",
        "iyiyim sen",
    )

    if normalized in greeting_tokens:
        return "Selam. Nasıl yardımcı olabilirim?"
    if normalized in thanks_tokens:
        return "Rica ederim."
    if normalized in {"iyiyim", "ben de iyiyim", "iyi"}:
        return "Güzel. Ne yapmamı istiyorsun?"
    if any(pattern in normalized for pattern in mutual_status_patterns):
        return "Ben de iyiyim. Ne yapmamı istiyorsun?"
    if any(pattern in normalized for pattern in status_patterns):
        return "İyiyim. Ne yapmamı istiyorsun?"
    if any(pattern in normalized for pattern in doing_patterns):
        return "Buradayım ve hazırım. Ne yapmamı istiyorsun?"
    return ""


def _should_show_thinking_indicator(text: str, has_media: bool = False) -> bool:
    if has_media:
        return True
    return bool((text or "").strip())


def _get_timeout_for_request(text: str) -> httpx.Timeout:
    """İstek turune gore timeout belirle."""
    text_lower = _normalize_tr(text)
    def _mk_timeout(read_sec: float, connect_sec: float = 10.0) -> httpx.Timeout:
        read_sec = max(20.0, float(read_sec))
        connect_sec = max(3.0, min(float(connect_sec), read_sec / 2))
        write_sec = max(5.0, min(connect_sec, 15.0))
        pool_sec = max(5.0, min(connect_sec, 15.0))
        return httpx.Timeout(connect=connect_sec, read=read_sec, write=write_sec, pool=pool_sec)

    # Durdurma/iptal komutlari kilitli durumda bile hizli donmeli.
    if any(k in text_lower for k in ("islemi durdur", "gorevi durdur", "iptal et", "hepsini durdur", "stop")):
        return _mk_timeout(35.0, 5.0)
    
    # GORSEL ISLEME: OCR + analiz uzun surebilir (3 dakika)
    if "gorsel" in text_lower or "[kullanici bir gorsel" in text_lower:
        return _mk_timeout(180.0, 10.0)
    
    # HIZLI ISLEMLER: Direkt calisir, kisa timeout yeterli
    fast_patterns = [
        "ekran goruntusu", "screenshot", "desktop", "masaustu",
        "webcam", "web cam", "kamera", "fotograf cek",
        "selfie", "anlik foto", "camera",
        "ses kaydet", "ses kaydi", "mikrofon", "audio record", "voice record",
        "video kaydet", "video cek", "webcam video"
    ]
    if any(p in text_lower for p in fast_patterns):
        return _mk_timeout(float(max(35, int(getattr(settings, "telegram_timeout_fast_sec", 45)))), 5.0)
    
    # NOTEBOOK DEVAM ETME: Cok uzun surebilir (5 dakika)
    if any(p in text_lower for p in ["devam et", "not defter", "rapora devam", "raporuna devam"]):
        return _mk_timeout(float(max(240, int(getattr(settings, "telegram_timeout_resume_sec", 420)))), 10.0)
    
    # MASAUSTU OTOMASYON: VS Code, Codex (30 saniye yeterli)
    automation_patterns = [
        "vscode", "vs code", "codex", "copilot",
        "kimicode", "kimi code", "claude code",
        "programi ac", "uygulamayi ac",
        "tikla", "yaz ve", "bul ve",
        "onay", "kabul", "izin ver", "approve", "allow",
    ]
    if any(p in text_lower for p in automation_patterns) and any(
        p in text_lower for p in ["ac", "bul", "yaz", "tikla", "gir", "git", "onay", "kabul", "izin"]
    ):
        return _mk_timeout(float(max(120, int(getattr(settings, "telegram_timeout_automation_sec", 240)))), 8.0)
    
    # ARASTIRMA ISLEMLERI: Uzun surebilir (5 dakika)
    # Sadece acik arastirma niyeti — "rapor", "analiz" gibi genel kelimeler dahil degil
    research_patterns = ["arastirma yap", "internette ara", "web'de ara", "haber tara",
                        "haberleri tara", "kaynak bul", "makale bul"]
    if any(p in text_lower for p in research_patterns):
        return _mk_timeout(float(max(300, int(getattr(settings, "telegram_timeout_research_sec", 420)))), 10.0)
    
    # STANDART: qwen dusunme sureci icin daha genis pencere
    return _mk_timeout(float(max(180, int(getattr(settings, "telegram_timeout_default_sec", 300)))), 10.0)


async def call_agent(session_id: str, text: str) -> dict:
    """Call agent API and return full response payload."""
    url = f"http://{settings.host}:{settings.port}/chat"
    payload = {"session_id": session_id, "message": text, "source": "telegram"}
    
    # İstek turune gore timeout belirle
    timeout = _get_timeout_for_request(text)
    
    try:
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
        read_sec = getattr(timeout, "read", None)
        read_hint = f" (~{int(read_sec)} sn)" if isinstance(read_sec, (int, float)) else ""
        raise RuntimeError(
            f"Islem zaman asimina ugradi{read_hint}.\n\n"
            "Olası nedenler:\n"
            "- Cok karmasik bir islem istediniz\n"
            "- Sistem yogun\n"
            "- LLM uzun sure dusunuyor olabilir\n\n"
            "Oneriler:\n"
            "1. Ayni istegi tekrar gonderin\n"
            "2. \"devam et\" yazarak kaldigi yerden surdurmeyi deneyin\n"
            "3. Gerekirse istegi parcalara bolun"
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


# ─── BLOK 2: /ekran ──────────────────────────────────────────────────────────

async def ekran_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/ekran [x y w h] — Ekran görüntüsü al, Telegram'a fotoğraf olarak gönder."""
    if not _is_allowed(update):
        return
    user_id = str(update.effective_user.id)
    if not _check_rate_limit(user_id):
        await update.message.reply_text("⏳ Çok fazla komut. Biraz bekle.")
        return
    _audit(user_id, f"/ekran {' '.join(context.args or [])}")
    status = await update.message.reply_text("📸 Ekran görüntüsü alınıyor...")
    try:
        import pyautogui
        args = context.args or []
        if len(args) == 4:
            region = (int(args[0]), int(args[1]), int(args[2]), int(args[3]))
            shot = pyautogui.screenshot(region=region)
        else:
            shot = pyautogui.screenshot()
        buf = io.BytesIO()
        shot.save(buf, format="PNG")
        buf.seek(0)
        await status.delete()
        await update.message.reply_photo(photo=buf, caption="📸 Ekran görüntüsü")
    except Exception as exc:
        await status.edit_text(f"❌ Ekran hatası: {exc}")


# ─── BLOK 3: /tikla, /yaz, /tus ─────────────────────────────────────────────

async def tikla_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/tikla X Y — Verilen koordinata sol tıkla."""
    if not _is_allowed(update):
        return
    user_id = str(update.effective_user.id)
    if not _check_rate_limit(user_id):
        await update.message.reply_text("⏳ Çok fazla komut.")
        return
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text("Kullanım: /tikla X Y\nÖrnek: /tikla 960 540")
        return
    _audit(user_id, f"/tikla {args[0]} {args[1]}")
    try:
        import pyautogui
        x, y = int(args[0]), int(args[1])
        pyautogui.click(x, y)
        await update.message.reply_text(f"✅ Tıklandı: ({x}, {y})")
    except Exception as exc:
        await update.message.reply_text(f"❌ Hata: {exc}")


async def yaz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/yaz [metin] — Aktif pencereye metin yaz (clipboard üzerinden, Unicode destekli)."""
    if not _is_allowed(update):
        return
    user_id = str(update.effective_user.id)
    if not _check_rate_limit(user_id):
        await update.message.reply_text("⏳ Çok fazla komut.")
        return
    text = " ".join(context.args or []).strip()
    if not text:
        await update.message.reply_text("Kullanım: /yaz [metin]\nÖrnek: /yaz Merhaba dünya")
        return
    _audit(user_id, f"/yaz {text[:50]}")
    try:
        import pyautogui
        import subprocess
        time.sleep(0.3)
        # Windows clipboard — Unicode (Türkçe dahil) desteği için
        try:
            import win32clipboard
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)
            win32clipboard.CloseClipboard()
        except ImportError:
            proc = subprocess.Popen(["clip"], stdin=subprocess.PIPE)
            proc.communicate(input=text.encode("utf-16"))
        pyautogui.hotkey("ctrl", "v")
        await update.message.reply_text(f"✅ Yazıldı: {text[:80]}")
    except Exception as exc:
        await update.message.reply_text(f"❌ Hata: {exc}")


async def tus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/tus [tuş] — Tuş bas. Kombiler: /tus ctrl+s, /tus alt+f4."""
    if not _is_allowed(update):
        return
    user_id = str(update.effective_user.id)
    if not _check_rate_limit(user_id):
        await update.message.reply_text("⏳ Çok fazla komut.")
        return
    key = " ".join(context.args or []).strip().lower()
    if not key:
        await update.message.reply_text(
            "Kullanım: /tus [tuş]\n"
            "Örnekler: /tus enter · /tus escape · /tus ctrl+s · /tus alt+f4"
        )
        return
    _audit(user_id, f"/tus {key}")
    try:
        import pyautogui
        if "+" in key:
            parts = [p.strip() for p in key.split("+")]
            pyautogui.hotkey(*parts)
        else:
            pyautogui.press(key)
        await update.message.reply_text(f"✅ Tuş basıldı: {key}")
    except Exception as exc:
        await update.message.reply_text(f"❌ Hata: {exc}")


# ─── BLOK 4: Onay akışı ──────────────────────────────────────────────────────

async def send_approval_request(
    bot,
    chat_id: str,
    tool_name: str,
    description: str,
    timeout: float = 60.0,
) -> bool:
    """High-impact araç için Telegram inline buton onayı iste.
    True döner → onaylandı. False → reddedildi veya timeout."""
    key = f"approval_{tool_name}"
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Onayla", callback_data=f"approve:{key}"),
        InlineKeyboardButton("❌ İptal",  callback_data=f"reject:{key}"),
    ]])
    sent = await bot.send_message(
        chat_id=chat_id,
        text=(
            f"⚠️ <b>Onay Gerekiyor</b>\n\n"
            f"<b>Araç:</b> <code>{tool_name}</code>\n"
            f"<b>İşlem:</b> {description[:300]}\n\n"
            f"Bu işlemi onaylıyor musun ({int(timeout)} sn içinde yanıtla)"
        ),
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    loop = asyncio.get_event_loop()
    future: asyncio.Future = loop.create_future()
    _pending_approvals[key] = future
    try:
        return await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            await sent.edit_text(
                f"⏱️ Onay zaman aşımı — işlem iptal edildi: <code>{tool_name}</code>",
                parse_mode="HTML",
            )
        except Exception:
            pass
        return False
    finally:
        _pending_approvals.pop(key, None)


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inline buton callback'lerini işle (onay/ret + 'başka bir şey...' yanıtı)."""
    if not _is_allowed(update):
        return
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    user_id = str(update.effective_user.id)
    _audit(user_id, f"callback:{data[:60]}")

    # BLOK 4: Araç onayı / reddi
    if data.startswith("approve:") or data.startswith("reject:"):
        key = data.split(":", 1)[1]
        future = _pending_approvals.get(key)
        if future and not future.done():
            future.set_result(data.startswith("approve"))
        if data.startswith("approve"):
            await query.edit_message_text(
                f"✅ Onaylandı: <code>{key}</code>", parse_mode="HTML"
            )
        else:
            await query.edit_message_text(
                f"❌ İptal edildi: <code>{key}</code>", parse_mode="HTML"
            )
        return

    # E-posta taslak onayı
    if data.startswith("draft_send:") or data.startswith("draft_skip:"):
        draft_id = data.split(":", 1)[1]
        try:
            from .services.email_monitor import (
                get_pending_draft,
                pop_pending_draft,
                send_email_via_gmail,
                send_email_via_outlook,
                _get_gmail_token,
                _get_outlook_token,
            )
            draft = get_pending_draft(draft_id)
            if not draft:
                await query.edit_message_text("❌ Taslak bulunamadı (zaten gönderilmiş veya süresi dolmuş).")
                return
            if data.startswith("draft_send:"):
                provider = str(draft.get("provider", "gmail") or "gmail").strip().lower()
                if provider == "outlook":
                    token = _get_outlook_token()
                    sent, detail = send_email_via_outlook(
                        token,
                        draft["to"],
                        draft["subject"],
                        draft["body"],
                    ) if token else (False, "Outlook erişim belirteci bulunamadı.")
                else:
                    token = _get_gmail_token()
                    sent, detail = send_email_via_gmail(
                        token,
                        draft["to"],
                        draft["subject"],
                        draft["body"],
                    ) if token else (False, "Gmail erişim belirteci bulunamadı.")
                if sent:
                    pop_pending_draft(draft_id)
                    await query.edit_message_text(
                        f"✅ Mail gönderildi!\nAlıcı: <code>{draft['to'][:60]}</code>",
                        parse_mode="HTML",
                    )
                else:
                    await query.answer("Mail gönderilemedi.", show_alert=False)
                    await query.message.reply_text(
                        f"❌ Mail gönderilemedi.\nNeden: {detail}\nTaslak korunuyor; tekrar deneyebilirsiniz."
                    )
            else:
                pop_pending_draft(draft_id)
                await query.edit_message_text("⏭ Taslak atlandı.")
        except Exception as exc:
            await query.edit_message_text(f"❌ Hata: {exc}")
        return

    # Watcher callback'leri
    if data == "watcher_stop":
        try:
            from .tools.super_agent import tool_stop_approval_watcher
            result = tool_stop_approval_watcher()
            msg = "Onay izleyici durduruldu." if result.get("success") else "İzleyici zaten kapalı."
            await query.edit_message_text(msg)
        except Exception as exc:
            await query.edit_message_text(f"Hata: {exc}")
        return

    if data == "watcher_continue":
        try:
            from .tools.super_agent import tool_ack_approval_completion_prompt
            tool_ack_approval_completion_prompt(keep_running=True)
            await query.edit_message_text("Onay izleyici devam ediyor.")
        except Exception as exc:
            await query.edit_message_text(f"Hata: {exc}")
        return

    if data == "watcher_screenshot":
        try:
            from .tools.super_agent import capture_notification_screenshot

            screenshot_path = capture_notification_screenshot("watcher_manual")
            if screenshot_path and Path(screenshot_path).exists():
                with open(screenshot_path, "rb") as fh:
                    await query.message.reply_photo(photo=fh, caption="Güncel ekran görüntüsü")
            else:
                await query.message.reply_text("Ekran görüntüsü alınamadı.")
        except Exception as exc:
            await query.message.reply_text(f"Ekran alınamadı: {exc}")
        return

    if data.startswith("watcher_choice:"):
        choice_text = data.split(":", 1)[1]
        try:
            from .tools.super_agent import tool_click_text_on_screen
            result = tool_click_text_on_screen(target_text=choice_text)
            if result.get("success"):
                await query.edit_message_text(f"Secim tiklandi: {result.get('matched_text', choice_text)[:60]}")
            else:
                await query.edit_message_text(f"Secim bulunamadi: {choice_text[:40]}")
        except Exception as exc:
            await query.edit_message_text(f"Hata: {exc}")
        return

    # BLOK 7: "Basqa bir sey..." yaniti
    if data == "more_yes":
        await query.edit_message_text("Tabii! Ne yapmami istersin...")
    elif data == "more_no":
        await query.edit_message_text("Anlaşıldı, beklemedeyim. İhtiyaç olursa yaz.")


# ─── BLOK 6: /araştır ────────────────────────────────────────────────────────

def _try_fast_research(text: str) -> Optional[str]:
    """Eger metin ACIKCA bir internet arastirmasi istegi ise konuyu cikarip dondurur.

    DIKKAT: Sadece kullanici acikca 'arastir', 'internette ara' gibi
    ifadeler kullandiginda tetiklenir. 'rapor', 'analiz', 'detayli' gibi
    genel kelimeler TETIKLEMEZ — bunlar LLM'e gider.
    """
    text_lower = _normalize_tr(text)
    # Sadece acik arastirma niyeti belirten cumle kaliplari
    explicit_research_phrases = [
        "arastirma yap",
        "internette ara",
        "internet'te ara",
        "web'de ara",
        "webde ara",
        "haber tara",
        "haberleri tara",
        "kaynak bul",
        "makale bul",
    ]
    # Kelimenin basinda "arastir" ile baslayan cumle (ama "arastirma" icinde degil)
    starts_with_research = text_lower.strip().startswith("arastir ") or text_lower.strip().startswith("arastir:")
    if starts_with_research and len(text) > 15:
        return text
    if any(phrase in text_lower for phrase in explicit_research_phrases) and len(text) > 15:
        return text
    return None


def _looks_like_fast_mail_query(text: str) -> bool:
    normalized = _normalize_tr(text)
    if not any(token in normalized for token in ("mail", "mailler", "eposta", "e-posta", "gmail", "outlook")):
        return False
    if any(token in normalized for token in ("gonder", "yolla", "cevapla", "yanitla", "taslak")):
        return False
    check_markers = (
        "var mi", "başka", "baska", "daha", "geldi mi", "neler var",
        "kontrol et", "bak", "bakar misin", "ozet", "özet",
    )
    return any(token in normalized for token in check_markers)


def _build_fast_mail_query_reply(text: str) -> Optional[str]:
    if not _looks_like_fast_mail_query(text):
        return None
    try:
        from .tools.registry import execute_tool
        from .services.email_monitor import get_preferred_mail_provider, _heuristic_triage

        provider = get_preferred_mail_provider()
        tool_name = "check_outlook_messages" if provider == "outlook" else "check_gmail_messages"
        params = {"max_results": 10}
        if provider == "outlook":
            params["unread_only"] = True
            params["today_only"] = False
        else:
            params["query"] = "is:unread"

        result = execute_tool(tool_name, params)
        messages = result.get("messages", []) if isinstance(result, dict) else []
        if not messages:
            return "Şu anda okunmamış başka mail görünmüyor."

        highlights = []
        for mail in messages[:6]:
            triage = _heuristic_triage(mail, reason_prefix="telegram_hizli")
            level = str(triage.get("level", "")).upper()
            if level not in {"CRITICAL", "IMPORTANT", "NOTICE"}:
                continue
            label = {
                "CRITICAL": "Kritik",
                "IMPORTANT": "Önemli",
                "NOTICE": "Bilgi",
            }.get(level, level.title())
            subject = str(mail.get("subject", "(Konu yok)") or "(Konu yok)").strip()
            sender = str(mail.get("from", "") or "").strip()
            highlights.append(f"- [{label}] {subject} | {sender}")

        if not highlights:
            return f"{len(messages)} okunmamış mail var ama öne çıkan başka kayıt görünmüyor."

        lines = ["Öne çıkan diğer mailler:"]
        lines.extend(highlights[:5])
        return "\n".join(lines)
    except Exception:
        return None

async def arastir_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/araştır [konu] — Arka planda araştırma başlat; bitince Telegram'a PDF rapor gelir."""
    if not _is_allowed(update):
        return
    user_id = str(update.effective_user.id)
    if not _check_rate_limit(user_id):
        await update.message.reply_text("⏳ Çok fazla komut.")
        return
    topic = " ".join(context.args or []).strip()
    if not topic:
        await update.message.reply_text(
            "Kullanım: /araştır [konu]\n"
            "Örnek: /araştır yapay zeka trendleri 2025"
        )
        return
    _audit(user_id, f"/araştır {topic[:80]}")
    try:
        from .tools.registry import execute_tool
        result = execute_tool("research_async", {"topic": topic})
        if result.get("success"):
            await update.message.reply_text(
                f"📚 <b>Araştırma başlatıldı!</b>\n\n"
                f"Konu: <b>{topic[:100]}</b>\n"
                f"Not defteri: <code>{result.get('notebook', '')}</code>\n\n"
                "Bitince Telegram'a özet ve PDF rapor gönderilecek. "
                "Süre, konuya ve kaynak yoğunluğuna göre değişebilir.",
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text(
                f"❌ Araştırma başlatılamadı: {result.get('error', '...')}"
            )
    except Exception as exc:
        await update.message.reply_text(f"❌ Hata: {exc}")


# ─── BLOK 10: /izle, /izleme_durdur, /izleme_durum ──────────────────────────

async def izle_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/izle [profil] — Onay izleyiciyi baslat. Profiller: gemini, codex, claudecode, kimicode, copilot, generic"""
    if not _is_allowed(update):
        return
    user_id = str(update.effective_user.id)
    if not _check_rate_limit(user_id):
        await update.message.reply_text("Cok fazla komut.")
        return
    args = context.args or []
    profile = args[0].lower().strip() if args else "generic"
    _audit(user_id, f"/izle {profile}")

    try:
        from .tools.super_agent import tool_start_approval_watcher
        result = tool_start_approval_watcher(
            profile=profile,
            notify_on_completion=True,
            auto_stop_on_completion=False,
        )
        if result.get("running"):
            msg = result.get("message", "Onay izleyici aktif.")
            status = result.get("status", {})
            if status:
                msg += f"\nProfil: {status.get('profile', profile)}"
                msg += f"\nKontrol: {status.get('checks', 0)} | Onay: {status.get('accepted', 0)}"
            await update.message.reply_text(msg)
        else:
            await update.message.reply_text(f"Izleyici baslatildi.\nProfil: {profile}")
    except Exception as exc:
        await update.message.reply_text(f"Hata: {exc}")


async def izleme_durdur_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/izleme_durdur — Onay izleyiciyi durdur."""
    if not _is_allowed(update):
        return
    _audit(str(update.effective_user.id), "/izleme_durdur")
    try:
        from .tools.super_agent import tool_stop_approval_watcher
        result = tool_stop_approval_watcher()
        await update.message.reply_text(result.get("message", "Durduruldu."))
    except Exception as exc:
        await update.message.reply_text(f"Hata: {exc}")


async def izleme_durum_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/izleme_durum — Onay izleyici durumu + ekran goruntusu."""
    if not _is_allowed(update):
        return
    _audit(str(update.effective_user.id), "/izleme_durum")
    try:
        from .tools.super_agent import capture_notification_screenshot, tool_approval_watcher_status
        status = tool_approval_watcher_status()
        running = status.get("running", False)
        lines = []
        lines.append(f"<b>Onay Izleyici:</b> {'Aktif' if running else 'Kapali'}")
        if running:
            lines.append(f"Profil: {status.get('profile', '?')}")
            lines.append(f"Durum: {status.get('watcher_state', '?')}")
            lines.append(f"Kontrol: {status.get('checks', 0)} | Onay: {status.get('accepted', 0)}")
            lines.append(f"Son olay: {status.get('last_event', '-')}")
            if status.get("llm_state"):
                lines.append(f"LLM: {status.get('llm_state', '')} (guven: {status.get('llm_confidence', 0):.0%})")
                if status.get("llm_reasoning"):
                    lines.append(f"LLM neden: {status.get('llm_reasoning', '')[:100]}")
            if status.get("last_error"):
                lines.append(f"Hata: {status.get('last_error', '')}")
        text = "\n".join(lines)
        await update.message.reply_text(text, parse_mode="HTML")

        # Ek olarak ekran goruntusu gonder
        if running:
            try:
                screenshot_path = capture_notification_screenshot("watcher_status")
                if screenshot_path and Path(screenshot_path).exists():
                    with open(screenshot_path, "rb") as fh:
                        await update.message.reply_photo(photo=fh, caption="Güncel ekran")
            except Exception:
                pass
    except Exception as exc:
        await update.message.reply_text(f"Hata: {exc}")


# ─── BLOK 11: /tikla_metin, /ajanyaz ────────────────────────────────────────

async def tikla_metin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/tikla_metin [metin] — Ekranda belirtilen metne OCR ile tikla."""
    if not _is_allowed(update):
        return
    user_id = str(update.effective_user.id)
    if not _check_rate_limit(user_id):
        await update.message.reply_text("Cok fazla komut.")
        return
    text = " ".join(context.args or []).strip()
    if not text:
        await update.message.reply_text("Kullanim: /tikla_metin [metin]\nOrnek: /tikla_metin Allow once")
        return
    _audit(user_id, f"/tikla_metin {text[:50]}")
    status_msg = await update.message.reply_text(f"Araniyor: {text[:40]}...")
    try:
        from .tools.super_agent import tool_click_text_on_screen
        result = tool_click_text_on_screen(target_text=text)
        if result.get("success"):
            await status_msg.edit_text(
                f"Tiklandi: {result.get('matched_text', text)[:60]}\n"
                f"Eslesme: {result.get('match_ratio', 0):.0%} | Konum: ({result.get('x', 0)}, {result.get('y', 0)})"
            )
        else:
            await status_msg.edit_text(f"Metin bulunamadi: {text[:60]}")
    except Exception as exc:
        await status_msg.edit_text(f"Hata: {exc}")


async def ajanyaz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/ajanyaz [ajan] [mesaj] — VS Code'daki ajana mesaj yaz.
    Ornek: /ajanyaz codex bu hatayi duzelt
    Ornek: /ajanyaz gemini projede sorun var"""
    if not _is_allowed(update):
        return
    user_id = str(update.effective_user.id)
    if not _check_rate_limit(user_id):
        await update.message.reply_text("Cok fazla komut.")
        return
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "Kullanim: /ajanyaz [ajan] [mesaj]\n"
            "Ajanlar: codex, claudecode, kimicode, copilot, gemini\n"
            "Ornek: /ajanyaz codex bu hatayi duzelt"
        )
        return
    agent = args[0].lower().strip()
    message = " ".join(args[1:]).strip()
    _audit(user_id, f"/ajanyaz {agent} {message[:50]}")
    status_msg = await update.message.reply_text(f"Yaziliyor: {agent} -> {message[:40]}...")
    try:
        from .tools.super_agent import tool_type_in_agent_input
        result = tool_type_in_agent_input(agent=agent, text=message)
        if result.get("success"):
            await status_msg.edit_text(f"Yazildi: {agent} <- {message[:60]}")
        else:
            await status_msg.edit_text(f"Hata: {result.get('error', 'Bilinmeyen hata')}")
    except Exception as exc:
        await status_msg.edit_text(f"Hata: {exc}")


async def ekran_analiz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/analiz [profil] — Ekrani LLM ile analiz et. Durum, aksiyon, butonlari tanimla."""
    if not _is_allowed(update):
        return
    user_id = str(update.effective_user.id)
    if not _check_rate_limit(user_id):
        await update.message.reply_text("Cok fazla komut.")
        return
    args = context.args or []
    profile = args[0].lower().strip() if args else "generic"
    _audit(user_id, f"/analiz {profile}")
    status_msg = await update.message.reply_text("Ekran analiz ediliyor...")
    try:
        from .tools.super_agent import tool_analyze_screen
        result = tool_analyze_screen(profile=profile)
        lines = []
        lines.append(f"<b>Durum:</b> {result.get('state', '?')}")
        lines.append(f"<b>Aksiyon:</b> {result.get('action', '?')}")
        if result.get("target_text"):
            lines.append(f"<b>Hedef:</b> {result.get('target_text', '')}")
        lines.append(f"<b>Guven:</b> {result.get('confidence', 0):.0%}")
        if result.get("reasoning"):
            lines.append(f"<b>Neden:</b> {result.get('reasoning', '')[:200]}")
        if result.get("options"):
            lines.append("<b>Secenekler:</b>")
            for i, opt in enumerate(result["options"][:6], 1):
                lines.append(f"  {i}. {opt}")
        if result.get("completion_summary"):
            lines.append(f"<b>Ozet:</b> {result.get('completion_summary', '')}")
        await status_msg.edit_text("\n".join(lines), parse_mode="HTML")

        # Ek olarak ekran goruntusu
        try:
            import pyautogui
            shot = pyautogui.screenshot()
            buf = io.BytesIO()
            shot.save(buf, format="PNG")
            buf.seek(0)
            await update.message.reply_photo(photo=buf)
        except Exception:
            pass
    except Exception as exc:
        await status_msg.edit_text(f"Hata: {exc}")


# ─── BLOK 1: /durum ──────────────────────────────────────────────────────────

async def durum_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/durum — Bot, servisler ve sistem durumunu göster."""
    if not _is_allowed(update):
        return
    _audit(str(update.effective_user.id), "/durum")
    lines = ["📊 <b>Sistem Durumu</b>\n"]

    # CPU / RAM
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory()
        lines.append(f"🖥️ CPU: <b>{cpu}%</b>")
        lines.append(
            f"💾 RAM: <b>{ram.percent}%</b> "
            f"({ram.used // 1024 // 1024} MB / {ram.total // 1024 // 1024} MB)"
        )
    except ImportError:
        lines.append("ℹ️ Sistem bilgisi: psutil yüklü değil")

    # Servis durumları
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"http://{settings.host}:{settings.port}/services/status"
            )
            if resp.status_code == 200:
                svcs = resp.json()
                lines.append("")
                for name, info in svcs.items():
                    if isinstance(info, dict):
                        icon = "✅" if info.get("running") else "❌"
                        lines.append(f"{icon} {name}")
    except Exception:
        lines.append("\n❌ Servis durumları alınamadı")

    # Rate limiter özeti
    user_id = str(update.effective_user.id)
    recent = len([t for t in _rate_window.get(user_id, []) if time.time() - t < 60])
    lines.append(f"\n📈 Son 60s komut: {recent}/{_RATE_MAX}")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def _process_image_with_ocr(image_bytes: bytes, caption: str = "") -> str:
    """Gorseli OCR ile isleyip metin cikar. Zaman asimi korumali."""
    import tempfile
    import asyncio
    from pathlib import Path
    from concurrent.futures import ThreadPoolExecutor
    
    def _do_ocr():
        try:
            # Gecici dosyaya kaydet
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp.write(image_bytes)
                tmp_path = tmp.name
            
            # OCR ile oku
            from .tools.registry import execute_tool
            result = execute_tool("ocr_image", {"image_path": tmp_path})
            
            # Gecici dosyayi temizle
            try:
                Path(tmp_path).unlink()
            except:
                pass
            
            return result.get("text", "")
        except Exception as e:
            return f""
    
    try:
        # OCR islemini 10 saniyede bitir, yoksa iptal et
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as pool:
            ocr_text = await asyncio.wait_for(
                loop.run_in_executor(pool, _do_ocr),
                timeout=10.0
            )
        
        # HER DURUMDA gorsel baglami olustur
        visual_context = "[SISTEM: Kullanici bir GORSEL gonderdi."
        
        if ocr_text and ocr_text.strip() and len(ocr_text.strip()) > 3:
            # OCR basarili - metin var
            visual_context += f" OCR ile metinler okundu:]\n\n"
            visual_context += f"=== GORSELDEKI METINLER ===\n{ocr_text[:1500]}\n"
            visual_context += f"=== METIN SONU ===\n\n"
        else:
            # OCR basarisiz - metin yok
            visual_context += "]\n\n"
            visual_context += "[NOT: Gorselde okunabilir metin bulunamadi.]\n\n"
        
        if caption:
            visual_context += f"[Kullanicinin istegi: {caption}]\n"
            visual_context += f"\nGorev: {caption}"
        else:
            visual_context += "\nGorev: Gorseldeki metinleri analiz et ve yorumla."
        
        return visual_context
        
    except asyncio.TimeoutError:
        # Zaman asimi - yine de gorsel oldugunu ve istegi belirt
        visual_context = "[SISTEM: Kullanici bir GORSEL gonderdi (OCR zaman asimi)]\n\n"
        if caption:
            visual_context += f"[Kullanicinin istegi: {caption}]\n\nGorev: {caption}"
        else:
            visual_context += "\nGorev: Gorseli analiz et."
        return visual_context
        
    except Exception as e:
        # Hata durumu
        visual_context = "[SISTEM: Kullanici bir GORSEL gonderdi (OCR hatasi)]\n\n"
        if caption:
            visual_context += f"[Kullanicinin istegi: {caption}]\n\nGorev: {caption}"
        else:
            visual_context += "\nGorev: Gorseli analiz et."
        return visual_context


async def _check_incomplete_notebooks(session_id: str) -> Optional[tuple[str, str]]:
    """Yarim kalan notebook var mi kontrol et; (signature, mesaj) dondur."""
    try:
        from .tools.notebook_tools import tool_notebook_list
        result = tool_notebook_list()
        notebooks = result.get("notebooks", [])
        
        incomplete = [n for n in notebooks if n.get("status") == "Devam Ediyor"]
        if incomplete:
            latest = incomplete[0]  # En sonuncu
            name = str(latest.get("name", "")).strip()
            progress = str(latest.get("progress", "-")).strip()
            signature = f"{name}|{progress}"
            message = (
                f"\n\n💡 **Yarim kalan isiniz var:** `{latest['name']}`\n"
                f"İlerleme: {latest['progress']}\n"
                f"Devam etmek icin: \"{latest['name']} raporuna devam et\" yazabilirsiniz."
            )
            return signature, message
    except:
        pass
    return None


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    if update.message is None:
        return

    user_id = str(update.effective_user.id)
    if not _check_rate_limit(user_id):
        await update.message.reply_text("⏳ Çok fazla mesaj. Biraz bekle.")
        return

    session_id = f"telegram_{update.effective_user.id}"
    request_token = int(time.time() * 1000)
    previous_token = _LATEST_REQUEST_TOKENS.get(session_id, 0)
    if request_token <= previous_token:
        request_token = previous_token + 1
    _LATEST_REQUEST_TOKENS[session_id] = request_token
    user_message = ""
    
    # 1. METIN MESAJI
    if update.message.text:
        user_message = update.message.text
    
    # 2. FOTOGRAF/GORSEL - OCR ile isle
    elif update.message.photo:
        # En buyuk fotografi al
        photo = update.message.photo[-1]
        caption = update.message.caption or ""
        
        # Once bilgi mesaji gonder
        status_msg = await update.message.reply_text("📸 Görsel algılandı, içerik okunuyor...")

        try:
            # Fotografi indir
            file = await context.bot.get_file(photo.file_id)
            image_bytes = await file.download_as_bytearray()

            # OCR ile isle (max 10 saniye)
            user_message = await _process_image_with_ocr(bytes(image_bytes), caption)

            # OCR sonucunu kontrol et
            if "okunabilir metin bulunamadi" in user_message.lower() or "metin yok" in user_message.lower():
                # Gorselde metin yok - kullaniciyi bilgilendir
                info_text = (
                    "ℹ️ **Görsel durumu:**\n"
                    "Görselde okunabilir **metin bulunamadı**.\n"
                    "Bu bot görsellerdeki yazıları OCR ile okuyabilir,\n"
                    "ama nesneleri/karakterleri göremez.\n\n"
                )
                if caption:
                    info_text += f"İsteğiniz işleniyor: {caption}"
                else:
                    info_text += "Görseli metin olarak anlatmak isterseniz yazabilirsiniz."

                await status_msg.edit_text(info_text)
            else:
                # Metin bulundu - devam et
                await status_msg.edit_text("✅ Görseldeki metinler OCR ile okundu, analiz ediliyor...")

        except Exception as e:
            await status_msg.edit_text(f"⚠️ Görsel işlenirken sorun: {e}")
            # Yine de devam et - bos mesaj kontrolu yapilacak
            if caption:
                user_message = f"[Kullanıcı bir görsel gönderdi. Açıklama: {caption}]"
            else:
                await update.message.reply_text("❌ Görsel işlenemedi. Lütfen metin olarak yazın.")
                return
    
    # 3. DOKUMAN (Resim dosyasi olarak gonderilmis olabilir)
    elif update.message.document:
        # Resim dosyasi mi kontrol et
        mime_type = update.message.document.mime_type or ""
        if mime_type.startswith("image/"):
            status_msg = await update.message.reply_text("📸 Görsel (doküman olarak gönderildi) algılandı, içerik okunuyor...")
            
            try:
                file = await context.bot.get_file(update.message.document.file_id)
                image_bytes = await file.download_as_bytearray()
                
                caption = update.message.caption or ""
                user_message = await _process_image_with_ocr(bytes(image_bytes), caption)
                
                await status_msg.edit_text("✅ Görsel içeriği okundu, analiz ediliyor...")
            except Exception as e:
                await status_msg.edit_text(f"⚠️ Görsel işlenirken sorun: {e}")
                if caption:
                    user_message = f"[Kullanıcı bir görsel gönderdi. Açıklama: {caption}]"
                else:
                    await update.message.reply_text("❌ Görsel analiz edilemedi.")
                    return
        else:
            await update.message.reply_text("📎 Bu doküman türünü henüz işleyemiyorum. Lütfen metin olarak yazın veya görsel olarak gönderin.")
            return
    
    else:
        # Desteklenmeyen mesaj tipi
        return
    
    # Bos mesaj kontrolu
    if not user_message or not user_message.strip():
        await update.message.reply_text("⚠️ Mesaj içeriği boş. Lütfen metin yazın veya görsel gönderin.")
        return

    fast_chat_reply = _build_fast_chat_reply(user_message)
    if fast_chat_reply and update.message.text and not update.message.photo and not update.message.document:
        await update.message.reply_text(fast_chat_reply)
        _audit(user_id, user_message[:100], status="ok")
        return
    
    # 4. SOHBET MODU
    # Telegram'da komutsuz mesajlari dogrudan ajana gonder.
    # Erken "smart" kisayollari burada devreye girmiyor; araci gerekirse LLM secsin.

    # Agent'i cagir
    thinking_msg = None
    thinking_task = None
    if update.message.text and _should_show_thinking_indicator(
        user_message,
        has_media=bool(update.message.photo or update.message.document),
    ):
        try:
            async def _thinking_heartbeat() -> None:
                nonlocal thinking_msg
                pulses = [
                    "⏳ Düşünüyorum... İsteğin işleniyor.",
                    "⏳ Hâlâ çalışıyorum... yanıt hazırlanıyor.",
                    "⏳ İşlem sürüyor, tamamlanınca sonucu paylaşacağım.",
                ]
                await asyncio.sleep(1)
                thinking_msg = await update.message.reply_text(pulses[0])
                idx = 0
                while True:
                    await asyncio.sleep(35)
                    if thinking_msg is None:
                        return
                    try:
                        await thinking_msg.edit_text(pulses[idx % len(pulses)])
                    except Exception:
                        return
                    idx += 1

            thinking_task = asyncio.create_task(_thinking_heartbeat())
        except Exception:
            thinking_msg = None
            thinking_task = None

    try:
        data = await call_agent(session_id, user_message)
        reply = data.get("reply", "")
        media_list = data.get("media") or []
        used_tools = data.get("used_tools") or []
    except Exception as exc:
        err_text = str(exc).strip()
        exc_type = type(exc).__name__
        if not err_text:
            err_text = exc_type
        
        # Timeout hatasi - daha yapici mesaj
        if "timeout" in err_text.lower() or "Timeout" in exc_type or "zaman asimi" in err_text.lower():
            # Gercekten notebook olusup olusmadigini kontrol et
            notebook_msg = await _check_incomplete_notebooks(session_id)
            
            if notebook_msg:
                signature, hint_text = notebook_msg
                should_show_hint = _TIMEOUT_NOTEBOOK_HINT_CACHE.get(session_id) != signature
                _TIMEOUT_NOTEBOOK_HINT_CACHE[session_id] = signature
                timeout_msg = "⏳ **İşlem zaman aşımına uğradı.**\n\n"
                timeout_msg += "Sistem o an yoğun olabilir. Aynı komutu tekrar deneyin."
                if should_show_hint:
                    timeout_msg += hint_text
            else:
                # Notebook yok - kaydedilemedi
                timeout_msg = "⏳ **İşlem zaman aşımına uğradı.**\n\n"
                timeout_msg += "Maalesef işlem çok uzun sürdü ve tamamlanamadı.\n"
                timeout_msg += "Lütfen tekrar deneyin veya daha kısa adımlara bölün."
            
            reply = timeout_msg
        elif "ConnectError" in exc_type or "ConnectionRefused" in exc_type:
            reply = "❌ Agent sunucusuna bağlanılamıyor. Backend çalışmıyor olabilir."
        elif "RSS" in err_text or "parse" in err_text.lower() or "XML" in err_text:
            reply = f"📰 Haber kaynagi hatasi: {err_text[:200]}"
        else:
            reply = f"❌ Hata: {err_text[:500]}"
        media_list = []
        used_tools = []
    finally:
        if thinking_task is not None:
            thinking_task.cancel()
            try:
                await thinking_task
            except BaseException:
                pass
        if thinking_msg is not None:
            try:
                await thinking_msg.delete()
            except Exception:
                pass

    if _LATEST_REQUEST_TOKENS.get(session_id) != request_token:
        _audit(user_id, user_message[:100] if user_message else "(media)", status="stale_drop")
        return

    try:
        if (
            isinstance(used_tools, list)
            and "research_async" in used_tools
            and isinstance(reply, str)
            and "hata" not in _normalize_tr(reply)
        ):
            looks_like_tool_dump = (
                "islem tamamlandi. sonuclar" in _normalize_tr(reply)
                or "`research_async`" in reply
            )
            if looks_like_tool_dump:
                reply = (
                    "Araştırmayı başlattım. Arka planda çalışıyor.\n\n"
                    "Bitince özeti ve PDF raporu buradan otomatik paylaşacağım."
                )
    except Exception:
        pass

    # Send media first.
    _logger = logging.getLogger(__name__)
    _logger.info(f"[TELEGRAM] Sending {len(media_list)} media files")
    
    base_url = f"http://{settings.host}:{settings.port}"
    for m in media_list:
        media_url = m.get("url", "")
        media_type = m.get("type", "")
        caption = m.get("caption", m.get("filename", ""))
        _logger.info(f"[TELEGRAM] Sending media: type={media_type}, url={media_url}")
        
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=15.0)) as client:
                file_resp = await client.get(f"{base_url}{media_url}")
                _logger.info(f"[TELEGRAM] Download response: {file_resp.status_code}")
                if file_resp.status_code != 200:
                    _logger.error(f"[TELEGRAM] Failed to download media: {file_resp.status_code}")
                    continue
                file_bytes = file_resp.content
                _logger.info(f"[TELEGRAM] Downloaded {len(file_bytes)} bytes")

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

    # BLOK 7: Görev tamamlama → "Başka bir şey..." inline butonu
    _done_hints = (
        "tamamland", "başarıyla", "basariyla", "hazır", "hazir",
        "oluşturuldu", "olusturuldu", "gönderildi", "gonderildi",
        "kaydedildi", "çalıştırıldı", "calıstirildi", "yazıldı",
        "yazildi", "açıldı", "acildi", "silindi", "bitti",
    )
    if reply and len(reply) > 200 and any(h in reply.lower() for h in _done_hints):
        try:
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Evet", callback_data="more_yes"),
                InlineKeyboardButton("❌ Hayır", callback_data="more_no"),
            ]])
            await update.message.reply_text(
                "Başka bir şey ister misin...",
                reply_markup=keyboard,
            )
        except Exception:
            pass

    _audit(user_id, user_message[:100] if user_message else "(media)")


# ─── Journal: /not, /notlar ──────────────────────────────────────────────────

async def not_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/not [metin] — Bugünün notuna ekle."""
    if not _is_allowed(update):
        return
    user_id = str(update.effective_user.id)
    if not _check_rate_limit(user_id):
        await update.message.reply_text("⏳ Çok fazla komut.")
        return
    text = " ".join(context.args or []).strip()
    if not text:
        await update.message.reply_text("Kullanım: /not [not metni]\nÖrnek: /not Vue 3 migration notları incele")
        return
    _audit(user_id, f"/not {text[:80]}")
    try:
        from .services.journal import add_note
        entry = add_note(text)
        await update.message.reply_text(
            f"📓 Not kaydedildi #{entry['id']} ({entry['time']})\n<i>{text[:200]}</i>",
            parse_mode="HTML",
        )
    except Exception as exc:
        await update.message.reply_text(f"❌ Not kaydedilemedi: {exc}")


async def notlar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/notlar [dün|hafta] — Notları listele."""
    if not _is_allowed(update):
        return
    user_id = str(update.effective_user.id)
    _audit(user_id, "/notlar")
    arg = " ".join(context.args or []).strip().lower()
    try:
        from .services.journal import get_notes, get_recent_notes, format_notes_message
        from datetime import datetime, timedelta
        if arg in ("dun", "dün"):
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            notes = get_notes(yesterday)
            msg = format_notes_message(notes, f"Dün ({yesterday})")
        elif arg in ("hafta", "7gun", "7gün"):
            notes = get_recent_notes(days=7)
            if not notes:
                msg = "📓 Son 7 günde kayıtlı not yok."
            else:
                lines = ["📓 <b>Son 7 Günün Notları</b>\n"]
                for n in notes[:20]:
                    lines.append(f"📅 <b>{n.get('date','')} {n.get('time','')}</b>\n{n['text']}")
                msg = "\n\n".join(lines)
        else:
            notes = get_notes()
            msg = format_notes_message(notes, "Bugün")
        await update.message.reply_text(msg[:4000], parse_mode="HTML")
    except Exception as exc:
        await update.message.reply_text(f"❌ Hata: {exc}")


# ─── Todo sistemi ─────────────────────────────────────────────────────────────

async def todo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/todo [metin] — Todo ekle."""
    if not _is_allowed(update):
        return
    user_id = str(update.effective_user.id)
    if not _check_rate_limit(user_id):
        await update.message.reply_text("⏳ Çok fazla komut.")
        return
    text = " ".join(context.args or []).strip()
    if not text:
        await update.message.reply_text(
            "Kullanım: /todo [metin]\n"
            "Örnek: /todo Vue 3 migration dökümantasyonunu oku"
        )
        return
    _audit(user_id, f"/todo {text[:80]}")
    try:
        from .services.journal import add_todo
        entry = add_todo(text)
        await update.message.reply_text(
            f"📋 Todo eklendi <b>#{entry['id']}</b>\n<i>{text[:200]}</i>",
            parse_mode="HTML",
        )
    except Exception as exc:
        await update.message.reply_text(f"❌ Hata: {exc}")


async def todos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/todos — Bekleyen todo'ları listele."""
    if not _is_allowed(update):
        return
    _audit(str(update.effective_user.id), "/todos")
    try:
        from .services.journal import get_all_todos, format_todos_message
        todos = get_all_todos(include_done=True)
        msg = format_todos_message(todos, "Yapılacaklar")
        await update.message.reply_text(msg[:4000], parse_mode="HTML")
    except Exception as exc:
        await update.message.reply_text(f"❌ Hata: {exc}")


async def done_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/done [id] — Todo'yu tamamla."""
    if not _is_allowed(update):
        return
    user_id = str(update.effective_user.id)
    arg = " ".join(context.args or []).strip()
    if not arg.isdigit():
        await update.message.reply_text("Kullanım: /done [id]\nÖrnek: /done 3")
        return
    _audit(user_id, f"/done {arg}")
    try:
        from .services.journal import complete_todo
        result = complete_todo(int(arg))
        if result:
            await update.message.reply_text(
                f"✅ Tamamlandı: <b>#{result['id']}</b>\n<s>{result['text'][:150]}</s>",
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text(f"❌ #{arg} bulunamadı.")
    except Exception as exc:
        await update.message.reply_text(f"❌ Hata: {exc}")


# ─── BLOK 12: /komut — Uzak terminal ─────────────────────────────────────────

_KOMUT_DANGEROUS_PATTERNS = re.compile(
    r"(rm\s+-rf|del\s+/[sfq]|format\s+[a-z]:|shutdown|restart|reboot"
    r"|mkfs|dd\s+if=|:\(\)\{|fork\s*bomb"
    r"|taskkill.*\/im\s+(explorer|csrss|winlogon|svchost)"
    r"|reg\s+delete|bcdedit|diskpart)",
    re.IGNORECASE,
)
_KOMUT_TIMEOUT = 30
_KOMUT_MAX_OUTPUT = 3800


async def komut_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/komut <shell komutu> — Uzak terminal. Komutu çalıştırır, çıktıyı döndürür."""
    if not _is_allowed(update):
        return
    _audit(str(update.effective_user.id), "/komut")
    cmd = " ".join(context.args or []).strip()
    if not cmd:
        await update.message.reply_text(
            "Kullanım: <code>/komut git status</code>\n"
            "Örnek: <code>/komut netstat -ano | findstr 8000</code>",
            parse_mode="HTML",
        )
        return

    # Tehlikeli komut kontrolü
    if _KOMUT_DANGEROUS_PATTERNS.search(cmd):
        await update.message.reply_text(
            f"⚠️ Tehlikeli komut engellendi:\n<code>{cmd[:200]}</code>\n\n"
            "Bu komutu çalıştırmak istiyorsan doğrudan bilgisayardan yap.",
            parse_mode="HTML",
        )
        return

    await update.message.reply_text(f"⏳ Çalıştırılıyor...\n<code>{cmd[:200]}</code>", parse_mode="HTML")

    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(Path.home() / "Desktop"),
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=_KOMUT_TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            await update.message.reply_text(f"⏱️ Zaman aşımı ({_KOMUT_TIMEOUT}s). Komut sonlandırıldı.")
            return

        output = (stdout or b"").decode("utf-8", errors="replace").strip()
        exit_code = proc.returncode
        icon = "✅" if exit_code == 0 else "❌"

        if not output:
            await update.message.reply_text(f"{icon} Çıkış kodu: {exit_code}\n(çıktı yok)")
            return

        if len(output) <= _KOMUT_MAX_OUTPUT:
            await update.message.reply_text(
                f"{icon} Çıkış: {exit_code}\n<pre>{output[:_KOMUT_MAX_OUTPUT]}</pre>",
                parse_mode="HTML",
            )
        else:
            # Uzun çıktıyı dosya olarak gönder
            buf = io.BytesIO(output.encode("utf-8"))
            buf.name = "komut_cikti.txt"
            await update.message.reply_document(
                document=buf,
                filename="komut_cikti.txt",
                caption=f"{icon} Çıkış: {exit_code} | {len(output)} karakter",
            )
    except Exception as exc:
        await update.message.reply_text(f"❌ Hata: {exc}")


async def export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/export [gün] — Todo + notları AI'ye gönderilebilir formatta aktar."""
    if not _is_allowed(update):
        return
    user_id = str(update.effective_user.id)
    _audit(user_id, "/export")
    arg = " ".join(context.args or []).strip()
    days = int(arg) if arg.isdigit() else 0
    try:
        from .services.journal import export_for_ai
        import datetime as _dt
        content = export_for_ai(include_notes_days=days)
        if len(content) <= 3800:
            await update.message.reply_text(
                f"<pre>{content[:3800]}</pre>",
                parse_mode="HTML",
            )
        else:
            buf = io.BytesIO(content.encode("utf-8"))
            fname = f"openworld_export_{_dt.datetime.now().strftime('%Y%m%d_%H%M')}.txt"
            buf.name = fname
            await update.message.reply_document(document=buf, filename=fname)
    except Exception as exc:
        await update.message.reply_text(f"❌ Hata: {exc}")


async def main() -> None:
    _acquire_single_instance_lock()
    atexit.register(_release_single_instance_lock)

    token = settings.telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token and settings.telegram_bot_token_enc:
        token = decrypt_text(settings.telegram_bot_token_enc)
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN missing in backend/.env")

    try:
        builder = Application.builder().token(token)
        try:
            builder = builder.concurrent_updates(8)
        except Exception:
            pass
        app = builder.build()
        app.add_handler(CommandHandler("start", start_cmd))
        # BLOK 2: Ekran görüntüsü
        app.add_handler(CommandHandler("ekran", ekran_cmd))
        # BLOK 3: Ekran etkileşimi
        app.add_handler(CommandHandler("tikla", tikla_cmd))
        app.add_handler(CommandHandler("yaz", yaz_cmd))
        app.add_handler(CommandHandler("tus", tus_cmd))
        # BLOK 6: Araştırma
        # Telegram komut adlari ASCII olmalidir.
        app.add_handler(CommandHandler(["arastir", "ara"], arastir_cmd))
        # BLOK 1: Durum
        app.add_handler(CommandHandler("durum", durum_cmd))
        # Journal + Todo
        app.add_handler(CommandHandler("not", not_cmd))
        app.add_handler(CommandHandler("notlar", notlar_cmd))
        app.add_handler(CommandHandler("todo", todo_cmd))
        app.add_handler(CommandHandler("todos", todos_cmd))
        app.add_handler(CommandHandler("done", done_cmd))
        app.add_handler(CommandHandler("export", export_cmd))
        # BLOK 12: Uzak terminal
        app.add_handler(CommandHandler("komut", komut_cmd))
        # BLOK 10: Onay izleyici
        app.add_handler(CommandHandler("izle", izle_cmd))
        app.add_handler(CommandHandler("izleme_durdur", izleme_durdur_cmd))
        app.add_handler(CommandHandler("izleme_durum", izleme_durum_cmd))
        # BLOK 11: Ekran etkilesim
        app.add_handler(CommandHandler("tikla_metin", tikla_metin_cmd))
        app.add_handler(CommandHandler("ajanyaz", ajanyaz_cmd))
        app.add_handler(CommandHandler("analiz", ekran_analiz_cmd))
        # BLOK 4 + 7 + draft onay + watcher: Inline buton callback'leri
        app.add_handler(CallbackQueryHandler(callback_handler))
        # Hem metin hem fotoğraf mesajlarını dinle
        app.add_handler(MessageHandler(
            (filters.TEXT | filters.PHOTO | filters.Document.IMAGE) & ~filters.COMMAND, 
            on_message
        ))
        await app.initialize()
        await app.start()

        # Arka plan thread'lerinin Telegram'a bildirim gondermesini sagla
        try:
            allowed_chat_id = settings.telegram_allowed_user_id.strip()
            if allowed_chat_id:
                from .notifier import set_context as _notifier_set_context
                _notifier_set_context(app.bot, allowed_chat_id, asyncio.get_running_loop())
        except Exception as _ne:
            import logging as _log2
            _log2.getLogger(__name__).warning("[TelegramBridge] Notifier baslatılamadi: %s", _ne)

        await app.updater.start_polling()

        await asyncio.Event().wait()
    finally:
        _release_single_instance_lock()


if __name__ == "__main__":
    asyncio.run(main())

