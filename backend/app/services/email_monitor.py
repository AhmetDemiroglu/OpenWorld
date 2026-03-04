"""
Email Monitor Background Service
Scans Gmail every N minutes, triages with Ollama LLM, sends Telegram notifications.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta
from difflib import SequenceMatcher
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

def _fetch_unread_emails(token: str, max_results: int = 20) -> List[Dict[str, Any]]:
    """Fetch unread emails from Gmail inbox."""
    headers = {"Authorization": f"Bearer {token}"}
    query = "is:unread in:inbox"

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
        self._refresh_cache()

    def _refresh_cache(self) -> None:
        seen = get_seen_emails(days=7)
        self._seen_ids = {s["id"] for s in seen}
        self._seen_subjects = [s["subject"] for s in seen]

    def is_duplicate(self, mail_id: str, subject: str) -> bool:
        if mail_id in self._seen_ids:
            return True
        for seen_subj in self._seen_subjects:
            if _subject_similarity(seen_subj, subject) > 0.85:
                return True
        return False

    def mark_seen(self, mail_id: str, subject: str) -> None:
        self._seen_ids.add(mail_id)
        self._seen_subjects.append(subject)
        mark_email_seen(mail_id, subject)


# ---------------------------------------------------------------------------
# LLM Triage – calls Ollama directly (no tools needed, just text)
# ---------------------------------------------------------------------------

_TRIAGE_PROMPT = """Sen bir e-posta önem derecesi belirleyicisisin.
Kullanıcı profili: Ahmet, Full-Stack Developer, İzmir'de yaşıyor, Frontend ağırlıklı (Vue.js, React, React Native, JS, CSS, HTML), Backend (C# .NET Core, SQL Server). AI/ML, yapay zeka modelleri, teknoloji trendleri ve yazılım iş ilanlarıyla yakından ilgileniyor.

Aşağıdaki e-postayı analiz et ve ÖNEMLİ olup olmadığını belirle.

KRİTİK olan durumlar:
- Yazılım iş ilanları (özellikle Frontend, İzmir, remote, React, Vue.js)
- AI model değişiklikleri (deprecation, yeni model, API değişikliği)
- Güvenlik uyarıları, hesap güvenliği
- Acil kişisel yazışmalar
- Fatura/ödeme bildirimleri
- Google, GitHub, npm güvenlik bildirimleri

ÖNEMLİ olan durumlar:
- Teknoloji haberleri/bültenleri (gerçekten ilginç olanlar)
- Proje güncellemeleri, PR bildirimleri
- Öğrenme fırsatları (kurslar, konferanslar)

NORMAL olan durumlar:
- Düzenli bültenler, haftalık özetler
- Sosyal medya bildirimleri
- Rutin güncellemeler

SPAM olan durumlar:
- Reklam, pazarlama, promosyon
- Tekrar eden/gereksiz bildirimler
- Tanımadığın kişilerden gelen satış mailleri

CEVAP FORMATI (SADECE JSON, başka hiçbir şey yazma):
{"level": "CRITICAL|IMPORTANT|NORMAL|SPAM", "reason": "kısa açıklama", "summary": "1-2 cümlelik özet"}

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
            return {
                "level": result.get("level", NORMAL),
                "reason": result.get("reason", ""),
                "summary": result.get("summary", ""),
            }
    except Exception as exc:
        logger.warning(f"LLM triage failed: {exc}")
        return {"level": NORMAL, "reason": "LLM triage failed", "summary": email.get("subject", "")}


# ---------------------------------------------------------------------------
# Telegram notification
# ---------------------------------------------------------------------------

_LEVEL_EMOJI = {
    CRITICAL: "🔴",
    IMPORTANT: "🟡",
    NORMAL: "⚪",
    SPAM: "🔇",
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


def _format_notification(email: Dict[str, Any], triage: Dict[str, str]) -> str:
    level = triage.get("level", NORMAL)
    emoji = _LEVEL_EMOJI.get(level, "📧")
    sender = email.get("from", "Bilinmeyen")
    subject = email.get("subject", "(Konu yok)")
    summary = triage.get("summary", "")
    reason = triage.get("reason", "")
    date_str = email.get("date", "")

    lines = [
        f"{emoji} <b>{'KRİTİK' if level == CRITICAL else 'ÖNEMLİ'} MAİL!</b>",
        "",
        f"📧 <b>Kimden:</b> {sender}",
        f"📋 <b>Konu:</b> {subject}",
    ]
    if summary:
        lines.append(f"📝 <b>Özet:</b> {summary}")
    if reason:
        lines.append(f"💡 <b>Neden önemli:</b> {reason}")
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
        important_batch: List[str] = []

        for email in emails:
            mid = email["id"]
            subject = email.get("subject", "")

            # Duplicate check
            if self._dup_filter.is_duplicate(mid, subject):
                continue

            # LLM triage
            triage = await _triage_email(email)
            level = triage.get("level", NORMAL)
            self._dup_filter.mark_seen(mid, subject)

            if level in _NOTIFY_LEVELS:
                notification = _format_notification(email, triage)
                important_batch.append(notification)
                self._notified_count += 1
                logger.info(f"EmailMonitor: [{level}] {subject}")
            else:
                logger.debug(f"EmailMonitor: [{level}] {subject} (skipped)")

        # Send batched notifications
        if important_batch:
            batch_text = "\n\n━━━━━━━━━━━━━━━\n\n".join(important_batch)
            header = f"📬 <b>{len(important_batch)} önemli mailiniz var</b>\n\n"
            await _send_telegram(header + batch_text)
        else:
            logger.info("EmailMonitor: no important emails this cycle")
