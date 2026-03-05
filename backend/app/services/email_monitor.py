"""
Email Monitor Background Service
Scans Gmail every N minutes, triages with Ollama LLM, sends Telegram notifications.
"""
from __future__ import annotations

import asyncio
import base64
import email as email_lib
import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from ..config import settings
from ..secrets import decrypt_text
from ..database import mark_email_seen, get_seen_emails

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Importance levels
# ---------------------------------------------------------------------------

CRITICAL = "CRITICAL"   # Aksiyon gerektiriyor, hemen bil
IMPORTANT = "IMPORTANT" # Oku, değerlendir
NOTICE = "NOTICE"       # Bilgi amaçlı, gözden kaçırma (deprecation, repo silme, model kaldırma vs)
NORMAL = "NORMAL"       # Atla
SPAM = "SPAM"           # Atla

_NOTIFY_LEVELS = {CRITICAL, IMPORTANT, NOTICE}
_DRAFT_LEVELS = {CRITICAL}  # Sadece bu seviyeler için taslak üret


def _get_secret(plain: str, encrypted: str) -> str:
    if plain:
        return plain
    if encrypted:
        try:
            return decrypt_text(encrypted)
        except Exception:
            return ""
    return ""


def _refresh_token() -> str:
    refresh = _get_secret(settings.gmail_refresh_token, settings.gmail_refresh_token_enc)
    if not refresh or not settings.gmail_client_id:
        return ""
    client_secret = _get_secret(settings.gmail_client_secret, settings.gmail_client_secret_enc)
    form: Dict[str, str] = {
        "client_id": settings.gmail_client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh,
    }
    if client_secret:
        form["client_secret"] = client_secret
    with httpx.Client(timeout=20) as c:
        resp = c.post("https://oauth2.googleapis.com/token", data=form)
        resp.raise_for_status()
    return resp.json().get("access_token", "")


def _get_gmail_token() -> str:
    token = _get_secret(settings.gmail_access_token, settings.gmail_access_token_enc)
    if not token:
        token = _refresh_token()
    return token


# ---------------------------------------------------------------------------
# Gmail fetch – only UNREAD
# ---------------------------------------------------------------------------

def _fetch_unread_emails(token: str, max_results: int = 30) -> List[Dict[str, Any]]:
    """Fetch unread emails from all tabs (inbox + promotions + updates + social)."""
    headers = {"Authorization": f"Bearer {token}"}
    # Include all tabs — critical mails often land in Promotions or Updates
    query = "is:unread (in:inbox OR in:promotions OR category:updates OR category:social) -in:spam -in:trash"

    with httpx.Client(timeout=30) as client:
        list_resp = client.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            params={"q": query, "maxResults": max_results},
            headers=headers,
        )
        # Auto-refresh on 401
        if list_resp.status_code == 401:
            new_token = _refresh_token()
            if new_token:
                token = new_token
                headers = {"Authorization": f"Bearer {token}"}
                list_resp = client.get(
                    "https://gmail.googleapis.com/gmail/v1/users/me/messages",
                    params={"q": query, "maxResults": max_results},
                    headers=headers,
                )
        if list_resp.status_code == 401:
            logger.error("Gmail 401 – token expired, skipping this cycle")
            return []
        list_resp.raise_for_status()

        msg_ids = [m["id"] for m in list_resp.json().get("messages", [])]
        results: List[Dict[str, Any]] = []
        for mid in msg_ids:
            msg_resp = client.get(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{mid}",
                params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
                headers=headers,
            )
            msg_resp.raise_for_status()
            payload = msg_resp.json()
            hdr_list = payload.get("payload", {}).get("headers", [])
            hmap = {h.get("name", "").lower(): h.get("value", "") for h in hdr_list}
            results.append({
                "id": mid,
                "from": hmap.get("from", ""),
                "subject": hmap.get("subject", ""),
                "date": hmap.get("date", ""),
                "snippet": payload.get("snippet", ""),
                "labels": payload.get("labelIds", []),
            })
    return results


# ---------------------------------------------------------------------------
# Duplicate filter
# ---------------------------------------------------------------------------

def _subject_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


