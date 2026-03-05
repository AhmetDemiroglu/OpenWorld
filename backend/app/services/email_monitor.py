"""
Email Monitor Background Service
Scans Gmail every N minutes, triages with Ollama LLM, sends Telegram notifications.
"""
from __future__ import annotations

import asyncio
import base64
import email as email_lib
import html
import json
import logging
import os
import re
import time
import unicodedata
import uuid
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from ..config import settings
from ..secrets import decrypt_text
from ..database import mark_email_seen, get_seen_emails, unmark_email_seen

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Importance levels
# ---------------------------------------------------------------------------

CRITICAL = "CRITICAL"   # Aksiyon gerektiriyor, hemen bil
IMPORTANT = "IMPORTANT" # Oku, deÄŸerlendir
NOTICE = "NOTICE"       # Bilgi amaÃ§lÄ±, gÃ¶zden kaÃ§Ä±rma (deprecation, repo silme, model kaldÄ±rma vs)
NORMAL = "NORMAL"       # Atla
SPAM = "SPAM"           # Atla

_NOTIFY_LEVELS = {CRITICAL, IMPORTANT, NOTICE}
_DRAFT_LEVELS = {CRITICAL}  # Sadece bu seviyeler iÃ§in taslak Ã¼ret

_CHAR_FOLD_MAP = str.maketrans({
    "ı": "i",
    "İ": "i",
    "ş": "s",
    "Ş": "s",
    "ç": "c",
    "Ç": "c",
    "ğ": "g",
    "Ğ": "g",
    "ö": "o",
    "Ö": "o",
    "ü": "u",
    "Ü": "u",
})


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
# Gmail fetch â€“ only UNREAD
# ---------------------------------------------------------------------------

def _fetch_unread_emails(token: str, max_results: int = 30) -> List[Dict[str, Any]]:
    """Fetch unread emails from all tabs (inbox + promotions + updates + social)."""
    headers = {"Authorization": f"Bearer {token}"}
    # Include all tabs â€” critical mails often land in Promotions or Updates
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
            logger.error("Gmail 401 â€“ token expired, skipping this cycle")
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

    def unmark_seen(self, mail_id: str, subject: str = "", job_key: Optional[str] = None) -> None:
        self._seen_ids.discard(mail_id)
        if subject:
            try:
                self._seen_subjects.remove(subject)
            except ValueError:
                pass
        unmark_email_seen(mail_id)
        if job_key:
            key = job_key.lower()
            self._seen_job_keys.discard(key)
            unmark_email_seen(f"job_{key}")


# ---------------------------------------------------------------------------
# LLM Triage â€“ calls Ollama directly (no tools needed, just text)
# ---------------------------------------------------------------------------

