"""
async_research.py â€” Otonom arka plan arastirma araci.
tool_research_async: Aninda yanitlar, arka planda arastirip Telegram'a bildirir.
Cikti: PDF rapor (reportlab ile) + Telegram ozet mesaji.
"""
from __future__ import annotations

import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


# â”€â”€ Yardimci: konuya ozgu sorgular â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _generate_smart_queries(topic: str) -> list:
    """Konuya OZGU alt sorgular uretir â€” sabit sablon degil."""
    t = topic.lower()
    queries = [topic]

    if any(w in t for w in ['kod', 'code', 'yazilim', 'software', 'api', 'python',
                              'javascript', 'uygulama', 'app', 'gelistir', 'develop',
                              'mimari', 'architecture', 'framework', 'refactor']):
        queries += [f"{topic} best practices 2025", f"{topic} mimari onerileri eksikler guclu yanlar"]

    elif any(w in t for w in ['haber', 'gundem', 'son dakika', 'politik', 'ekonomi',
                                'piyasa', 'borsa', 'doviz', 'enflasyon', 'secim', 'savas']):
        queries += [f"{topic} son gelismeler analiz", f"{topic} uzman yorumu neden etki"]

    elif any(w in t for w in ['urun', 'marka', 'sirket', 'firma', 'company', 'brand', 'startup']):
        queries += [f"{topic} pazar analiz 2025", f"{topic} avantajlar eksikler karsilastirma"]

    else:
        queries += [f"{topic} nedir nasil calisir avantaj dezavantaj", f"{topic} guncel gelismeler 2025"]

    return list(dict.fromkeys(queries))[:5]