class DuplicateFilter:
    def __init__(self) -> None:
        self._seen_job_keys: set = set()
        self._refresh_cache()

    def _refresh_cache(self) -> None:
        seen = get_seen_emails(days=30)
        self._seen_ids = {s["id"] for s in seen}
        self._seen_subjects = [s["subject"] for s in seen]
        # Restore job keys from stored subjects (encoded as "JOB:key" prefix)
        for s in seen:
            subj = s.get("subject", "")
            if subj.startswith("JOB:"):
                self._seen_job_keys.add(subj[4:])

    def is_duplicate(self, mail_id: str, subject: str) -> bool:
        if mail_id in self._seen_ids:
            return True
        for seen_subj in self._seen_subjects:
            if seen_subj.startswith("JOB:"):
                continue  # job keys compared separately
            if _subject_similarity(seen_subj, subject) > 0.85:
                return True
        return False

    def is_duplicate_job(self, job_key: str) -> bool:
        """Returns True if we've already seen this job (company+role)."""
        return job_key.lower() in self._seen_job_keys

    def mark_seen(self, mail_id: str, subject: str, job_key: Optional[str] = None) -> None:
        self._seen_ids.add(mail_id)
        self._seen_subjects.append(subject)
        mark_email_seen(mail_id, subject)
        if job_key:
            key = job_key.lower()
            self._seen_job_keys.add(key)
            # Also persist so it survives restart (encode in subject with prefix)
            mark_email_seen(f"job_{key}", f"JOB:{key}")


# ---------------------------------------------------------------------------
# LLM Triage – calls Ollama directly (no tools needed, just text)
# ---------------------------------------------------------------------------

_TRIAGE_PROMPT = """Sen bir e-posta öncelik sınıflandırıcısısın.
Kullanıcı profili: Ahmet, Full-Stack Developer, İzmir. Teknolojiler: Vue.js, React, React Native, JS/TS, CSS, C# .NET Core, SQL Server. AI/ML, yapay zeka modelleri ve yazılım iş ilanlarıyla ilgileniyor.

SINIFLANDIRMA KURALLARI (sırayla değerlendir):

CRITICAL – Hemen bilmesi gerekiyor, aksiyon gerektirebilir:
- Hesap/güvenlik uyarıları (şifre sıfırlama, şüpheli giriş, 2FA)
- Fatura, ödeme, abonelik bildirimleri
- GitHub: repo silinecek, fork kaldırılacak, depo arşivlenecek
- Google/AWS/Azure/Vercel: servis kapatılıyor, hesap askıya alındı
- npm/PyPI/NuGet: paket deprecated veya kaldırılıyor (kullandığın teknolojiler için)
- API değişikliği / breaking change bildirimleri (OpenAI, Anthropic, Google AI, Azure AI vb.)
- Kişisel/acil yazışmalar (gerçek insanlardan, iş/proje bağlamında)
- Yazılım iş ilanları (Frontend, React, Vue.js, İzmir veya remote pozisyonlar)

IMPORTANT – Okuması gerekiyor ama hemen değil:
- İlginç iş ilanları (yukarıdakiyle örtüşmeyen ama değerlendirilmesi gereken pozisyonlar)
- Gerçekten değerli teknik içerik veya bülten (sadece konuya özel, genel reklam değil)
- PR bildirimleri, proje güncellemeleri (kendi projeleri veya katkıda bulunduğu projeler)
- Konferans/etkinlik bildirimleri (teknik, ücretsiz veya değerli)

NOTICE – Bilmesi gerekiyor ama aksiyon şart değil:
- AI model güncellemeleri, yeni model duyuruları (GPT, Claude, Gemini, Mistral, Llama vb.)
- Framework/kütüphane yeni sürüm duyuruları (React 19, Vue 4, Next.js vb.)
- Deprecation bildirimleri (kısa/orta vadeli, hemen aksiyon gerektirmeyen)
- Önemli teknoloji haberleri (acquisition, kapatma, büyük değişim)
- GitHub Sponsors, açık kaynak duyuruları, topluluk haberleri
- Servis fiyat değişiklikleri (kullandığı araçlar için)

NORMAL – Atlansın:
- Rutin bültenler, haftalık özetler, digest mailler
- Sosyal medya bildirimleri (LinkedIn, Twitter vb.)
- Rutin PR bildirimleri (önemsiz repolardan)
- Otomatik sistem raporları (başarılı build, deploy vs.)

SPAM – Kesinlikle atlansın:
- Reklam, promosyon, indirim
- Tanımadığı kişilerden satış mailleri
- Alakasız listeler

İŞ İLANI TEKRAR KONTROLÜ:
Eğer bu email bir iş ilanıysa, job_key alanını doldur: "şirket_adı|pozisyon_başlığı" formatında (küçük harf, Türkçe karakter yok, boşluk yerine - kullan).
Örnek: "xyztech|senior-frontend-developer"

CEVAP FORMATI (SADECE JSON, başka hiçbir şey):
{{"level": "CRITICAL|IMPORTANT|NOTICE|NORMAL|SPAM", "reason": "kısa Türkçe açıklama (max 15 kelime)", "summary": "1-2 cümlelik Türkçe özet", "job_key": null}}

E-POSTA:
Kimden: {sender}
Konu: {subject}
Tarih: {date}
Önizleme: {snippet}
"""


