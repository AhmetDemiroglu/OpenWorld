"""
async_research.py â€” Otonom arka plan arastirma araci.
tool_research_async: Aninda yanitlar, arka planda arastirip Telegram'a bildirir.
Cikti: PDF rapor (reportlab ile) + Telegram ozet mesaji.
"""
from __future__ import annotations

import re
import threading
import time
import unicodedata
import traceback
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from urllib.parse import parse_qs, unquote, urlsplit


# â”€â”€ Yardimci: konuya ozgu sorgular â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _normalize_ascii(value: str) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _generate_smart_queries(topic: str) -> list:
    """Konuya ozgu, genis kapsama sahip alt sorgular uret."""
    stop_words = {
        "bir", "ve", "ile", "icin", "hakkinda", "konulu", "detayli", "arastirma", "rapor",
        "istiyorum", "yapmani", "hazirla", "bana", "gonder", "olusturmani", "yazacagin",
        "cevirecek", "buradan", "gondermeni", "lutfen", "bul", "getir", "nihai", "durumda",
        "pdfe", "pdf", "worde", "word", "olasi", "mevcut",
    }
    raw_words = re.findall(r"[^\W_]+", topic, flags=re.UNICODE)
    words = [w for w in raw_words if len(w) > 2 and _normalize_ascii(w).lower() not in stop_words]
    base = " ".join(words[:12]).strip() or topic[:180].strip()
    base_ascii = _normalize_ascii(base)

    queries: list[str] = []
    for q in (base, base_ascii):
        if q and q not in queries:
            queries.append(q)

    lower_topic = _normalize_ascii(topic).lower()
    if any(k in lower_topic for k in ("iran", "israil", "israel", "abd", "us", "savas", "war", "catisma")):
        queries.extend(
            [
                f"{base_ascii} son dakika gelismeler",
                f"{base_ascii} military situation latest",
                f"{base_ascii} conflict timeline",
                "Iran Israel US war latest updates",
            ]
        )
    if any(k in lower_topic for k in ("finans", "piyasa", "borsa", "doviz", "emtia", "petrol", "altin", "ekonomi")):
        queries.extend(
            [
                f"{base_ascii} finansal etkiler",
                f"{base_ascii} market impact analysis",
                f"{base_ascii} oil gold forex reaction",
                "Iran Israel war financial market impact",
            ]
        )

    queries.extend(
        [
            f"{base_ascii} analiz",
            f"{base_ascii} experts commentary",
        ]
    )
    dedup: list[str] = []
    seen: set[str] = set()
    for q in queries:
        cleaned = re.sub(r"\s+", " ", q).strip()
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        dedup.append(cleaned)
    return dedup[:8]


def _decode_bing_click_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    if "bing.com/news/apiclick" not in raw.lower():
        return raw
    try:
        parsed = urlsplit(raw)
        query = parse_qs(parsed.query)
        target = (query.get("url", [""])[0] or "").strip()
        if target:
            decoded = unquote(target)
            if decoded.startswith("http://") or decoded.startswith("https://"):
                return decoded
    except Exception:
        return raw
    return raw


def _extract_llm_text(resp: Any) -> str:
    if isinstance(resp, str):
        return resp.strip()
    if isinstance(resp, dict):
        msg = resp.get("message")
        if isinstance(msg, dict):
            content = msg.get("content", "")
            if isinstance(content, str):
                return content.strip()
        content = resp.get("content", "")
        if isinstance(content, str):
            return content.strip()
    return ""


def _is_low_signal_content(text: str) -> bool:
    raw = (text or "").strip()
    if len(raw) < 140:
        return True
    lowered = raw.lower()
    bad_markers = (
        "google news",
        "enable javascript",
        "access denied",
        "captcha",
        "forbidden",
        "bad request",
        "error 404",
        "not found",
    )
    if any(marker in lowered for marker in bad_markers):
        return True
    alpha_count = sum(1 for ch in raw if ch.isalpha())
    return alpha_count < 110