_TRIAGE_PROMPT = """Sen bir e-posta Ã¶ncelik sÄ±nÄ±flandÄ±rÄ±cÄ±sÄ±sÄ±n.
KullanÄ±cÄ± profili: Ahmet, Full-Stack Developer, Ä°zmir. Teknolojiler: Vue.js, React, React Native, JS/TS, CSS, C# .NET Core, SQL Server. AI/ML, yapay zeka modelleri ve yazÄ±lÄ±m iÅŸ ilanlarÄ±yla ilgileniyor.

SINIFLANDIRMA KURALLARI (sÄ±rayla deÄŸerlendir):

CRITICAL â€“ Hemen bilmesi gerekiyor, aksiyon gerektirebilir:
- Hesap/gÃ¼venlik uyarÄ±larÄ± (ÅŸifre sÄ±fÄ±rlama, ÅŸÃ¼pheli giriÅŸ, 2FA)
- Fatura, Ã¶deme, abonelik bildirimleri
- GitHub: repo silinecek, fork kaldÄ±rÄ±lacak, depo arÅŸivlenecek
- Google/AWS/Azure/Vercel: servis kapatÄ±lÄ±yor, hesap askÄ±ya alÄ±ndÄ±
- npm/PyPI/NuGet: paket deprecated veya kaldÄ±rÄ±lÄ±yor (kullandÄ±ÄŸÄ±n teknolojiler iÃ§in)
- API deÄŸiÅŸikliÄŸi / breaking change bildirimleri (OpenAI, Anthropic, Google AI, Azure AI vb.)
- KiÅŸisel/acil yazÄ±ÅŸmalar (gerÃ§ek insanlardan, iÅŸ/proje baÄŸlamÄ±nda)
- YazÄ±lÄ±m iÅŸ ilanlarÄ± (Frontend, React, Vue.js, Ä°zmir veya remote pozisyonlar)

IMPORTANT â€“ OkumasÄ± gerekiyor ama hemen deÄŸil:
- Ä°lginÃ§ iÅŸ ilanlarÄ± (yukarÄ±dakiyle Ã¶rtÃ¼ÅŸmeyen ama deÄŸerlendirilmesi gereken pozisyonlar)
- GerÃ§ekten deÄŸerli teknik iÃ§erik veya bÃ¼lten (sadece konuya Ã¶zel, genel reklam deÄŸil)
- PR bildirimleri, proje gÃ¼ncellemeleri (kendi projeleri veya katkÄ±da bulunduÄŸu projeler)
- Konferans/etkinlik bildirimleri (teknik, Ã¼cretsiz veya deÄŸerli)

NOTICE â€“ Bilmesi gerekiyor ama aksiyon ÅŸart deÄŸil:
- AI model gÃ¼ncellemeleri, yeni model duyurularÄ± (GPT, Claude, Gemini, Mistral, Llama vb.)
- Framework/kÃ¼tÃ¼phane yeni sÃ¼rÃ¼m duyurularÄ± (React 19, Vue 4, Next.js vb.)
- Deprecation bildirimleri (kÄ±sa/orta vadeli, hemen aksiyon gerektirmeyen)
- Ã–nemli teknoloji haberleri (acquisition, kapatma, bÃ¼yÃ¼k deÄŸiÅŸim)
- GitHub Sponsors, aÃ§Ä±k kaynak duyurularÄ±, topluluk haberleri
- Servis fiyat deÄŸiÅŸiklikleri (kullandÄ±ÄŸÄ± araÃ§lar iÃ§in)

NORMAL â€“ AtlansÄ±n:
- Rutin bÃ¼ltenler, haftalÄ±k Ã¶zetler, digest mailler
- Sosyal medya bildirimleri (LinkedIn, Twitter vb.)
- Rutin PR bildirimleri (Ã¶nemsiz repolardan)
- Otomatik sistem raporlarÄ± (baÅŸarÄ±lÄ± build, deploy vs.)

SPAM â€“ Kesinlikle atlansÄ±n:
- Reklam, promosyon, indirim
- TanÄ±madÄ±ÄŸÄ± kiÅŸilerden satÄ±ÅŸ mailleri
- AlakasÄ±z listeler

Ä°Å Ä°LANI TEKRAR KONTROLÃœ:
EÄŸer bu email bir iÅŸ ilanÄ±ysa, job_key alanÄ±nÄ± doldur: "ÅŸirket_adÄ±|pozisyon_baÅŸlÄ±ÄŸÄ±" formatÄ±nda (kÃ¼Ã§Ã¼k harf, TÃ¼rkÃ§e karakter yok, boÅŸluk yerine - kullan).
Ã–rnek: "xyztech|senior-frontend-developer"

CEVAP FORMATI (SADECE JSON, baÅŸka hiÃ§bir ÅŸey):
{{"level": "CRITICAL|IMPORTANT|NOTICE|NORMAL|SPAM", "reason": "kÄ±sa TÃ¼rkÃ§e aÃ§Ä±klama (max 15 kelime)", "summary": "1-2 cÃ¼mlelik TÃ¼rkÃ§e Ã¶zet", "job_key": null}}

E-POSTA:
Kimden: {sender}
Konu: {subject}
Tarih: {date}
Ã–nizleme: {snippet}
"""