async def _triage_email(email: Dict[str, Any]) -> Dict[str, str]:
    """Call Ollama to classify an email."""
    prompt = _TRIAGE_PROMPT.format(
        sender=email.get("from", ""),
        subject=email.get("subject", ""),
        date=email.get("date", ""),
        snippet=email.get("snippet", ""),
    )
    messages = [{"role": "user", "content": prompt}]
    payload = {
        "model": settings.ollama_model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 200},
    }
    base = settings.ollama_base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            resp = await client.post(f"{base}/api/chat", json=payload)
            resp.raise_for_status()
            content = resp.json().get("message", {}).get("content", "")
            # Parse JSON from response
            content = content.strip()
            # Handle markdown code blocks
            if content.startswith("```"):
                content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            result = json.loads(content)
            level = result.get("level", NORMAL)
            if level not in (CRITICAL, IMPORTANT, NOTICE, NORMAL, SPAM):
                level = NORMAL
            return {
                "level": level,
                "reason": result.get("reason", ""),
                "summary": result.get("summary", ""),
                "job_key": result.get("job_key") or None,
            }
    except Exception as exc:
        logger.warning(f"LLM triage failed: {exc}")
        return {"level": NORMAL, "reason": "LLM triage failed", "summary": email.get("subject", ""), "job_key": None}


# ---------------------------------------------------------------------------
# Telegram notification
# ---------------------------------------------------------------------------

_LEVEL_EMOJI = {
    CRITICAL: "🔴",
    IMPORTANT: "🟡",
    NOTICE: "📢",
    NORMAL: "⚪",
    SPAM: "🔇",
}

_LEVEL_LABEL = {
    CRITICAL: "KRİTİK",
    IMPORTANT: "ÖNEMLİ",
    NOTICE: "BİLGİLENDİRME",
}


async def _send_telegram(text: str) -> None:
    """Send a Telegram message to the allowed user."""
    token = settings.telegram_bot_token or ""
    if not token and settings.telegram_bot_token_enc:
        token = decrypt_text(settings.telegram_bot_token_enc)
    user_id = settings.telegram_allowed_user_id.strip()
    if not token or not user_id:
        logger.warning("Telegram not configured – skipping notification")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": user_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                logger.error(f"Telegram send failed: {resp.text[:200]}")
    except Exception as exc:
        logger.error(f"Telegram send error: {exc}")


# ---------------------------------------------------------------------------
# Pending draft storage (shared with telegram_bridge via file)
# ---------------------------------------------------------------------------

def _drafts_file() -> Path:
    from ..config import settings as _settings
    p = _settings.data_path / "pending_drafts.json"
    if not p.exists():
        p.write_text("{}", encoding="utf-8")
    return p