# â”€â”€ PDF olusturucu â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _write_pdf(report_path: Path, topic: str, read_contents: list, all_sources: list,
               elapsed: int, report_style: str) -> str:
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
    story.append(Paragraph(f"Arastirma Raporu", h1))
    story.append(Paragraph(topic, h2))
    story.append(Paragraph(
        f"Tarih: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC Â |Â  "
        f"Stil: {report_style} Â |Â  Kaynak: {len(read_contents)} Â |Â  Sure: {elapsed}s",
        meta,
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e0e0e0"), spaceAfter=12))

    if not read_contents:
        story.append(Paragraph("Okunabilir kaynak bulunamadi. Haber basliklari:", h2))
        for item in all_sources[:8]:
            title = (item.get("title") or "")[:120]
            summary = (item.get("summary") or "")[:200]
            story.append(Paragraph(f"<b>{title}</b>", body))
            if summary:
                story.append(Paragraph(summary, body))
            story.append(Spacer(1, 4))
    else:
        story.append(Paragraph("Kaynaklar ve Bulgular", h2))
        for i, rc in enumerate(read_contents, 1):
            title = (rc.get("title") or f"Kaynak {i}")[:120]
            url = (rc.get("url") or "")[:200]
            content = (rc.get("content") or "")[:800]

            story.append(Paragraph(f"{i}. {title}", h2))
            if url:
                story.append(Paragraph(url, url_style))
            story.append(Paragraph(content.replace("<", "&lt;").replace(">", "&gt;"), body))
            story.append(HRFlowable(width="80%", thickness=0.5, color=colors.lightgrey, spaceAfter=8))

    doc = SimpleDocTemplate(
        str(report_path),
        pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )
    doc.build(story)

    # Ozet metni (Telegram mesaji icin)
    titles = [rc.get("title", "")[:60] for rc in read_contents[:4]]
    titles_text = "\n".join(f"  - {t}" for t in titles) if titles else "  (kaynak bulunamadi)"
    summary_text = (
        f"<b>Arastirma Ozeti</b>\n\n"
        f"<b>Konu:</b> {topic[:100]}\n"
        f"<b>Kaynak sayisi:</b> {len(read_contents)}\n"
        f"<b>Sure:</b> {elapsed} saniye\n\n"
        f"<b>One cikan kaynaklar:</b>\n{titles_text}\n\n"
        f"Detayli rapor asagidaki PDF dosyasinda."
    )
    return summary_text


# â”€â”€ Ana tool â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def tool_research_async(
    topic: str,
    report_style: str = "standard",
    max_sources: int = 10,
    out_path: str = "",
) -> Dict[str, Any]:
    """Arastirmayi ARKA PLANDA baslatir. Hemen 'Arastirma basladi' mesaji don.
    Arastirma bitince Telegram'a ozet mesaj + PDF rapor dosyasi gonderilir.

    Args:
        topic: Arastirilacak konu (ne kadar detayli, o kadar iyi)
        report_style: standard, technical, academic, brief
        max_sources: Kullanilacak max kaynak sayisi (varsayilan: 10)
        out_path: Cikti PDF dosyasi yolu (opsiyonel, bos birakilirsa otomatik)
    """
    if not topic.strip():
        return {"error": "Konu bos olamaz."}

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
                    "Konuya ozgu sorgular belirle\n"
                    "Kaynaklari tara ve topla\n"
                    "Kaynak iceriklerini oku ve not al\n"
                    "Bulgulari sentezle\n"
                    "PDF rapor olustur ve bildir"
                ),
            )
            notify(
                f"\U0001f4da <b>Arastirma basladi:</b> {topic[:80]}\n\n"
                f"Not defteri: <code>{safe_name}</code>\n"
                f"Bitince PDF raporu buraya gonderecegim. (~3-8 dk)"
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

            # 3. Haber/web ara
            all_sources: list = []
            for q in queries:
                try:
                    res = execute_tool("search_news", {"query": q, "limit": 8})
                    items = res.get("results", []) or res.get("items", [])
                    all_sources.extend(items)
                    tool_notebook_add_note(name=safe_name, note=f"'{q}': {len(items)} kaynak")
                    if res.get("error"):
                        tool_notebook_add_note(name=safe_name, note=f"'{q}' search hatasi: {res['error']}")
                except Exception as exc2:
                    import logging as _log, traceback as _tb
                    _log.getLogger(__name__).error("[research_async] search hatasi: %s\n%s", exc2, _tb.format_exc())
                    tool_notebook_add_note(name=safe_name, note=f"'{q}' hatasi: {exc2}")

            tool_notebook_complete_step(
                name=safe_name, step_keyword="tara",
                finding=f"{len(all_sources)} toplam kaynak"
            )
            notify(
                f"\U0001f50d <b>{topic[:60]}</b>\n"
                f"{len(all_sources)} kaynak bulundu, içerikler okunuyor..."
            )

            # 4. Kaynak iceriklerini oku
            # NOT: RSS items "link" key kullanir, "url" degil!
            read_contents: list = []
            seen: set = set()
            for item in all_sources[:max_sources]:
                url = item.get("url", "") or item.get("link", "")  # RSS: "link"
                title = item.get("title", "")

                if url and url in seen:
                    continue
                if url:
                    seen.add(url)

                # Web sayfasini cekmeden once RSS bilgilerini kullan
                content = ""
                try:
                    if url:
                        page = execute_tool("fetch_web_page", {"url": url})
                        fetched = (page.get("content", "") or page.get("text", ""))
                        if len(fetched) > 100:
                            content = fetched[:1500]
                except Exception:
                    pass  # Sayfa cekilemediyse RSS basligini kullanacagiz

                # Fallback: en azindan baslik + tarih + kaynak bilgisi
                if not content:
                    content = (
                        f"Başlık: {title}\n"
                        f"Yayın tarihi: {item.get('pub_date', 'Bilinmiyor')}\n"
                        f"Ozet: {item.get('summary', 'Bilinmiyor')[:500]}\n"
                        f"Kaynak: {item.get('source', 'Bilinmiyor')}"
                    )

                if title or url:
                    read_contents.append({
                        "title": title or url,
                        "url": url,
                        "content": content,
                    })
                    tool_notebook_add_note(
                        name=safe_name,
                        note=f"[KAYNAK] {title[:50]}: {content[:200]}"
                    )

                if time.time() - start_ts > 240:
                    tool_notebook_add_note(name=safe_name, note="[UYARI] 4dk siniri: icerik okuma durduruldu")
                    break

            tool_notebook_complete_step(
                name=safe_name, step_keyword="oku",
                finding=f"{len(read_contents)} kaynak islendi"
            )

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
            )

            tool_notebook_complete_step(
                name=safe_name, step_keyword="rapor",
                finding=f"PDF Rapor: {report_path}"
            )

            # 6. Telegram'a ozet + PDF gonder
            notify(
                f"\u2705 <b>Arastirma tamamlandi!</b>\n\n{summary_text}",
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
            f"Arastirma arka planda baslatildi: {topic}\n"
            f"Bitince Telegram'a ozet mesaj ve PDF rapor gonderilecek. (~3-8 dakika)"
        ),
    }