def _normalize_for_match(text: str) -> str:
    raw = (text or "").lower()
    raw = raw.translate(_CHAR_FOLD_MAP)
    raw = unicodedata.normalize("NFKD", raw)
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw


def _looks_personal_sender(sender: str) -> bool:
    sender_n = _normalize_for_match(sender)
    if any(token in sender_n for token in ("noreply", "no-reply", "mailer-daemon", "do-not-reply")):
        return False
    return bool(re.search(r"<[^>]+@[^>]+>", sender) or re.search(r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b", sender_n))


def _clean_display_text(text: str, limit: int = 240) -> str:
    value = str(text or "")
    value = re.sub(r"[\u200b-\u200f\u2060\ufeff]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    if limit and len(value) > limit:
        value = value[:limit - 3].rstrip() + "..."
    return value


def _extract_json_dict(raw_content: str) -> Optional[Dict[str, Any]]:
    text = (raw_content or "").strip()
    if not text:
        return None
    # Remove fenced markdown and model "thinking" wrappers if present.
    text = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE).replace("```", "").strip()
    text = re.sub(r"<think>[\s\S]*?</think>", " ", text, flags=re.IGNORECASE).strip()

    candidates: List[str] = [text]
    for m in re.finditer(r"\{[\s\S]*?\}", text):
        block = m.group(0).strip()
        if len(block) >= 2:
            candidates.append(block)

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue
    return None


def _derive_job_key(sender: str, subject: str) -> Optional[str]:
    s = _normalize_for_match(sender)
    subj = _normalize_for_match(subject)
    job_markers = ("job", "is ilani", "kariyer", "career", "frontend", "react", "vue", "developer", "muhendis")
    if not any(k in subj for k in job_markers):
        return None

    domain_part = ""
    m = re.search(r"@([a-z0-9.-]+)", s)
    if m:
        parts = m.group(1).split(".")
        domain_part = parts[-2] if len(parts) >= 2 else parts[0]
    if not domain_part:
        domain_part = "unknown-company"

    role = re.sub(r"[^a-z0-9\s-]", " ", subj)
    role = re.sub(r"\s+", "-", role).strip("-")
    role = "-".join(role.split("-")[:6]) or "role"
    return f"{domain_part}|{role}"


def _heuristic_triage(email: Dict[str, Any], reason_prefix: str = "heuristic") -> Dict[str, str]:
    sender = str(email.get("from", "") or "")
    subject = str(email.get("subject", "") or "")
    snippet = str(email.get("snippet", "") or "")
    labels = [str(x).upper() for x in (email.get("labels") or [])]

    blob = _normalize_for_match(f"{sender}\n{subject}\n{snippet}")
    sender_n = _normalize_for_match(sender)
    subject_n = _normalize_for_match(subject)
    snippet_n = _normalize_for_match(snippet)
    inbox_like = any(x in labels for x in ("INBOX", "CATEGORY_PERSONAL"))
    automated_sender = not _looks_personal_sender(sender)

    spam_terms = (
        "discount", "indirim", "kampanya", "promo", "promosyon", "sale", "firsat",
        "newsletter", "unsubscribe", "abone ol", "kupon", "coupon",
    )
    critical_terms = (
        "urgent", "acil", "action required", "hemen", "deadline", "due today",
        "security alert", "supheli giris", "sifre", "password", "2fa", "verify",
        "odeme", "payment", "fatura", "invoice",
        "deprecated", "deprecation", "breaking change", "kaldirilacak", "askiya alindi", "suspended",
        "offer letter", "is teklifi", "teklif mektubu",
    )
    meeting_terms = (
        "toplanti", "meeting", "meet", "calendar", "invite", "invitation",
        "katilim", "attendance", "schedule", "scheduled", "randevu",
    )
    urgent_time_terms = (
        "acil", "urgent", "yarin", "bugun", "today", "tomorrow", "asap",
        "hemen", "saat", "confirm", "teyit", "katiliminizi bildir",
    )
    job_subject_terms = (
        "is ilani", "job", "kariyer", "career", "application", "basvuru",
        "opening", "position", "pozisyon", "remote", "full time",
        "frontend", "react", "vue", "developer", "engineer", "muhendis",
        "interview", "mulakat", "technical interview", "case study",
    )
    job_sender_terms = ("indeed", "linkedin", "kariyer", "glassdoor", "secretcv", "workable", "jobs")
    important_terms = (
        "project update", "proposal", "teklif", "konferans", "etkinlik", "webinar",
        "release", "announcement",
    )
    notice_terms = (
        "release", "surum", "guncelleme", "update", "model", "api", "framework",
        "deprecate", "changelog", "maintenance", "scheduled",
    )
    meeting_blob = f"{subject_n}\n{snippet_n}"
    meeting_hit = any(t in meeting_blob for t in meeting_terms)
    urgent_meeting_hit = any(t in meeting_blob for t in urgent_time_terms)
    job_subject_hits = sum(1 for t in job_subject_terms if t in subject_n)
    job_sender_hit = any(t in sender_n for t in job_sender_terms)
    project_hit = any(t in blob for t in important_terms)

    if ("CATEGORY_PROMOTIONS" in labels or "CATEGORY_SOCIAL" in labels) and any(t in blob for t in spam_terms):
        return {"level": SPAM, "reason": f"{reason_prefix}: promosyon/sosyal", "summary": subject[:180], "job_key": None}
    if any(t in blob for t in critical_terms):
        return {
            "level": CRITICAL,
            "reason": f"{reason_prefix}: kritik anahtar kelime",
            "summary": (snippet or subject)[:220],
            "job_key": _derive_job_key(sender, subject),
        }
    if not automated_sender and meeting_hit and urgent_meeting_hit:
        return {
            "level": CRITICAL,
            "reason": f"{reason_prefix}: zaman hassas toplanti",
            "summary": (snippet or subject)[:220],
            "job_key": None,
        }
    if not automated_sender and meeting_hit and inbox_like:
        return {
            "level": IMPORTANT,
            "reason": f"{reason_prefix}: toplanti/planning",
            "summary": (snippet or subject)[:220],
            "job_key": None,
        }
    if (job_subject_hits >= 2) or (job_sender_hit and job_subject_hits >= 1):
        return {
            "level": IMPORTANT,
            "reason": f"{reason_prefix}: is firsati",
            "summary": (snippet or subject)[:220],
            "job_key": _derive_job_key(sender, subject),
        }
    if project_hit:
        return {
            "level": IMPORTANT,
            "reason": f"{reason_prefix}: onemli konu",
            "summary": (snippet or subject)[:220],
            "job_key": None,
        }
    if any(t in blob for t in notice_terms):
        return {
            "level": NOTICE,
            "reason": f"{reason_prefix}: bilgilendirme",
            "summary": (snippet or subject)[:220],
            "job_key": None,
        }
    if automated_sender:
        return {"level": NORMAL, "reason": f"{reason_prefix}: otomatik gonderici", "summary": subject[:180], "job_key": None}
    if ("CATEGORY_PROMOTIONS" in labels or "CATEGORY_SOCIAL" in labels) and len(subject_n) < 140:
        return {"level": NORMAL, "reason": f"{reason_prefix}: dusuk oncelik", "summary": subject[:180], "job_key": None}
    return {"level": NORMAL, "reason": f"{reason_prefix}: normal", "summary": (snippet or subject)[:180], "job_key": None}


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
        "format": "json",
        "options": {"temperature": 0.1, "num_predict": 200},
    }
    base = settings.ollama_base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=12.0)) as client:
            resp = await client.post(f"{base}/api/chat", json=payload)
            resp.raise_for_status()
            content = resp.json().get("message", {}).get("content", "")
            result = _extract_json_dict(content)
            if not isinstance(result, dict):
                logger.warning("LLM triage: JSON parse edilemedi, heuristic fallback. preview=%s", (content or "")[:180])
                return _heuristic_triage(email, reason_prefix="fallback")
            level = result.get("level", NORMAL)
            if level not in (CRITICAL, IMPORTANT, NOTICE, NORMAL, SPAM):
                level = NORMAL
            job_key = result.get("job_key") or _derive_job_key(email.get("from", ""), email.get("subject", ""))
            return {
                "level": level,
                "reason": result.get("reason", ""),
                "summary": result.get("summary", ""),
                "job_key": job_key,
            }
    except Exception as exc:
        logger.warning(f"LLM triage failed: {exc}")
        return _heuristic_triage(email, reason_prefix="fallback_exc")