def _load_drafts() -> Dict[str, Any]:
    try:
        return json.loads(_drafts_file().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_drafts(drafts: Dict[str, Any]) -> None:
    _drafts_file().write_text(json.dumps(drafts, ensure_ascii=False, indent=2), encoding="utf-8")


def save_pending_draft(draft_id: str, data: Dict[str, Any]) -> None:
    drafts = _load_drafts()
    drafts[draft_id] = data
    _save_drafts(drafts)


def pop_pending_draft(draft_id: str) -> Optional[Dict[str, Any]]:
    drafts = _load_drafts()
    data = drafts.pop(draft_id, None)
    if data is not None:
        _save_drafts(drafts)
    return data


# ---------------------------------------------------------------------------
# Gmail Send API
# ---------------------------------------------------------------------------

def send_email_via_gmail(token: str, to: str, subject: str, body: str, thread_id: Optional[str] = None) -> bool:
    """Send an email via Gmail API. Returns True on success."""
    msg = MIMEText(body, "plain", "utf-8")
    msg["to"] = to
    msg["subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    payload: Dict[str, Any] = {"raw": raw}
    if thread_id:
        payload["threadId"] = thread_id
    try:
        with httpx.Client(timeout=20) as client:
            resp = client.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
            )
            if resp.status_code == 401:
                new_token = _refresh_token()
                if not new_token:
                    return False
                resp = client.post(
                    "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                    headers={"Authorization": f"Bearer {new_token}"},
                    json=payload,
                )
            resp.raise_for_status()
            logger.info(f"Email sent to {to}: {subject}")
            return True
    except Exception as exc:
        logger.error(f"Gmail send failed: {exc}")
        return False


# ---------------------------------------------------------------------------
# LLM draft reply generation
# ---------------------------------------------------------------------------

_DRAFT_PROMPT = """Sen Ahmet'in e-posta asistanısın. Aşağıdaki e-postaya kısa, profesyonel ve Türkçe bir yanıt taslağı yaz.
Yanıt 3-5 cümle olsun. Gereksiz uzatma. Sadece e-posta metnini yaz, başka hiçbir şey ekleme.

E-POSTA:
Kimden: {sender}
Konu: {subject}
Önizleme: {snippet}
Önem: {level} – {reason}
"""


async def _generate_draft_reply(email: Dict[str, Any], triage: Dict[str, str]) -> str:
    """LLM ile taslak e-posta yanıtı üret."""
    prompt = _DRAFT_PROMPT.format(
        sender=email.get("from", ""),
        subject=email.get("subject", ""),
        snippet=email.get("snippet", ""),
        level=triage.get("level", ""),
        reason=triage.get("reason", ""),
    )
    payload = {
        "model": settings.ollama_model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 300},
    }
    base = settings.ollama_base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            resp = await client.post(f"{base}/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json().get("message", {}).get("content", "").strip()
    except Exception as exc:
        logger.warning(f"Draft generation failed: {exc}")
        return ""


async def _send_telegram_with_inline(text: str, buttons: List[List[Dict]]) -> None:
    """Send a Telegram message with inline keyboard buttons."""
    token = settings.telegram_bot_token or ""
    if not token and settings.telegram_bot_token_enc:
        token = decrypt_text(settings.telegram_bot_token_enc)
    user_id = settings.telegram_allowed_user_id.strip()
    if not token or not user_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": user_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "reply_markup": {"inline_keyboard": buttons},
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                logger.error(f"Telegram inline send failed: {resp.text[:200]}")
    except Exception as exc:
        logger.error(f"Telegram inline send error: {exc}")


def _format_notification(email: Dict[str, Any], triage: Dict[str, str]) -> str:
    level = triage.get("level", NORMAL)
    emoji = _LEVEL_EMOJI.get(level, "📧")
    label = _LEVEL_LABEL.get(level, level)
    sender = email.get("from", "Bilinmeyen")
    subject = email.get("subject", "(Konu yok)")
    summary = triage.get("summary", "")
    reason = triage.get("reason", "")
    date_str = email.get("date", "")

    lines = [
        f"{emoji} <b>{label} MAİL</b>",
        "",
        f"📧 <b>Kimden:</b> {sender}",
        f"📋 <b>Konu:</b> {subject}",
    ]
    if summary:
        lines.append(f"📝 <b>Özet:</b> {summary}")
    if reason:
        lines.append(f"💡 {reason}")
    if date_str:
        lines.append(f"⏰ {date_str}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main monitor class
# ---------------------------------------------------------------------------

class EmailMonitor:
    def __init__(self) -> None:
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._interval = getattr(settings, "bg_email_interval_min", 15) * 60
        self._dup_filter = DuplicateFilter()
        self._last_scan: Optional[float] = None
        self._scan_count = 0
        self._notified_count = 0

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            f"EmailMonitor started (interval={self._interval}s)"
        )

    def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("EmailMonitor stopped")

    @property
    def status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "interval_min": self._interval // 60,
            "last_scan": self._last_scan,
            "scan_count": self._scan_count,
            "notified_count": self._notified_count,
        }

    async def _loop(self) -> None:
        # Small initial delay so app finishes startup
        await asyncio.sleep(10)
        while self._running:
            try:
                await self._scan()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception(f"EmailMonitor scan error: {exc}")
            await asyncio.sleep(self._interval)

    async def _scan(self) -> None:
        logger.info("EmailMonitor: scanning unread mails...")
        self._last_scan = time.time()
        self._scan_count += 1

        token = _get_gmail_token()
        if not token:
            logger.warning("EmailMonitor: no Gmail token available, skipping")
            return

        emails = _fetch_unread_emails(token, max_results=20)
        if not emails:
            logger.info("EmailMonitor: no unread emails")
            return

        logger.info(f"EmailMonitor: {len(emails)} unread emails found")
        important_batch: List[str] = []  # IMPORTANT mails
        notice_batch: List[str] = []     # NOTICE mails (FYI)

        for mail in emails:
            mid = mail["id"]
            subject = mail.get("subject", "")

            # Duplicate check (ID + subject similarity)
            if self._dup_filter.is_duplicate(mid, subject):
                continue

            # LLM triage
            triage = await _triage_email(mail)
            level = triage.get("level", NORMAL)
            job_key = triage.get("job_key")

            # Job listing duplicate check (same company+role already seen)
            if job_key and self._dup_filter.is_duplicate_job(job_key):
                logger.debug(f"EmailMonitor: duplicate job listing skipped: {job_key}")
                self._dup_filter.mark_seen(mid, subject)  # mark ID seen to avoid re-triaging
                continue

            self._dup_filter.mark_seen(mid, subject, job_key=job_key)

            if level not in _NOTIFY_LEVELS:
                logger.debug(f"EmailMonitor: [{level}] {subject} (skipped)")
                continue

            notification = _format_notification(mail, triage)
            self._notified_count += 1
            logger.info(f"EmailMonitor: [{level}] {subject}")

            if level in _DRAFT_LEVELS:
                # Generate draft reply + send with inline buttons (one-by-one for CRITICAL)
                draft_body = await _generate_draft_reply(mail, triage)
                if draft_body:
                    draft_id = str(uuid.uuid4())[:8]
                    sender_addr = mail.get("from", "")
                    save_pending_draft(draft_id, {
                        "to": sender_addr,
                        "subject": f"Re: {subject}",
                        "body": draft_body,
                        "email_id": mid,
                    })
                    draft_msg = (
                        f"{notification}\n\n"
                        f"✉️ <b>Taslak Yanıt:</b>\n<i>{draft_body[:500]}</i>"
                    )
                    buttons = [[
                        {"text": "✅ Gönder", "callback_data": f"draft_send:{draft_id}"},
                        {"text": "❌ Atla", "callback_data": f"draft_skip:{draft_id}"},
                    ]]
                    await _send_telegram_with_inline(draft_msg, buttons)
                else:
                    important_batch.append(notification)
            elif level == NOTICE:
                notice_batch.append(notification)
            else:  # IMPORTANT
                important_batch.append(notification)

        # Send batched IMPORTANT notifications
        if important_batch:
            batch_text = "\n\n━━━━━━━━━━━━━━━\n\n".join(important_batch)
            header = f"📬 <b>{len(important_batch)} önemli mailiniz var</b>\n\n"
            await _send_telegram(header + batch_text)

        # Send batched NOTICE notifications (FYI digest)
        if notice_batch:
            batch_text = "\n\n─────────────\n\n".join(notice_batch)
            header = f"📢 <b>Bilgine ({len(notice_batch)} bilgilendirme)</b>\n\n"
            await _send_telegram(header + batch_text)

        if not important_batch and not notice_batch:
            logger.info("EmailMonitor: no important emails this cycle")