def _build_fallback_synthesis(topic: str, read_contents: list[dict], max_items: int = 12) -> str:
    lines: list[str] = [
        f"## Yonetici Ozeti",
        f"Bu rapor, `{topic}` konusu icin toplanan kaynaklardan derlenmistir.",
        "",
        "## Temel Bulgular",
    ]
    used = 0
    for idx, rc in enumerate(read_contents[:max_items], start=1):
        title = str(rc.get("title", "")).strip() or f"Kaynak {idx}"
        source = str(rc.get("source", "")).strip() or "Bilinmiyor"
        pub_date = str(rc.get("pub_date", "")).strip() or "Bilinmiyor"
        content = str(rc.get("content", "")).strip()
        summary = content[:420].replace("\n", " ")
        lines.append(f"- **[S{idx}] {title}** ({source}, {pub_date})")
        if summary:
            lines.append(f"  - Ozet: {summary}")
        used += 1
    if used == 0:
        lines.append("- Kullanilabilir kaynak icerigi bulunamadi.")
    lines.extend(
        [
            "",
            "## Sinirlar ve Guven",
            "- Bazi kaynaklarda icerik cekimi sinirli olabilir.",
            "- Bulgu seti, erisilebilen kaynak metinleri ile sinirlidir.",
            "- Kritik kararlar oncesinde birincil kaynaklardan manuel dogrulama onerilir.",
        ]
    )
    return "\n".join(lines).strip()


def _error_brief(exc: Exception) -> str:
    text = str(exc or "").strip()
    if text:
        return text
    name = type(exc).__name__
    return name or "UnknownError"


def _looks_like_turkish_text(text: str) -> bool:
    sample = (text or "").lower()
    if not sample:
        return False
    if any(ch in sample for ch in ("ç", "ğ", "ı", "ö", "ş", "ü")):
        return True
    markers = (" ve ", " ile ", " olarak ", " için ", " kaynak", " piyasa", " savaş", " etki")
    return sum(1 for m in markers if m in sample) >= 2