# ---------------------------------------------------------------------------
# Telegram notification
# ---------------------------------------------------------------------------

_LEVEL_EMOJI = {
    CRITICAL: "[!]",
    IMPORTANT: "[*]",
    NOTICE: "[i]",
    NORMAL: "[-]",
    SPAM: "[x]",
}

_LEVEL_LABEL = {
    CRITICAL: "KRITIK",
    IMPORTANT: "ONEMLI",
    NOTICE: "BILGILENDIRME",
}


async def _send_telegram(text: str) -> bool:
    """Send a Telegram message to the allowed user."""
    token = settings.telegram_bot_token or ""
    if not token and settings.telegram_bot_token_enc:
        token = decrypt_text(settings.telegram_bot_token_enc)
    user_id = settings.telegram_allowed_user_id.strip()
    if not token or not user_id:
        logger.warning("Telegram not configured â€“ skipping notification")
        return False
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
                body = resp.text[:400]
                if resp.status_code == 400 and "can't parse entities" in body.lower():
                    fallback_payload = {
                        "chat_id": user_id,
                        "text": _telegram_plain_text(text),
                        "disable_web_page_preview": True,
                    }
                    retry = await client.post(url, json=fallback_payload)
                    if retry.status_code == 200:
                        logger.warning("Telegram HTML parse failed; plain-text fallback sent.")
                        return True
                    logger.error(f"Telegram fallback send failed: {retry.text[:200]}")
                logger.error(f"Telegram send failed: {body[:200]}")
                return False
            return True
    except Exception as exc:
        logger.error(f"Telegram send error: {exc}")
        return False


