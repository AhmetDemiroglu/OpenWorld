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


def _extract_topic_keywords(topic: str) -> list[str]:
    """Konudan anlamli anahtar kelimeleri cikar (stop-word temizlemesi ile)."""
    stop_words = {
        # Turkce
        "bir", "ve", "ile", "icin", "ise", "olan", "ben", "sen", "biz", "siz",
        "hakkinda", "konulu", "konusu", "konusunda", "detayli", "arastirma", "rapor",
        "istiyorum", "yapmani", "hazirla", "bana", "gonder", "olusturmani", "yazacagin",
        "cevirecek", "buradan", "gondermeni", "lutfen", "bul", "getir", "nihai", "durumda",
        "pdfe", "pdf", "worde", "word", "olasi", "mevcut", "uzerine", "uzerinde",
        "kapsamli", "ilgili", "nasil", "tarih", "itibariyle", "konulu", "yapmayi",
        "itibari", "ihtimali", "onumuzdeki", "icerisinde", "arasinda",
        "yapilan", "yapman", "hazirla", "gonder", "olustur", "yaz",
        # Ingilizce
        "the", "and", "for", "with", "about", "from", "that", "this", "have", "will",
        "can", "how", "what", "which", "their", "there", "been", "would", "could",
    }
    raw_words = re.findall(r"[^\W_]+", topic, flags=re.UNICODE)
    keywords = [w for w in raw_words if len(w) > 2 and _normalize_ascii(w).lower() not in stop_words]
    return keywords


def _topic_has_keyword(topic_lower: str, keywords: list[str]) -> bool:
    """Kelime siniri kontrolu ile keyword varligini test eder (substring hatasi onlenir)."""
    for kw in keywords:
        # \b kullanarak tam kelime eslestirmesi
        if re.search(r'\b' + re.escape(kw) + r'\b', topic_lower):
            return True
    return False


def _generate_smart_queries(topic: str) -> list:
    """Konuya ozgu, KISA ve odakli alt sorgular uret.

    Kurallar:
    - Her sorgu max 6-8 kelime (Google News kisa sorgularda daha iyi calisir)
    - Turkce + Ingilizce varyantlar
    - Konu kategorisine gore ozel sorgular
    - Hardcoded alakasiz sorgular YASAK
    """
    keywords = _extract_topic_keywords(topic)
    # Cekirdek anahtar kelimeler (en onemli 6)
    core = keywords[:6]
    if not core:
        core = topic.split()[:4]

    # Kisa temel sorgu (max 6 kelime)
    base_tr = " ".join(core[:6]).strip()
    base_en = _normalize_ascii(base_tr)

    queries: list[str] = []

    # 1. Temel sorgular (kisa)
    if base_tr:
        queries.append(base_tr)
    if base_en and base_en != base_tr:
        queries.append(base_en)

    # 2. Daha da kisa versiyon (ilk 3 kelime)
    short_tr = " ".join(core[:3]).strip()
    short_en = _normalize_ascii(short_tr)
    if short_tr and short_tr != base_tr:
        queries.append(short_tr)
    if short_en and short_en != short_tr and short_en != base_en:
        queries.append(short_en)

    # 3. Konu kategorisine gore EK sorgular
    topic_lower = _normalize_ascii(topic).lower()
    topic_words = set(re.findall(r'\b\w{3,}\b', topic_lower))

    geopolitik_kw = {"iran", "israil", "israel", "abd", "savas", "war", "catisma", "conflict",
                     "nato", "ordu", "army", "military", "missile", "fuzesi"}
    finans_kw = {"finans", "piyasa", "borsa", "doviz", "emtia", "petrol", "altin", "ekonomi",
                 "market", "stock", "gold", "oil", "forex", "economy"}
    saglik_kw = {"kanser", "cancer", "tedavi", "treatment", "ilac", "drug", "saglik", "health",
                 "hastalik", "disease", "bilimsel", "scientific", "tibbi", "medical"}
    teknoloji_kw = {"yapay", "zeka", "llm", "ajanlar", "agents", "teknoloji", "technology",
                    "yazilim", "software", "bilgisayar", "computer", "robot", "otomasyon"}

    if topic_words & geopolitik_kw:
        queries.extend([
            f"{short_en} latest updates",
            f"{short_en} son gelismeler",
            f"{short_en} analysis",
        ])
    if topic_words & finans_kw:
        queries.extend([
            f"{short_en} market impact",
            f"{short_en} financial analysis",
            f"{short_en} piyasa etkisi",
        ])
    if topic_words & saglik_kw:
        queries.extend([
            f"{short_en} research breakthroughs",
            f"{short_en} bilimsel gelismeler",
            f"{short_en} clinical trials 2026",
        ])
    if topic_words & teknoloji_kw:
        queries.extend([
            f"{short_en} future predictions",
            f"{short_en} gelecek trendleri",
            f"{short_en} latest developments 2026",
        ])

    # Kategori eslesmedi ise genel sorgular
    all_category_kw = geopolitik_kw | finans_kw | saglik_kw | teknoloji_kw
    if not (topic_words & all_category_kw):
        queries.extend([
            f"{short_en} analysis",
            f"{short_en} latest news",
        ])

    # 4. Dedup ve sinirla
    dedup: list[str] = []
    seen: set[str] = set()
    for q in queries:
        cleaned = re.sub(r"\s+", " ", q).strip()
        key = cleaned.lower()
        if not cleaned or key in seen or len(cleaned) < 4:
            continue
        seen.add(key)
        dedup.append(cleaned)
    return dedup[:10]


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