# â”€â”€ PDF olusturucu â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _write_pdf(report_path: Path, topic: str, read_contents: list, all_sources: list,
               elapsed: int, report_style: str, synthesis_text: str = "") -> str:
    """reportlab ile PDF olustur. Ozet metni (str) dondurur."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, HRFlowable, PageBreak
    )
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    # Turkce karakter destegi: Arial/DejaVu dene
    _FONT = "Helvetica"
    try:
        import os
        font_dirs = [
            r"C:\Windows\Fonts",
            "/usr/share/fonts/truetype/dejavu",
            "/usr/share/fonts",
        ]
        for d in font_dirs:
            candidate = Path(d) / "arial.ttf"
            if candidate.exists():
                pdfmetrics.registerFont(TTFont("TurkFont", str(candidate)))
                _FONT = "TurkFont"
                break
            candidate2 = Path(d) / "DejaVuSans.ttf"
            if candidate2.exists():
                pdfmetrics.registerFont(TTFont("TurkFont", str(candidate2)))
                _FONT = "TurkFont"
                break
    except Exception:
        pass

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", fontName=_FONT, fontSize=18, spaceAfter=10, textColor=colors.HexColor("#1a1a2e"), leading=22)
    h2 = ParagraphStyle("H2", fontName=_FONT, fontSize=13, spaceAfter=6, textColor=colors.HexColor("#16213e"), leading=18)
    body = ParagraphStyle("Body", fontName=_FONT, fontSize=10, spaceAfter=6, leading=14)
    meta = ParagraphStyle("Meta", fontName=_FONT, fontSize=9, textColor=colors.grey, spaceAfter=4)
    url_style = ParagraphStyle("URL", fontName=_FONT, fontSize=8, textColor=colors.blue, spaceAfter=8)

    story = []

    # Baslik
    story.append(Paragraph(f"Araştırma Raporu", h1))
    story.append(Paragraph(topic, h2))
    story.append(Paragraph(
        f"Tarih: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC  |  "
        f"Stil: {report_style}  |  Kaynak: {len(read_contents)}  |  Sure: {elapsed}s",
        meta,
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e0e0e0"), spaceAfter=12))

    if not read_contents:
        if synthesis_text:
            story.append(Paragraph("Sentezlenmiş Araştırma Sonucu", h2))
            for line in synthesis_text.split('\n'):
                line = line.strip()
                if not line:
                    story.append(Spacer(1, 6))
                    continue
                if line.startswith('### '):
                    story.append(Paragraph(line[4:].replace("<", "&lt;").replace(">", "&gt;"), h2))
                elif line.startswith('## '):
                    story.append(Paragraph(line[3:].replace("<", "&lt;").replace(">", "&gt;"), h1))
                elif line.startswith('# '):
                    story.append(Paragraph(line[2:].replace("<", "&lt;").replace(">", "&gt;"), h1))
                elif line.startswith('- ') or line.startswith('* '):
                    story.append(Paragraph(f"• {line[2:].replace('<', '&lt;').replace('>', '&gt;')}", body))
                else:
                    story.append(Paragraph(line.replace("<", "&lt;").replace(">", "&gt;"), body))
            story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e0e0e0"), spaceAfter=12))
        story.append(Paragraph("Okunabilir kaynak bulunamadı. Haber başlıkları:", h2))
        for item in all_sources[:8]:
            title = (item.get("title") or "")[:120]
            summary = (item.get("summary") or "")[:200]
            story.append(Paragraph(f"<b>{title}</b>", body))
            if summary:
                story.append(Paragraph(summary, body))
            story.append(Spacer(1, 4))
    else:
        if synthesis_text:
            story.append(Paragraph("Sentezlenmiş Araştırma Sonucu", h2))
            for line in synthesis_text.split('\n'):
                line = line.strip()
                if not line:
                    story.append(Spacer(1, 6))
                    continue
                # Handle basic markdown headings
                if line.startswith('### '):
                    story.append(Paragraph(line[4:].replace("<", "&lt;").replace(">", "&gt;"), h2))
                elif line.startswith('## '):
                    story.append(Paragraph(line[3:].replace("<", "&lt;").replace(">", "&gt;"), h1))
                elif line.startswith('# '):
                    story.append(Paragraph(line[2:].replace("<", "&lt;").replace(">", "&gt;"), h1))
                elif line.startswith('- ') or line.startswith('* '):
                    story.append(Paragraph(f"• {line[2:].replace('<', '&lt;').replace('>', '&gt;')}", body))
                else:
                    story.append(Paragraph(line.replace("<", "&lt;").replace(">", "&gt;"), body))
            story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e0e0e0"), spaceAfter=12))
            
        story.append(Paragraph("Kullanılan Kaynaklar", h2))
        for i, rc in enumerate(read_contents, 1):
            title = (rc.get("title") or f"Kaynak {i}")[:120]
            url = (rc.get("url") or "")[:200]
            story.append(Paragraph(f"{i}. {title}", body))
            if url:
                story.append(Paragraph(url, url_style))
            story.append(Spacer(1, 4))

    doc = SimpleDocTemplate(
        str(report_path),
        pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )
    doc.build(story)

    # Ozet metni (Telegram mesaji icin)
    titles = [rc.get("title", "")[:60] for rc in read_contents[:4]]
    titles_text = "\n".join(f"  - {t}" for t in titles) if titles else "  (kaynak bulunamadı)"
    summary_text = (
        f"📋 <b>Araştırma Özeti</b>\n\n"
        f"<b>Konu:</b> {topic[:100]}\n"
        f"<b>Kaynak sayısı:</b> {len(read_contents)}\n"
        f"<b>Süre:</b> {elapsed} saniye\n\n"
        f"<b>Öne çıkan kaynaklar:</b>\n{titles_text}\n\n"
        f"Detaylı rapor aşağıdaki PDF dosyasında 👇"
    )
    return summary_text


# â”€â”€ Ana tool â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def tool_research_async(
    topic: str,
    report_style: str = "standard",
    max_sources: int = 24,
    out_path: str = "",
) -> Dict[str, Any]:
    """Araştırmayı ARKA PLANDA başlatır. Hemen 'Araştırma başladı' mesajı dön.
    Araştırma bitince Telegram'a özet mesaj + PDF rapor dosyası gönderilir.

    Args:
        topic: Araştırılacak konu (ne kadar detaylı, o kadar iyi)
        report_style: standard, technical, academic, brief
        max_sources: Kullanılacak max kaynak sayısı (varsayılan: 24)
        out_path: Çıktı PDF dosyası yolu (opsiyonel, boş bırakılırsa otomatik)
    """
    if not topic.strip():
        return {"error": "Konu boş olamaz."}

    safe_name = re.sub(r'[^\w\s-]', '', topic[:40]).strip().replace(' ', '_')
    if not safe_name:
        safe_name = f"arastirma_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    def _run():
        from ..notifier import notify
        from .notebook_tools import (
            tool_notebook_create,
            tool_notebook_add_note,
            tool_notebook_complete_step,
        )
        from .registry import execute_tool
        from ..config import settings

        start_ts = time.time()

        # 1. Not defteri ac
        try:
            tool_notebook_create(
                name=safe_name,
                goal=topic,
                steps=(
                    "Konuya özgül sorgular belirle\n"
                    "Kaynakları tara ve topla\n"
                    "Kaynak içeriklerini oku ve not al\n"
                    "Bulguları sentezle\n"
                    "PDF rapor oluştur ve bildir"
                ),
            )
            notify(
                f"\U0001f4da <b>Araştırma başladı:</b> {topic[:80]}\n\n"
                f"Not defteri: <code>{safe_name}</code>\n"
                f"Bitince PDF raporu buraya göndereceğim. (~3-8 dk)"
            )
        except Exception as exc:
            import logging, traceback
            logging.getLogger(__name__).error(
                "[research_async] Baslatma hatasi: %s\n%s", exc, traceback.format_exc()
            )
            notify(f"⚠️ Araştırma başlatılamadı ({safe_name}): {exc}")
            return

        try:
            # 2. Konuya ozgu sorgular
            queries = _generate_smart_queries(topic)
            tool_notebook_add_note(name=safe_name, note=f"Alt sorgular: {queries}")
            try:
                tool_notebook_complete_step(
                    name=safe_name,
                    step_keyword="sorgu",
                    finding=f"{len(queries)} alt sorgu olusturuldu",
                )
            except Exception:
                pass

            # 3. Haber/web ara
            all_sources: list = []
            seen_source_keys: set = set()
            per_query_limit = max(8, min(int(max_sources or 24), 25))
            for q in queries:
                try:
                    res = execute_tool("search_news", {"query": q, "limit": per_query_limit})
                    items = res.get("results", []) or res.get("items", [])
                    feed_warnings = res.get("feed_warnings", []) or []
                    for fw in feed_warnings[:2]:
                        tool_notebook_add_note(name=safe_name, note=f"[UYARI] {fw[:180]}")
                    added_now = 0
                    for item in items:
                        raw_url = item.get("url", "") or item.get("link", "")
                        url = _decode_bing_click_url(str(raw_url))
                        title = str(item.get("title", "") or "").strip()
                        source = str(item.get("source", "") or "").strip()
                        source_url = str(item.get("source_url", "") or "").strip()
                        key = (url or title).strip().lower()
                        if not key or key in seen_source_keys:
                            continue
                        seen_source_keys.add(key)
                        all_sources.append(
                            {
                                "title": title,
                                "url": url,
                                "link": url,
                                "pub_date": str(item.get("pub_date", "") or "").strip(),
                                "source": source,
                                "source_url": source_url,
                                "summary": str(item.get("summary", "") or "").strip(),
                            }
                        )
                        added_now += 1
                    tool_notebook_add_note(name=safe_name, note=f"'{q}': {added_now} benzersiz kaynak")
                    if res.get("error"):
                        tool_notebook_add_note(name=safe_name, note=f"'{q}' search hatasi: {res['error']}")
                except Exception as exc2:
                    logging.getLogger(__name__).error("[research_async] search hatasi: %s\n%s", exc2, traceback.format_exc())
                    tool_notebook_add_note(name=safe_name, note=f"'{q}' hatasi: {_error_brief(exc2)}")

            tool_notebook_complete_step(
                name=safe_name, step_keyword="tara",
                finding=f"{len(all_sources)} toplam kaynak"
            )
            notify(
                f"\U0001f50d <b>{topic[:60]}</b>\n"
                f"{len(all_sources)} kaynak bulundu, içerikler okunuyor..."
            )

            # 4. Kaynak iceriklerini oku
            read_contents: list = []
            fetch_failures = 0
            high_signal_count = 0
            source_cap = max(12, min(int(max_sources or 24), 35))

            for idx, item in enumerate(all_sources[:source_cap], start=1):
                url = str(item.get("url", "") or item.get("link", "")).strip()
                title = str(item.get("title", "")).strip()
                source = str(item.get("source", "")).strip()
                source_url = str(item.get("source_url", "")).strip()
                summary = str(item.get("summary", "")).strip()
                pub_date = str(item.get("pub_date", "")).strip()

                content_parts: list[str] = []
                fetched_ok = False

                if url:
                    try:
                        page = execute_tool("fetch_web_page", {"url": url, "max_chars": 22000})
                        fetched = str(page.get("content", "") or page.get("text", "") or "").strip()
                        if fetched and not _is_low_signal_content(fetched):
                            content_parts.append(fetched[:3600])
                            fetched_ok = True
                        else:
                            fetch_failures += 1
                    except Exception as fetch_exc:
                        fetch_failures += 1
                        tool_notebook_add_note(
                            name=safe_name,
                            note=f"[FETCH HATA] {title[:70]} -> {_error_brief(fetch_exc)[:140]}",
                        )

                if not fetched_ok and source_url and source_url != url:
                    try:
                        page2 = execute_tool("fetch_web_page", {"url": source_url, "max_chars": 18000})
                        fetched2 = str(page2.get("content", "") or page2.get("text", "") or "").strip()
                        if fetched2 and not _is_low_signal_content(fetched2):
                            content_parts.append(fetched2[:2400])
                            fetched_ok = True
                    except Exception:
                        pass

                if summary and len(summary) >= 45:
                    content_parts.append(f"RSS Ozeti: {summary[:900]}")

                if not content_parts:
                    content_parts.append(
                        (
                            f"Baslik: {title or 'Bilinmiyor'}\n"
                            f"Yayin tarihi: {pub_date or 'Bilinmiyor'}\n"
                            f"Kaynak: {source or 'Bilinmiyor'}\n"
                            f"Ozet: {summary[:700] if summary else 'Bilinmiyor'}"
                        )
                    )
                else:
                    high_signal_count += 1 if fetched_ok else 0

                content = "\n\n".join(content_parts).strip()[:5200]
                if title or url:
                    read_contents.append(
                        {
                            "title": title or url,
                            "url": url,
                            "source": source,
                            "pub_date": pub_date,
                            "content": content,
                        }
                    )
                    tool_notebook_add_note(
                        name=safe_name,
                        note=(
                            f"[KAYNAK {idx}/{source_cap}] { (title or url)[:60] } | "
                            f"icerik={len(content)} karakter | kaynak={source[:40] or 'Bilinmiyor'}"
                        ),
                    )

                if time.time() - start_ts > 480:
                    tool_notebook_add_note(name=safe_name, note="[UYARI] 8dk siniri: icerik okuma durduruldu")
                    break

            tool_notebook_complete_step(
                name=safe_name, step_keyword="oku",
                finding=(
                    f"{len(read_contents)} kaynak islendi | "
                    f"zengin icerik: {high_signal_count} | fetch hata: {fetch_failures}"
                ),
            )

            # 4.5 Bulgulari Sentezle (LLM ile)
            synthesis_text = ""
            if read_contents:
                try:
                    import asyncio
                    from ..llm import LLMClient
                    
                    llm_client = LLMClient()
                    context_blocks = []
                    synthesis_source_cap = max(10, min(len(read_contents), 24))
                    for i, rc in enumerate(read_contents[:synthesis_source_cap], 1):
                        context_blocks.append(
                            "\n".join(
                                [
                                    f"[S{i}] Baslik: {rc.get('title')}",
                                    f"Kaynak: {rc.get('source', 'Bilinmiyor')}",
                                    f"Tarih: {rc.get('pub_date', 'Bilinmiyor')}",
                                    f"URL: {rc.get('url', '')}",
                                    "Icerik:",
                                    str(rc.get("content", ""))[:1600],
                                ]
                            )
                        )
                    
                    full_context = "\n\n".join(context_blocks)
                    
                    system_prompt = (
                        "Sen deneyimli bir jeopolitik ve finans arastirma analistisin. "
                        "Verilen kaynaklardan kapsamli bir rapor yaz. Cikti dili yalnizca Turkce olsun. "
                        "Kaynak yetersizse raporu reddetme; belirsizlikleri acikca not ederek yine sentez yap. "
                        "Kullanici tarih verdiyse (or. 5 Mart 2026), bu tarihi referans tarih kabul et; "
                        "salt tarih nedeniyle 'gelecek tarih' reddi uretme. "
                        "Sadece verilen kaynaklara dayan, spekulasyonu sinirla ve her ana bulguda [S1], [S2] gibi kaynak etiketi kullan. "
                        "Ingilizce yanit verme."
                    )
                    
                    messages = [
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": (
                                f"Arastirma Konusu: {topic}\n\n"
                                "Asagidaki formati uygula:\n"
                                "1) Yonetici Ozeti\n"
                                "2) Mevcut Durum (zaman cizelgesi)\n"
                                "3) Kuresel Finans Etkisi (enerji, altin, hisse, doviz, tahvil)\n"
                                "4) Senaryolar (kisa/orta vade)\n"
                                "5) Riskler ve Belirsizlikler\n"
                                "6) Sonuc\n\n"
                                f"Toplanan Kaynaklar:\n{full_context}"
                            ),
                        },
                    ]

                    llm_last_exc: Exception | None = None
                    for attempt in range(1, 4):
                        try:
                            llm_resp = asyncio.run(llm_client.chat(messages=messages, tools=[]))
                            candidate = _extract_llm_text(llm_resp)
                            if candidate:
                                synthesis_text = candidate
                            if len(candidate) >= 420:
                                break
                        except Exception as synth_exc:
                            llm_last_exc = synth_exc
                            time.sleep(1.2 * attempt)

                    if not synthesis_text.strip():
                        if llm_last_exc:
                            tool_notebook_add_note(
                                name=safe_name,
                                note=f"[UYARI] LLM sentez hatasi: {_error_brief(llm_last_exc)}",
                            )
                        synthesis_text = _build_fallback_synthesis(topic, read_contents)
                        tool_notebook_add_note(
                            name=safe_name,
                            note="[UYARI] LLM sentezi alinamadi; kaynaklardan fallback sentez uretildi.",
                        )
                    elif not _looks_like_turkish_text(synthesis_text):
                        translated_ok = False
                        try:
                            tr_messages = [
                                {
                                    "role": "system",
                                    "content": (
                                        "Asagidaki metni anlami koruyarak yalnizca Turkceye cevir. "
                                        "Yapisal basliklari ve maddelemeyi koru."
                                    ),
                                },
                                {"role": "user", "content": synthesis_text[:12000]},
                            ]
                            translated = _extract_llm_text(asyncio.run(llm_client.chat(messages=tr_messages, tools=[])))
                            if translated and len(translated) >= 240 and _looks_like_turkish_text(translated):
                                synthesis_text = translated
                                translated_ok = True
                                tool_notebook_add_note(
                                    name=safe_name,
                                    note="[BILGI] Sentez cikti dili Turkceye normalize edildi.",
                                )
                        except Exception as tr_exc:
                            tool_notebook_add_note(
                                name=safe_name,
                                note=f"[UYARI] Turkce normalize adimi atlandi: {_error_brief(tr_exc)}",
                            )
                        if not translated_ok:
                            synthesis_text = _build_fallback_synthesis(topic, read_contents)
                            tool_notebook_add_note(
                                name=safe_name,
                                note="[UYARI] Turkceye normalize basarisiz; Turkce fallback sentez uygulandi.",
                            )

                    tool_notebook_complete_step(
                        name=safe_name,
                        step_keyword="sentez",
                        finding=f"Sentez tamamlandi ({len(synthesis_text)} karakter)",
                    )

                except Exception as synth_exc:
                    err_trace = traceback.format_exc()
                    logging.getLogger(__name__).error("[research_async] Sentez hatasi: %s\n%s", synth_exc, err_trace)
                    try:
                        err_log_path = settings.data_path / "logs" / "research_async_errors.log"
                        err_log_path.parent.mkdir(parents=True, exist_ok=True)
                        with err_log_path.open("a", encoding="utf-8") as fh:
                            fh.write(
                                f"\n[{datetime.utcnow().isoformat()}Z] notebook={safe_name} stage=sentez error={_error_brief(synth_exc)}\n"
                            )
                            fh.write(err_trace + "\n")
                    except Exception:
                        pass
                    synthesis_text = _build_fallback_synthesis(topic, read_contents)
                    tool_notebook_add_note(
                        name=safe_name,
                        note=f"[UYARI] Sentez asamasinda hata: {_error_brief(synth_exc)}. Fallback sentez uygulandi.",
                    )
                    try:
                        tool_notebook_complete_step(
                            name=safe_name,
                            step_keyword="sentez",
                            finding=f"Fallback sentez uygulandi ({len(synthesis_text)} karakter)",
                        )
                    except Exception:
                        pass
            else:
                synthesis_text = _build_fallback_synthesis(topic, read_contents)
                tool_notebook_add_note(
                    name=safe_name,
                    note="[UYARI] Sentez adimi: kaynak icerigi bulunamadigi icin fallback rapor olusturuldu.",
                )
                try:
                    tool_notebook_complete_step(
                        name=safe_name,
                        step_keyword="sentez",
                        finding="Kaynak icerigi bulunamadigi icin fallback sentez uygulandi",
                    )
                except Exception:
                    pass

            # 5. PDF olustur
            elapsed = int(time.time() - start_ts)
            workspace = Path(settings.workspace_path)
            if out_path:
                report_path = workspace / out_path
                if report_path.suffix.lower() != ".pdf":
                    report_path = report_path.with_suffix(".pdf")
            else:
                reports_dir = workspace / "reports"
                reports_dir.mkdir(parents=True, exist_ok=True)
                report_path = reports_dir / f"{safe_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"

            summary_text = _write_pdf(
                report_path=report_path,
                topic=topic,
                read_contents=read_contents,
                all_sources=all_sources,
                elapsed=elapsed,
                report_style=report_style,
                synthesis_text=synthesis_text
            )

            tool_notebook_complete_step(
                name=safe_name, step_keyword="rapor",
                finding=f"PDF Rapor: {report_path}"
            )

            # 6. Telegram'a özet + PDF gönder
            notify(
                f"\u2705 <b>Araştırma tamamlandı!</b>\n\n{summary_text}",
                file_path=str(report_path),
            )

        except Exception as exc:
            import logging, traceback
            logging.getLogger(__name__).error(
                "[research_async] Hata: %s\n%s", exc, traceback.format_exc()
            )
            try:
                notify(f"❌ <b>Araştırma hatası ({safe_name}):</b>\n<code>{str(exc)[:300]}</code>")
            except Exception:
                pass

    threading.Thread(target=_run, daemon=True, name=f"research_{safe_name}").start()

    return {
        "success": True,
        "status": "started",
        "notebook": safe_name,
        "message": (
            f"Araştırma arka planda başlatıldı: {topic}\n"
            f"Bitince Telegram'a özet mesaj ve PDF rapor gönderilecek. (~4-12 dakika)"
        ),
    }