def _telegram_plain_text(text: str) -> str:
    plain = str(text or "")
    plain = re.sub(r"</?(?:b|i|u|code|pre)>", "", plain, flags=re.IGNORECASE)
    plain = plain.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    return html.unescape(plain)


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

_DRAFT_PROMPT = """Sen Ahmet'in e-posta asistanÄ±sÄ±n. AÅŸaÄŸÄ±daki e-postaya kÄ±sa, profesyonel ve TÃ¼rkÃ§e bir yanÄ±t taslaÄŸÄ± yaz.
YanÄ±t 3-5 cÃ¼mle olsun. Gereksiz uzatma. Sadece e-posta metnini yaz, baÅŸka hiÃ§bir ÅŸey ekleme.

E-POSTA:
Kimden: {sender}
Konu: {subject}
Ã–nizleme: {snippet}
Ã–nem: {level} â€“ {reason}
"""


async def _generate_draft_reply(email: Dict[str, Any], triage: Dict[str, str]) -> str:
    """LLM ile taslak e-posta yanÄ±tÄ± Ã¼ret."""
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


def _fallback_draft_reply(email: Dict[str, Any], triage: Dict[str, str]) -> str:
    subject_n = _normalize_for_match(str(email.get("subject", "") or ""))
    snippet_n = _normalize_for_match(str(email.get("snippet", "") or ""))
    blob = f"{subject_n}\n{snippet_n}"

    if any(term in blob for term in ("toplanti", "meeting", "invite", "calendar")):
        return (
            "Merhaba,\n\n"
            "Mailinizi aldım. Toplantı detaylarını not ettim; uygunluk durumumu "
            "kısa süre içinde net olarak paylaşacağım.\n\n"
            "Teşekkürler."
        )

    if any(term in blob for term in ("security", "password", "verify", "2fa", "sifre")):
        return (
            "Merhaba,\n\n"
            "Uyarınızı aldım. Konuyu hemen kontrol edip gerekli aksiyonu alacağım.\n\n"
            "Teşekkürler."
        )

    if any(term in blob for term in ("odeme", "payment", "invoice", "fatura")):
        return (
            "Merhaba,\n\n"
            "Mailinizi aldım. Ödeme/fatura konusunu inceleyip kısa süre içinde geri döneceğim.\n\n"
            "Teşekkürler."
        )

    return (
        "Merhaba,\n\n"
        "Mailinizi aldım. İnceleyip kısa süre içinde geri dönüş yapacağım.\n\n"
        "Teşekkürler."
    )


