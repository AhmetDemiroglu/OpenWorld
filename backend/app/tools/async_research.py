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
    # Uzun istekleri kisaltarak temiz arama motoru sorgulari uret
    stop_words = {"bir", "ve", "ile", "icin", "hakkinda", "konulu", "detayli", "arastirma", "rapor", "istiyorum", "yapmani", "hazirla", "bana", "gonder", "olusturmani", "yazacagin", "cevirecek", "buradan", "gondermeni", "lutfen", "bul", "getir", "nihai", "durumda", "pdf'e"}
    words = [w for w in topic.split() if w.lower() not in stop_words and len(w) > 2]
    core_topic = " ".join(words[:6]) if words else topic[:40]
    
    t = core_topic.lower()
    queries = [core_topic]

    if any(w in t for w in ['kod', 'code', 'yazilim', 'software', 'api', 'python',
                              'javascript', 'uygulama', 'app', 'gelistir', 'develop',
                              'mimari', 'architecture', 'framework', 'refactor']):
        queries += [f"{core_topic} best practices", f"{core_topic} mimari eksikler"]

    elif any(w in t for w in ['haber', 'gundem', 'son dakika', 'politik', 'ekonomi',
                                'piyasa', 'borsa', 'doviz', 'enflasyon', 'secim', 'savas']):
        queries += [f"{core_topic} son gelismeler", f"{core_topic} analiz yorum"]

    elif any(w in t for w in ['urun', 'marka', 'sirket', 'firma', 'company', 'brand', 'startup']):
        queries += [f"{core_topic} pazar analiz 2025", f"{core_topic} avantajlar karsilastirma"]

    else:
        queries += [f"{core_topic} nedir nasil calisir", f"{core_topic} guncel gelismeler 2025"]

    return list(dict.fromkeys(queries))[:4]


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
    max_sources: int = 10,
    out_path: str = "",
) -> Dict[str, Any]:
    """Araştırmayı ARKA PLANDA başlatır. Hemen 'Araştırma başladı' mesajı dön.
    Araştırma bitince Telegram'a özet mesaj + PDF rapor dosyası gönderilir.

    Args:
        topic: Araştırılacak konu (ne kadar detaylı, o kadar iyi)
        report_style: standard, technical, academic, brief
        max_sources: Kullanılacak max kaynak sayısı (varsayılan: 10)
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

            # 4.5 Bulgulari Sentezle (LLM ile)
            synthesis_text = ""
            if read_contents:
                try:
                    import asyncio
                    from ..llm import LLMClient
                    
                    llm_client = LLMClient()
                    context_blocks = []
                    # Sadece ilk 6 kaynagi gonder, context limitini ve sureyi asma
                    for i, rc in enumerate(read_contents[:6], 1):
                        context_blocks.append(f"Kaynak {i}:\nBaslik: {rc.get('title')}\nIcerik: {rc.get('content')[:800]}")
                    
                    full_context = "\n\n".join(context_blocks)
                    
                    system_prompt = (
                        "Sen profesyonel bir arastirmacisin. Asagidaki kaynaklari kullanarak verilen konu hakkinda "
                        "detayli, akici ve kapsamli bir rapor hazirla. Raporu markdown formati kullanarak basliklar (###), "
                        "maddelendirmeler ve paragraflar seklinde profesyonelce yapilandir. "
                        "Sadece kaynaklarda yer alan dogrulanmis bilgileri kullan. Eger kaynaklarda yeterli bilgi yoksa, elindeki bilgilerle sınırlı kal. Turkce yaz."
                    )
                    
                    messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Arastirma Konusu: {topic}\n\nToplanan Kaynaklar:\n{full_context}"}
                    ]
                    
                    # LLM cagirisi
                    llm_resp = asyncio.run(llm_client.chat(messages=messages, tools=[]))
                    synthesis_text = llm_resp.get("message", {}).get("content", "")
                    
                    tool_notebook_complete_step(
                        name=safe_name, step_keyword="sentez",
                        finding=f"Sentez tamamlandi ({len(synthesis_text)} karakter)"
                    )
                    
                except Exception as synth_exc:
                    import logging, traceback
                    err_trace = traceback.format_exc()
                    with open("C:\\Users\\Ahmet Demiro\u011flu\\Desktop\\OpenWorld\\backend\\synth_err.txt", "w", encoding="utf-8") as f:
                        f.write(err_trace)
                    logging.getLogger(__name__).error(f"[research_async] Sentez hatasi: {synth_exc}\n{err_trace}")
                    tool_notebook_add_note(name=safe_name, note=f"[UYARI] Sentez asamasinda hata: {synth_exc}")
                    synthesis_text = "Bulgular sentezlenirken bir hata olustu. Icerikler dogrudan dosyaya eklenemedi."

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
            f"Bitince Telegram'a özet mesaj ve PDF rapor gönderilecek. (~3-8 dakika)"
        ),
    }