def _build_fallback_synthesis(topic: str, read_contents: list[dict], max_items: int = 15) -> str:
    """LLM sentezi başarısız olduğunda kaynak başlık + temiz özet bazlı rapor üret.

    Ham HTML/JS icerigini KESINLIKLE dahil etmez — sadece anlamli cumleler secilir.
    """
    lines: list[str] = [
        "## Yönetici Özeti",
        f"Bu rapor '{topic}' konusu için toplanan kaynaklardan derlendi.",
        "",
        "## Bulunan Kaynaklar ve Özetleri",
    ]
    used = 0
    for idx, rc in enumerate(read_contents[:max_items], start=1):
        title = str(rc.get("title", "")).strip() or f"Kaynak {idx}"
        source = str(rc.get("source", "")).strip() or "Bilinmiyor"
        pub_date = str(rc.get("pub_date", "")).strip() or "Bilinmiyor"
        content = str(rc.get("content", "")).strip()

        # Icerigi tekrar temizle (fallback icin ekstra guvenlik)
        content = _clean_web_content(content)

        # Anlamli cumleleri sec (noktalama ile biten, yeterince uzun, alfabe orani yuksek)
        sentences = re.split(r'(?<=[.!?])\s+', content[:2000])
        good_sentences: list[str] = []
        for s in sentences:
            s = s.strip()
            if len(s) < 40:
                continue
            alpha_ratio = sum(1 for c in s if c.isalpha()) / max(len(s), 1)
            if alpha_ratio < 0.5:
                continue
            # JS/CSS artigi iceren cumleleri at
            if any(junk in s.lower() for junk in ("function(", "var ", "const ", "document.", "window.",
                                                     "observer", "innerhtml", ".classname", "appendchild")):
                continue
            good_sentences.append(s)
            if len(good_sentences) >= 3:
                break

        summary = " ".join(good_sentences) if good_sentences else ""

        # Ozet hala bossa sadece basligi yaz
        if not summary or len(summary) < 30:
            lines.append(f"\n### [K{idx}] {title}")
            lines.append(f"*Kaynak: {source} | Tarih: {pub_date}*")
        else:
            lines.append(f"\n### [K{idx}] {title}")
            lines.append(f"*Kaynak: {source} | Tarih: {pub_date}*")
            lines.append(summary)
        used += 1

    if used == 0:
        lines.append("Kullanılabilir kaynak içeriği bulunamadı.")

    lines.extend([
        "",
        "## Değerlendirme",
        "- Bu rapor otomatik kaynak taramasına dayanmaktadır.",
        "- Kritik kararlar için birincil kaynaklardan doğrulama önerilir.",
    ])
    return "\n".join(lines).strip()


def _error_brief(exc: Exception) -> str:
    text = str(exc or "").strip()
    if text:
        return text
    name = type(exc).__name__
    return name or "UnknownError"


