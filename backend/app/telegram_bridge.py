from __future__ import annotations

import atexit
import asyncio
import html as html_lib
import os
import re
from pathlib import Path
from typing import Optional

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


def _get_timeout_for_request(text: str) -> httpx.Timeout:
    """İstek turune gore timeout belirle."""
    text_lower = text.lower()
    
    # GORSEL ISLEME: OCR + analiz uzun surebilir (3 dakika)
    if "gorsel" in text_lower or "[kullanici bir gorsel" in text_lower:
        return httpx.Timeout(connect=10.0, read=180.0, write=10.0, pool=10.0)
    
    # HIZLI ISLEMLER: Direkt calisir, kisa timeout yeterli
    fast_patterns = [
        "ekran goruntusu", "screenshot", "desktop", "masaustu",
        "webcam", "web cam", "kamera", "fotograf cek", "fotoğraf çek", 
        "selfie", "anlik foto", "anılık foto", "camera",
        "ses kaydet", "ses kaydı", "mikrofon", "audio record", "voice record",
        "video kaydet", "video çek", "webcam video"
    ]
    if any(p in text_lower for p in fast_patterns):
        # Hizli islemler (screenshot, webcam, ses) 15sn icinde biter
        return httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)
    
    # NOTEBOOK DEVAM ETME: Cok uzun surebilir (5 dakika)
    if any(p in text_lower for p in ["devam", "not defter", "rapora devam"]):
        return httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0)
    
    # MASAUSTU OTOMASYON: VS Code, Codex, adim adim GUI islemleri (3 dakika)
    automation_patterns = [
        "vscode", "vs code", "codex", "copilot",
        "klasor ac", "klasörü aç", "programi ac", "programı aç",
        "uygulamayi ac", "uygulamayı aç",
        "tikla", "tıkla", "yaz ve", "bul ve",
        "masaustu", "masaüstü",
    ]
    if any(p in text_lower for p in automation_patterns) and any(
        p in text_lower for p in ["ac", "aç", "bul", "yaz", "tikla", "tıkla", "gir", "git"]
    ):
        return httpx.Timeout(connect=10.0, read=180.0, write=10.0, pool=10.0)
    
    # ARASTIRMA ISLEMLERI: Uzun surebilir (5 dakika)
    research_patterns = ["arastir", "rapor", "detayli", "tum haber", "haber tara",
                        "analiz", "research", "report", "pdf olustur", "word olustur"]
    if any(p in text_lower for p in research_patterns):
        # Arastirma icin 5 dakika
        return httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0)
    
    # STANDART: 2 dakika (LLM multi-step cevaplari icin 60sn yetersiz)
    return httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)


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
        # Timeout turune gore mesaj
        text_lower = text.lower()
        if "gorsel" in text_lower or "[kullanici bir gorsel" in text_lower:
            raise RuntimeError(
                "Gorsel analizi zaman asimina ugradi (5dk). Gorsel cok buyuk olabilir veya "
                "sistem yogun. Lutfen tekrar deneyin veya gorseli daha kucuk boyutta gonderin."
            ) from exc
        elif "devam" in text_lower or "not defter" in text_lower:
            raise RuntimeError(
                "Notebook devam islemi zaman asimina ugradi (5dk). "
                "Sistem cok yavas calisiyor olabilir. Lutfen biraz bekleyip tekrar 'devam et' yazin. "
                "Not defteri kaydedildi, veri kaybi yok."
            ) from exc
        elif any(p in text_lower for p in ["arastir", "rapor", "detayli"]):
            raise RuntimeError(
                "Arastirma zaman asimina ugradi (5dk) ancak not defterine kaydedildi. "
                "'Devam et' yazarak kaldigim yerden devam edebilirim."
            ) from exc
        elif any(p in text_lower for p in ["vscode", "vs code", "codex", "copilot", "ac", "aç"]):
            raise RuntimeError(
                "Masaustu otomasyon islemi zaman asimina ugradi (3dk). "
                "Bu tur cok adimli islemler bazen uzun surebilir. Lutfen tekrar deneyin."
            ) from exc
        else:
            raise RuntimeError(
                "Islem zaman asimina ugradi. Lutfen tekrar deneyin."
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


async def _check_incomplete_notebooks(session_id: str) -> Optional[str]:
    """Yarim kalan notebook var mi kontrol et, devam mesaji dondur."""
    try:
        from .tools.notebook_tools import tool_notebook_list
        result = tool_notebook_list()
        notebooks = result.get("notebooks", [])
        
        incomplete = [n for n in notebooks if n.get("status") == "Devam Ediyor"]
        if incomplete:
            latest = incomplete[0]  # En sonuncu
            return (
                f"\n\n💡 **Yarim kalan isiniz var:** `{latest['name']}`\n"
                f"İlerleme: {latest['progress']}\n"
                f"Devam etmek icin: \"{latest['name']} raporuna devam et\" yazabilirsiniz."
            )
    except:
        pass
    return None


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    if update.message is None:
        return
    
    session_id = f"telegram_{update.effective_user.id}"
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
        status_msg = await update.message.reply_text("📸 Gorsel algilandi, icerik okunuyor...")
        
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
                    "ℹ️ **Gorsel durumu:**\n"
                    "Gorselde okunabilir **metin bulunamadi**.\n"
                    "Bu bot gorsellerdeki yazilari OCR ile okuyabilir,\n"
                    "ama nesneleri/karakterleri goremez.\n\n"
                )
                if caption:
                    info_text += f"Isteginiz isleniyor: {caption}"
                else:
                    info_text += "Gorseli metin olarak anlatmak isterseniz yazabilirsiniz."
                
                await status_msg.edit_text(info_text)
            else:
                # Metin bulundu - devam et
                await status_msg.edit_text("✅ Gorseldeki metinler OCR ile okundu, analiz ediliyor...")
            
        except Exception as e:
            await status_msg.edit_text(f"⚠️ Gorsel islenirken sorun: {e}")
            # Yine de devam et - bos mesaj kontrolu yapilacak
            if caption:
                user_message = f"[Kullanici bir gorsel gonderdi. Aciklama: {caption}]"
            else:
                await update.message.reply_text("❌ Gorsel islenemedi. Lutfen metin olarak yazin.")
                return
    
    # 3. DOKUMAN (Resim dosyasi olarak gonderilmis olabilir)
    elif update.message.document:
        # Resim dosyasi mi kontrol et
        mime_type = update.message.document.mime_type or ""
        if mime_type.startswith("image/"):
            status_msg = await update.message.reply_text("📸 Gorsel (dokuman olarak gonderildi) algilandi, icerik okunuyor...")
            
            try:
                file = await context.bot.get_file(update.message.document.file_id)
                image_bytes = await file.download_as_bytearray()
                
                caption = update.message.caption or ""
                user_message = await _process_image_with_ocr(bytes(image_bytes), caption)
                
                await status_msg.edit_text("✅ Gorsel icerigi okundu, analiz ediliyor...")
            except Exception as e:
                await status_msg.edit_text(f"⚠️ Gorsel islenirken sorun: {e}")
                if caption:
                    user_message = f"[Kullanici bir gorsel gonderdi. Aciklama: {caption}]"
                else:
                    await update.message.reply_text("❌ Gorsel analiz edilemedi.")
                    return
        else:
            await update.message.reply_text("📎 Bu dokuman turunu henuz isleyemiyorum. Lutfen metin olarak yazin veya gorsel olarak gonderin.")
            return
    
    else:
        # Desteklenmeyen mesaj tipi
        return
    
    # Bos mesaj kontrolu
    if not user_message or not user_message.strip():
        await update.message.reply_text("⚠️ Mesaj icerigi bos. Lutfen metin yazin veya gorsel gonderin.")
        return
    
    # Agent'i cagir
    try:
        data = await call_agent(session_id, user_message)
        reply = data.get("reply", "")
        media_list = data.get("media") or []
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
                # Notebook var - gercekten kaydedildi
                timeout_msg = "⏳ **Islem zaman asimina ugradi.**\n\n"
                timeout_msg += "Bu tur kapsamli istekler icin:\n"
                timeout_msg += "1️⃣ Not defterine kaydedildi ✅\n"
                timeout_msg += "2️⃣ Bir sonraki mesajinizda kaldigim yerden devam edecegim\n"
                timeout_msg += "3️⃣ Veya \"rapora devam et\" yazabilirsiniz\n\n"
                timeout_msg += notebook_msg
            else:
                # Notebook yok - kaydedilemedi
                timeout_msg = "⏳ **Islem zaman asimina ugradi.**\n\n"
                timeout_msg += "Maalesef islem cok uzun surdu ve tamamlanamadi.\n"
                timeout_msg += "Lutfen daha kucuk parcalar halinde istekte bulunun:\n"
                timeout_msg += "- Once 'Irak-Iran petrolu hakkinda kisa bilgi ver'\n"
                timeout_msg += "- Sonra 'Petrol fiyatlarina etkisini anlat'\n\n"
                timeout_msg += "💡 Alternatif: Not defteri olusturup adim adim ilerleyebiliriz."
            
            reply = timeout_msg
        elif "ConnectError" in exc_type or "ConnectionRefused" in exc_type:
            reply = "❌ Agent sunucusuna baglanilamiyor. Backend calismiyor olabilir."
        elif "RSS" in err_text or "parse" in err_text.lower() or "XML" in err_text:
            reply = f"📰 Haber kaynagi hatasi: {err_text[:200]}"
        else:
            reply = f"❌ Hata: {err_text[:500]}"
        media_list = []

    # Send media first.
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[TELEGRAM] Sending {len(media_list)} media files")
    
    base_url = f"http://{settings.host}:{settings.port}"
    for m in media_list:
        media_url = m.get("url", "")
        media_type = m.get("type", "")
        caption = m.get("caption", m.get("filename", ""))
        logger.info(f"[TELEGRAM] Sending media: type={media_type}, url={media_url}")
        
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=15.0)) as client:
                file_resp = await client.get(f"{base_url}{media_url}")
                logger.info(f"[TELEGRAM] Download response: {file_resp.status_code}")
                if file_resp.status_code != 200:
                    logger.error(f"[TELEGRAM] Failed to download media: {file_resp.status_code}")
                    continue
                file_bytes = file_resp.content
                logger.info(f"[TELEGRAM] Downloaded {len(file_bytes)} bytes")

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
        # Hem metin hem fotoğraf mesajlarını dinle
        app.add_handler(MessageHandler(
            (filters.TEXT | filters.PHOTO | filters.Document.IMAGE) & ~filters.COMMAND, 
            on_message
        ))
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        await asyncio.Event().wait()
    finally:
        _release_single_instance_lock()


if __name__ == "__main__":
    asyncio.run(main())