async def _send_telegram_with_inline(text: str, buttons: List[List[Dict]]) -> bool:
    """Send a Telegram message with inline keyboard buttons."""
    token = settings.telegram_bot_token or ""
    if not token and settings.telegram_bot_token_enc:
        token = decrypt_text(settings.telegram_bot_token_enc)
    user_id = settings.telegram_allowed_user_id.strip()
    if not token or not user_id:
        return False
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
                body = resp.text[:400]
                if resp.status_code == 400 and "can't parse entities" in body.lower():
                    fallback_payload = {
                        "chat_id": user_id,
                        "text": _telegram_plain_text(text),
                        "disable_web_page_preview": True,
                        "reply_markup": {"inline_keyboard": buttons},
                    }
                    retry = await client.post(url, json=fallback_payload)
                    if retry.status_code == 200:
                        logger.warning("Telegram inline HTML parse failed; plain-text fallback sent.")
                        return True
                    logger.error(f"Telegram inline fallback send failed: {retry.text[:200]}")
                logger.error(f"Telegram inline send failed: {body[:200]}")
                return False
            return True
    except Exception as exc:
        logger.error(f"Telegram inline send error: {exc}")
        return False


def _format_notification(email: Dict[str, Any], triage: Dict[str, str]) -> str:
    level = triage.get("level", NORMAL)
    emoji = _LEVEL_EMOJI.get(level, "[mail]")
    label = _LEVEL_LABEL.get(level, level)
    sender = html.escape(_clean_display_text(str(email.get("from", "Bilinmeyen") or "Bilinmeyen"), limit=160))
    subject = html.escape(_clean_display_text(str(email.get("subject", "(Konu yok)") or "(Konu yok)"), limit=180))
    summary = html.escape(_clean_display_text(str(triage.get("summary", "") or ""), limit=260))
    reason = html.escape(_clean_display_text(str(triage.get("reason", "") or ""), limit=120))
    date_str = html.escape(_clean_display_text(str(email.get("date", "") or ""), limit=80))

    lines = [
        f"{emoji} <b>{label} MAIL</b>",
        "",
        f"<b>Kimden:</b> {sender}",
        f"<b>Konu:</b> {subject}",
    ]
    if summary:
        lines.append(f"<b>Ozet:</b> {summary}")
    if reason:
        lines.append(f"<b>Neden:</b> {reason}")
    if date_str:
        lines.append(f"<b>Tarih:</b> {date_str}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main monitor class
# ---------------------------------------------------------------------------

class EmailMonitor:
    def __init__(self) -> None:
        self._running = False
        self._task: Optional[asyncio.Task] = None
        interval_min = max(1, min(int(getattr(settings, "bg_email_interval_min", 5) or 5), 5))
        self._interval = interval_min * 60
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
        important_batch: List[Tuple[str, str, str, Optional[str]]] = []
        notice_batch: List[Tuple[str, str, str, Optional[str]]] = []
        notified_total = 0
        level_counts: Dict[str, int] = {CRITICAL: 0, IMPORTANT: 0, NOTICE: 0, NORMAL: 0, SPAM: 0}

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
            level_counts[level] = int(level_counts.get(level, 0)) + 1

            # Job listing duplicate check (same company+role already seen)
            if job_key and self._dup_filter.is_duplicate_job(job_key):
                logger.debug(f"EmailMonitor: duplicate job listing skipped: {job_key}")
                self._dup_filter.mark_seen(mid, subject)  # mark ID seen to avoid re-triaging
                continue

            if level not in _NOTIFY_LEVELS:
                self._dup_filter.mark_seen(mid, subject, job_key=job_key)
                logger.debug(f"EmailMonitor: [{level}] {subject} (skipped)")
                continue

            notification = _format_notification(mail, triage)
            logger.info(f"EmailMonitor: [{level}] {subject}")

            if level in _DRAFT_LEVELS:
                # Generate draft reply + send with inline buttons (one-by-one for CRITICAL)
                draft_body = await _generate_draft_reply(mail, triage)
                if not draft_body:
                    draft_body = _fallback_draft_reply(mail, triage)

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
                    f"<b>Taslak Yanit:</b>\n<i>{html.escape(draft_body[:500])}</i>"
                )
                buttons = [[
                    {"text": "Gonder", "callback_data": f"draft_send:{draft_id}"},
                    {"text": "Atla", "callback_data": f"draft_skip:{draft_id}"},
                ]]
                sent = await _send_telegram_with_inline(draft_msg, buttons)
                if sent:
                    self._dup_filter.mark_seen(mid, subject, job_key=job_key)
                    self._notified_count += 1
                    notified_total += 1
                else:
                    pop_pending_draft(draft_id)
                    logger.warning("EmailMonitor: CRITICAL mail notification failed, will retry next cycle: %s", subject)
            elif level == NOTICE:
                notice_batch.append((notification, mid, subject, job_key))
            else:  # IMPORTANT
                important_batch.append((notification, mid, subject, job_key))
        # Send batched IMPORTANT notifications
        if important_batch:
            batch_text = "\n\n---------------\n\n".join(item[0] for item in important_batch)
            header = f"<b>{len(important_batch)} onemli mailiniz var</b>\n\n"
            sent = await _send_telegram(header + batch_text)
            if sent:
                for _, batch_mid, batch_subject, batch_job_key in important_batch:
                    self._dup_filter.mark_seen(batch_mid, batch_subject, job_key=batch_job_key)
                self._notified_count += len(important_batch)
                notified_total += len(important_batch)
            else:
                logger.warning("EmailMonitor: important batch notification failed, will retry next cycle")

        # Send batched NOTICE notifications (FYI digest)
        if notice_batch:
            batch_text = "\n\n-------------\n\n".join(item[0] for item in notice_batch)
            header = f"<b>Bilgine ({len(notice_batch)} bilgilendirme)</b>\n\n"
            sent = await _send_telegram(header + batch_text)
            if sent:
                for _, batch_mid, batch_subject, batch_job_key in notice_batch:
                    self._dup_filter.mark_seen(batch_mid, batch_subject, job_key=batch_job_key)
                self._notified_count += len(notice_batch)
                notified_total += len(notice_batch)
            else:
                logger.warning("EmailMonitor: notice batch notification failed, will retry next cycle")

        logger.info(
            "EmailMonitor: triage summary | critical=%s important=%s notice=%s normal=%s spam=%s notified=%s",
            level_counts.get(CRITICAL, 0),
            level_counts.get(IMPORTANT, 0),
            level_counts.get(NOTICE, 0),
            level_counts.get(NORMAL, 0),
            level_counts.get(SPAM, 0),
            notified_total,
        )

        if notified_total == 0 and not important_batch and not notice_batch:
            logger.info("EmailMonitor: no important emails this cycle")