def _clean_web_content(text: str) -> str:
    """Web sayfasından çekilen içerikten JS/CSS artıklarını, navigasyon çöplerini temizle."""
    if not text:
        return ""
    # HTML tag artiklari (kalanlar)
    text = re.sub(r'<[^>]{0,500}>', ' ', text)
    # JS obje literalleri: { key: value, ... }
    text = re.sub(r'\{[^{}]{0,600}\}', ' ', text)
    # Kalan süslü parantezler
    text = re.sub(r'[{}]', ' ', text)
    # JS fonksiyon / method kaliplari
    text = re.sub(
        r'\b(?:addEventListener|querySelector|getAttribute|setAttribute|'
        r'attributeFilter|MutationObserver|ResizeObserver|IntersectionObserver|'
        r'document\.\w+|window\.\w+|console\.\w+|function\s*\(|var\s+\w+\s*=|'
        r'let\s+\w+\s*=|const\s+\w+\s*=|return\s+\w+|typeof\s+\w+|'
        r'observer\.observe|\.innerHTML|\.textContent|\.className|'
        r'\.parentNode|\.childNodes|\.appendChild)\b[^.;]{0,200}[;)]?', ' ', text)
    # data-* attribute kalıpları
    text = re.sub(r'data-[\w-]+=[\"\'][^\"\']{0,200}[\"\']', ' ', text)
    # Inline CSS / style / attribute artıkları
    text = re.sub(r'(?:style|class|href|src|onclick|onload|onerror|aria-\w+)\s*=\s*["\'][^"\']{0,300}["\']', ' ', text)
    # CSS seçicileri ve kuralları
    text = re.sub(r'[.#][\w-]+\s*\{[^}]{0,500}\}', ' ', text)
    text = re.sub(r'@media[^{]*\{[^}]{0,1000}\}', ' ', text)
    # URL'ler (cok uzun olanlar kesinlikle nav/resource link)
    text = re.sub(r'https?://\S{60,}', ' ', text)
    # Parantez icinde JS argumanlari: (document.documentElement, )
    text = re.sub(r'\([^)]{0,300}(?:document|window|Element|Node|observer)[^)]{0,300}\)', ' ', text)
    # "DİĞER Röportaj Teknoloji Kültür-Sanat" tipi nav menu satirlari
    # Ardisik kisa kelimelerin (2-15 karakter) 5+ tekrari = menu
    text = re.sub(r'(?:\b\w{2,15}\b\s+){5,}(?=\b\w{2,15}\b\s*$)', ' ', text, flags=re.MULTILINE)
    # Cookie/consent banner metinleri
    text = re.sub(r'(?i)(?:cookie|consent|privacy policy|terms of use|accept all|reject all)[^.]{0,200}\.?', ' ', text)
    # Çok kısa satırları (menü öğeleri, nav linkler) filtrele
    lines = text.split('\n')
    good_lines = []
    for ln in lines:
        ln = ln.strip()
        if len(ln) < 25:
            continue
        # Cok fazla ozel karakter iceren satirlari at (JS/CSS artigi)
        alpha_ratio = sum(1 for c in ln if c.isalpha()) / max(len(ln), 1)
        if alpha_ratio < 0.4:
            continue
        good_lines.append(ln)
    text = ' '.join(good_lines)
    # Tekrar eden boşluklar
    text = re.sub(r'\s{2,}', ' ', text).strip()
    return text


def _source_is_relevant(title: str, content: str, topic_keywords: list[str]) -> bool:
    """Kaynağın araştırma konusuyla alakalı olup olmadığını kontrol eder.

    En az 1 anahtar kelimenin başlık veya içerikte geçmesi yeterli.
    Cok katı olmamak lazım - ama tamamen alakasız kaynakları elemeli.
    """
    if not topic_keywords:
        return True  # Keyword yoksa filtreleme yapma
    combined = (title + " " + content[:500]).lower()
    combined_ascii = _normalize_ascii(combined)
    matches = 0
    for kw in topic_keywords:
        kw_lower = kw.lower()
        kw_ascii = _normalize_ascii(kw_lower)
        if kw_lower in combined or kw_ascii in combined_ascii:
            matches += 1
    # En az 1 keyword eslesmesi gerekli
    return matches >= 1


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
            topic_keywords = _extract_topic_keywords(topic)[:8]
            queries = _generate_smart_queries(topic)
            tool_notebook_add_note(name=safe_name, note=f"Alt sorgular: {queries}")
            tool_notebook_add_note(name=safe_name, note=f"Konu anahtar kelimeleri: {topic_keywords[:6]}")
            try:
                tool_notebook_complete_step(
                    name=safe_name,
                    step_keyword="sorgu",
                    finding=f"{len(queries)} alt sorgu olusturuldu",
                )
            except Exception:
                pass

            # 3. Haber/web ara — geniş kaynak yelpazesi
            all_sources: list = []
            seen_source_keys: set = set()
            per_query_limit = 30  # Google News RSS zaten 20-30 sonuç döndürür, yapay kısıt yok

            def _add_sources_from_items(items: list, label: str) -> int:
                added = 0
                skipped_irrelevant = 0
                for item in items:
                    raw_url = item.get("url", "") or item.get("link", "")
                    url = _decode_bing_click_url(str(raw_url))
                    title = str(item.get("title", "") or "").strip()
                    source = str(item.get("source", "") or "").strip()
                    source_url = str(item.get("source_url", "") or "").strip()
                    summary = str(item.get("summary", "") or "").strip()
                    key = (url or title).strip().lower()
                    if not key or key in seen_source_keys:
                        continue
                    # Konu ilgililik filtresi
                    if not _source_is_relevant(title, summary, topic_keywords):
                        skipped_irrelevant += 1
                        continue
                    seen_source_keys.add(key)
                    all_sources.append({
                        "title": title,
                        "url": url,
                        "link": url,
                        "pub_date": str(item.get("pub_date", "") or "").strip(),
                        "source": source or label,
                        "source_url": source_url,
                        "summary": summary,
                    })
                    added += 1
                if skipped_irrelevant:
                    tool_notebook_add_note(
                        name=safe_name,
                        note=f"[FİLTRE] {skipped_irrelevant} alakasız kaynak elendi",
                    )
                return added

            # 3a. Google News RSS (Türkçe + İngilizce sorgular)
            for q in queries:
                try:
                    res = execute_tool("search_news", {"query": q, "limit": per_query_limit})
                    items = res.get("results", []) or res.get("items", [])
                    feed_warnings = res.get("feed_warnings", []) or []
                    for fw in feed_warnings[:2]:
                        tool_notebook_add_note(name=safe_name, note=f"[UYARI] {fw[:180]}")
                    added_now = _add_sources_from_items(items, "Google News")
                    tool_notebook_add_note(name=safe_name, note=f"[HABER] '{q}': {added_now} kaynak eklendi")
                    if res.get("error"):
                        tool_notebook_add_note(name=safe_name, note=f"'{q}' arama hatası: {res['error']}")
                except Exception as exc2:
                    logging.getLogger(__name__).error("[research_async] search hatasi: %s\n%s", exc2, traceback.format_exc())
                    tool_notebook_add_note(name=safe_name, note=f"'{q}' hatası: {_error_brief(exc2)}")

            # 3b. Wikipedia — konuya ait genel bilgi çek (kelime siniri kontrolu ile)
            _lower_topic = _normalize_ascii(topic).lower()
            wiki_subjects: list[str] = []
            if _topic_has_keyword(_lower_topic, ["iran", "israil", "israel"]):
                wiki_subjects += ["Iran–Israel conflict", "Israel–Hamas war", "Iran nuclear program"]
            if _topic_has_keyword(_lower_topic, ["finans", "piyasa", "petrol", "enerji", "ekonomi"]):
                wiki_subjects += ["Oil price", "Geopolitical risk premium", "Commodity market"]
            if _topic_has_keyword(_lower_topic, ["abd", "nato", "america"]):
                wiki_subjects += ["United States foreign policy in the Middle East"]
            if _topic_has_keyword(_lower_topic, ["kanser", "cancer", "tedavi", "treatment"]):
                wiki_subjects += ["Cancer research", "Immunotherapy", "Cancer treatment"]
            if _topic_has_keyword(_lower_topic, ["yapay", "zeka", "llm", "agents", "ajanlar"]):
                wiki_subjects += ["Artificial intelligence", "Large language model", "AI agent"]
            for subj in wiki_subjects:
                try:
                    wiki_url = f"https://en.wikipedia.org/wiki/{subj.replace(' ', '_')}"
                    page = execute_tool("fetch_web_page", {"url": wiki_url, "max_chars": 18000})
                    raw = str(page.get("content", "") or "").strip()
                    cleaned = _clean_web_content(raw)
                    if cleaned and len(cleaned) > 300:
                        all_sources.append({
                            "title": f"Wikipedia: {subj}",
                            "url": wiki_url,
                            "link": wiki_url,
                            "pub_date": "",
                            "source": "Wikipedia",
                            "source_url": wiki_url,
                            "summary": cleaned[:600],
                        })
                        tool_notebook_add_note(name=safe_name, note=f"[WİKİ] '{subj}': {len(cleaned)} karakter çekildi")
                except Exception as wiki_exc:
                    tool_notebook_add_note(name=safe_name, note=f"[WİKİ HATA] {subj}: {_error_brief(wiki_exc)[:100]}")

            # 3c. Finansal konular için özel kaynaklar doğrudan çek
            if _topic_has_keyword(_lower_topic, ["finans", "piyasa", "petrol", "altin", "doviz", "emtia", "borsa"]):
                financial_urls = [
                    ("Reuters Markets", "https://www.reuters.com/markets/"),
                    ("Bloomberg Middle East", "https://www.bloomberg.com/middle-east"),
                ]
                for label, furl in financial_urls:
                    try:
                        page = execute_tool("fetch_web_page", {"url": furl, "max_chars": 15000})
                        raw = str(page.get("content", "") or "").strip()
                        cleaned = _clean_web_content(raw)
                        if cleaned and not _is_low_signal_content(cleaned):
                            key = furl.lower()
                            if key not in seen_source_keys:
                                seen_source_keys.add(key)
                                all_sources.append({
                                    "title": f"{label} (güncel)",
                                    "url": furl,
                                    "link": furl,
                                    "pub_date": datetime.utcnow().strftime("%Y-%m-%d"),
                                    "source": label,
                                    "source_url": furl,
                                    "summary": cleaned[:800],
                                })
                                tool_notebook_add_note(name=safe_name, note=f"[FİNANS] {label}: {len(cleaned)} karakter çekildi")
                    except Exception as fin_exc:
                        tool_notebook_add_note(name=safe_name, note=f"[FİNANS HATA] {label}: {_error_brief(fin_exc)[:100]}")

            tool_notebook_complete_step(
                name=safe_name, step_keyword="tara",
                finding=f"{len(all_sources)} toplam kaynak (haber + wiki + finansal)"
            )
            notify(
                f"\U0001f50d <b>{topic[:60]}</b>\n"
                f"{len(all_sources)} kaynak bulundu (haber, Wikipedia, finansal). İçerikler okunuyor..."
            )

            # 4. Kaynak iceriklerini oku
            read_contents: list = []
            fetch_failures = 0
            high_signal_count = 0
            # 80 kaynak: kapsamlı ama makul (100 kaynak × ~10s fetch = saatler sürer)
            # Zaman limiti zaten 30 dk'da keser; bu ek bir güvence
            source_cap = min(len(all_sources), 80)

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
                        page = execute_tool("fetch_web_page", {"url": url, "max_chars": 28000})
                        raw = str(page.get("content", "") or page.get("text", "") or "").strip()
                        fetched = _clean_web_content(raw)
                        if fetched and not _is_low_signal_content(fetched):
                            content_parts.append(fetched[:6000])
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
                        page2 = execute_tool("fetch_web_page", {"url": source_url, "max_chars": 20000})
                        raw2 = str(page2.get("content", "") or page2.get("text", "") or "").strip()
                        fetched2 = _clean_web_content(raw2)
                        if fetched2 and not _is_low_signal_content(fetched2):
                            content_parts.append(fetched2[:4000])
                            fetched_ok = True
                    except Exception:
                        pass

                if summary and len(summary) >= 45:
                    content_parts.append(f"RSS Özeti: {_clean_web_content(summary)[:1200]}")

                if not content_parts:
                    content_parts.append(
                        (
                            f"Başlık: {title or 'Bilinmiyor'}\n"
                            f"Yayın tarihi: {pub_date or 'Bilinmiyor'}\n"
                            f"Kaynak: {source or 'Bilinmiyor'}\n"
                            f"Özet: {summary[:700] if summary else 'Bilgi yok'}"
                        )
                    )
                else:
                    high_signal_count += 1 if fetched_ok else 0

                content = "\n\n".join(content_parts).strip()[:7000]
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
                            f"[KAYNAK {idx}/{source_cap}] {(title or url)[:60]} | "
                            f"içerik={len(content)} karakter | kaynak={source[:40] or 'Bilinmiyor'}"
                        ),
                    )

                if time.time() - start_ts > 1800:
                    tool_notebook_add_note(name=safe_name, note="[UYARI] 30 dk sınırı: içerik okuma durduruldu, senteze geçiliyor")
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

                    # Thread-safe event loop olustur (asyncio.run() thread icinde sorunlu)
                    _synth_loop = asyncio.new_event_loop()

                    def _llm_call_safe(msgs: list, timeout_sec: float = 300.0) -> str:
                        """Thread-safe LLM cagrisi, timeout koruması ile."""
                        async def _do():
                            client = LLMClient()
                            return await asyncio.wait_for(
                                client.chat(messages=msgs, tools=[]),
                                timeout=timeout_sec,
                            )
                        for attempt in range(1, 3):  # max 2 deneme (eskiden 3'tu)
                            try:
                                resp = _synth_loop.run_until_complete(_do())
                                return _extract_llm_text(resp)
                            except asyncio.TimeoutError:
                                tool_notebook_add_note(
                                    name=safe_name,
                                    note=f"[UYARI] LLM {timeout_sec}sn timeout (deneme {attempt})",
                                )
                                time.sleep(2.0)
                            except Exception as _exc:
                                tool_notebook_add_note(
                                    name=safe_name,
                                    note=f"[UYARI] LLM hata (deneme {attempt}): {_error_brief(_exc)[:100]}",
                                )
                                time.sleep(2.0 * attempt)
                        return ""

                    # ── Batch sentez ────────────────────────────────────────────────────────
                    BATCH_SIZE = 10  # Kucuk batch = LLM daha hizli ve basarili cevap verir

                    _synthesis_system = (
                        "Sen Türkçe yazan üst düzey bir araştırma analistisin. "
                        "Görevin: sana verilen ham kaynak metinlerini okuyarak bütünleşik, analitik bir metin üretmek.\n\n"
                        "KESİN KURALLAR:\n"
                        "1. Yanıt dili TAMAMEN TÜRKÇE. İngilizce cümle veya paragraf YASAK.\n"
                        "2. Türkçe karakterleri (ğ, ş, ı, ö, ü, ç, İ, Ğ, Ş, Ö, Ü, Ç) doğru kullan.\n"
                        "3. Her kaynağı AYRI AYRI özetleme — sentez yap.\n"
                        "4. Bulguları [K1], [K2] gibi kaynak etiketiyle destekle.\n"
                        "5. HTML artığı, JS kodu, navigasyon metni gibi anlamsız içerikleri YOK SAY.\n"
                        "6. Verilen tarihi referans al; 'gelecek tarih' diye reddetme.\n"
                        "7. Spekülasyonu 'öngörü' veya 'olası' şeklinde işaretle."
                    )

                    def _build_source_block(rc: dict, idx: int) -> str:
                        content = str(rc.get("content", ""))[:1800]  # 2200 -> 1800 (LLM context icin)
                        return "\n".join([
                            f"[K{idx}] Başlık: {rc.get('title', '')}",
                            f"Kaynak: {rc.get('source', 'Bilinmiyor')} | Tarih: {rc.get('pub_date', 'Bilinmiyor')}",
                            "--- İçerik ---",
                            content,
                        ])

                    # Tüm kaynaklar için blok oluştur
                    all_blocks = [_build_source_block(rc, i) for i, rc in enumerate(read_contents, 1)]
                    total_sources = len(all_blocks)

                    if total_sources <= BATCH_SIZE:
                        full_context = "\n\n".join(all_blocks)
                        batch_summaries = [full_context]
                        tool_notebook_add_note(name=safe_name, note=f"[SENTEZ] {total_sources} kaynak — tek geçiş")
                    else:
                        batch_summaries = []
                        batches = [all_blocks[i:i+BATCH_SIZE] for i in range(0, total_sources, BATCH_SIZE)]
                        tool_notebook_add_note(name=safe_name, note=f"[SENTEZ] {total_sources} kaynak → {len(batches)} batch")
                        for b_idx, batch in enumerate(batches, 1):
                            batch_ctx = "\n\n".join(batch)
                            b_msgs = [
                                {"role": "system", "content": _synthesis_system},
                                {"role": "user", "content": (
                                    f"ARAŞTIRMA KONUSU: {topic}\n\n"
                                    f"Aşağıdaki {len(batch)} kaynaktan en önemli bulguları çıkar. "
                                    "Konuyla ilgisiz içerikleri atla. "
                                    "Bulgular arası bağlantı kur, sentez yap. Türkçe yaz.\n\n"
                                    f"KAYNAKLAR (Batch {b_idx}/{len(batches)}):\n{batch_ctx}"
                                )},
                            ]
                            b_summary = _llm_call_safe(b_msgs, timeout_sec=300.0)
                            if b_summary:
                                batch_summaries.append(f"[Batch {b_idx} özeti]\n{b_summary}")
                                tool_notebook_add_note(name=safe_name, note=f"[SENTEZ] Batch {b_idx}/{len(batches)} tamamlandı ({len(b_summary)} karakter)")
                            else:
                                tool_notebook_add_note(name=safe_name, note=f"[UYARI] Batch {b_idx}/{len(batches)} boş döndü")

                    # Final rapor
                    final_context = "\n\n".join(batch_summaries)
                    # Context cok buyukse kirp (yerel LLM icin)
                    if len(final_context) > 12000:
                        final_context = final_context[:12000] + "\n\n[... bazi icerikler uzunluk nedeniyle kirpildi ...]"

                    final_msgs = [
                        {"role": "system", "content": _synthesis_system},
                        {"role": "user", "content": (
                            f"ARAŞTIRMA KONUSU: {topic}\n\n"
                            "Aşağıdaki araştırma bulgularından kapsamlı bir rapor yaz. "
                            "Her bölüm en az 2-3 paragraf içermeli. Yüzeysel değil, derin analiz yap.\n\n"
                            "RAPOR YAPISI:\n"
                            "## 1. Yönetici Özeti\n"
                            "## 2. Mevcut Durum ve Arka Plan\n"
                            "## 3. Detaylı Analiz\n"
                            "## 4. Senaryolar ve Öngörüler\n"
                            "## 5. Riskler ve Belirsizlikler\n"
                            "## 6. Sonuç ve Değerlendirme\n\n"
                            f"BULGULAR:\n{final_context}"
                        )},
                    ]

                    synthesis_text = _llm_call_safe(final_msgs, timeout_sec=420.0)

                    # Event loop kapat
                    try:
                        _synth_loop.close()
                    except Exception:
                        pass

                    if not synthesis_text.strip():
                        synthesis_text = _build_fallback_synthesis(topic, read_contents)
                        tool_notebook_add_note(
                            name=safe_name,
                            note="[UYARI] LLM sentezi alınamadı; kaynaklardan fallback sentez üretildi.",
                        )
                    elif not _looks_like_turkish_text(synthesis_text):
                        # Turkceye cevir denemesi
                        tr_messages = [
                            {
                                "role": "system",
                                "content": (
                                    "Aşağıdaki metni anlam ve yapı bozulmadan yalnızca Türkçeye çevir. "
                                    "Başlıkları ve madde listelerini koru."
                                ),
                            },
                            {"role": "user", "content": synthesis_text[:10000]},
                        ]
                        _tr_loop = asyncio.new_event_loop()
                        try:
                            async def _tr_call():
                                client = LLMClient()
                                return await asyncio.wait_for(
                                    client.chat(messages=tr_messages, tools=[]),
                                    timeout=300.0,
                                )
                            translated = _extract_llm_text(_tr_loop.run_until_complete(_tr_call()))
                            if translated and len(translated) >= 400 and _looks_like_turkish_text(translated):
                                synthesis_text = translated
                                tool_notebook_add_note(name=safe_name, note="[BİLGİ] Sentez Türkçeye normalize edildi.")
                            else:
                                synthesis_text = _build_fallback_synthesis(topic, read_contents)
                                tool_notebook_add_note(name=safe_name, note="[UYARI] Türkçe normalize başarısız; fallback uygulandı.")
                        except Exception as tr_exc:
                            tool_notebook_add_note(name=safe_name, note=f"[UYARI] Türkçe normalize atlandı: {_error_brief(tr_exc)[:80]}")
                        finally:
                            try:
                                _tr_loop.close()
                            except Exception:
                                pass

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
                        note=f"[UYARI] Sentez hatası: {_error_brief(synth_exc)[:100]}. Fallback uygulandı.",
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
                    note="[UYARI] Kaynak icerigi bulunamadi; fallback rapor olusturuldu.",
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
