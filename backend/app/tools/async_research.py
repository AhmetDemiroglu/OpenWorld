"""
async_research.py — Otonom arka plan arastirma araci.
tool_research_async: Aninda yanitlar, arka planda arastirip Telegram'a bildirir.
"""
from __future__ import annotations

import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


def _generate_smart_queries(topic: str) -> list:
    """Konuya OZGU alt sorgular uretir -- sabit sablon degil, konuya gore boyut ekler."""
    t = topic.lower()
    queries = [topic]

    if any(w in t for w in ['kod', 'code', 'yazilim', 'software', 'api', 'python',
                              'javascript', 'uygulama', 'app', 'gelistir', 'develop',
                              'mimari', 'architecture', 'framework']):
        queries += [f"{topic} best practices 2025", f"{topic} mimari onerileri eksikler"]
    elif any(w in t for w in ['haber', 'gundem', 'son dakika', 'politik', 'ekonomi',
                                'piyasa', 'borsa', 'doviz', 'enflasyon', 'secim', 'savas']):
        queries += [f"{topic} son gelismeler analiz", f"{topic} uzman yorumu"]
    elif any(w in t for w in ['urun', 'marka', 'sirket', 'firma', 'company', 'brand', 'startup']):
        queries += [f"{topic} analiz rapor 2025", f"{topic} piyasa karsilastirma avantajlar"]
    else:
        queries += [f"{topic} nedir nasil calisir", f"{topic} guncel durum avantaj dezavantaj 2025"]

    return list(dict.fromkeys(queries))[:5]  # tekrar yok, maks 5


def tool_research_async(
    topic: str,
    report_style: str = "standard",
    max_sources: int = 10,
    out_path: str = "",
) -> Dict[str, Any]:
    """Arastirmayi ARKA PLANDA baslatir. Hemen 'Arastirma basladi' mesaji don.
    Arastirma bitince Telegram'a ozet ve rapor dosyasi gonderilir.

    Args:
        topic: Arastirilacak konu (ne kadar detayli, o kadar iyi)
        report_style: standard, technical, academic, brief
        max_sources: Kullanilacak max kaynak sayisi (varsayilan: 10)
        out_path: Cikti dosyasi yolu (opsiyonel, bos birakilirsa otomatik)
    """
    if not topic.strip():
        return {"error": "Konu bos olamaz."}

    safe_name = re.sub(r'[^\w\s-]', '', topic[:40]).strip().replace(' ', '_')
    if not safe_name:
        safe_name = f"arastirma_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    def _run():
        # Lazy import to avoid circular deps
        from .notifier import notify
        from .notebook_tools import (
            tool_notebook_create,
            tool_notebook_add_note,
            tool_notebook_complete_step,
        )
        from .registry import execute_tool
        from ..config import settings

        start_ts = time.time()

        # 1. Not defteri aç
        try:
            tool_notebook_create(
                name=safe_name,
                goal=topic,
                steps=(
                    "Konuya ozgu sorgular belirle\n"
                    "Kaynaklari tara ve topla\n"
                    "Kaynak iceriklerini oku ve not al\n"
                    "Bulgulari sentezle\n"
                    "Rapor olustur ve bildir"
                ),
            )
            notify(
                f"\U0001f4da <b>Arastirma basladi:</b> {topic[:80]}\n\n"
                f"Not defteri: <code>{safe_name}</code>\n"
                f"Bitince raporu buraya gondereceğim. (~3-8 dk)"
            )
        except Exception as exc:
            notify(f"\u26a0\ufe0f Arastirma baslatılamadı: {exc}")
            return

        try:
            # 2. Konuya özgü sorgular
            queries = _generate_smart_queries(topic)
            tool_notebook_add_note(name=safe_name, note=f"Alt sorgular: {queries}")

            # 3. Haber/web ara
            all_sources: list = []
            for q in queries:
                try:
                    res = execute_tool("search_news", {"query": q, "max_results": 5})
                    items = res.get("results", []) or res.get("items", [])
                    all_sources.extend(items)
                    tool_notebook_add_note(name=safe_name, note=f"'{q}': {len(items)} kaynak")
                except Exception as exc2:
                    tool_notebook_add_note(name=safe_name, note=f"'{q}' hatasi: {exc2}")

            tool_notebook_complete_step(
                name=safe_name, step_keyword="tara",
                finding=f"{len(all_sources)} toplam kaynak"
            )

            # 4. Kaynakları oku
            read_contents: list = []
            seen: set = set()
            for item in all_sources[:max_sources]:
                url = item.get("url", "")
                if not url or url in seen:
                    continue
                seen.add(url)
                try:
                    page = execute_tool("fetch_web_page", {"url": url, "timeout": 15})
                    content = (page.get("content", "") or page.get("text", ""))[:600]
                    if content and len(content) > 150:
                        read_contents.append({
                            "title": item.get("title", url),
                            "url": url,
                            "content": content,
                        })
                        tool_notebook_add_note(
                            name=safe_name,
                            note=f"[KAYNAK] {item.get('title', url)[:50]}: {content[:250]}"
                        )
                except Exception:
                    pass
                if time.time() - start_ts > 300:
                    break

            tool_notebook_complete_step(
                name=safe_name, step_keyword="oku",
                finding=f"{len(read_contents)} kaynak okundu"
            )

            # 5. Rapor yaz
            elapsed = int(time.time() - start_ts)
            lines = [
                f"# Arastirma Raporu: {topic}",
                f"Tarih: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC | Stil: {report_style} | Sure: {elapsed}s\n",
                "## Kaynaklar ve Bulgular",
            ]
            for i, rc in enumerate(read_contents, 1):
                lines += [f"\n### {i}. {rc['title']}", f"URL: {rc['url']}", rc['content']]
            if not read_contents:
                lines.append("Okunabilir tam kaynak bulunamadi. Haber ozeti:")
                for itm in all_sources[:6]:
                    lines.append(f"- {itm.get('title', '')}: {itm.get('summary', '')[:200]}")

            report_text = "\n".join(lines)

            # Dosya yolu
            if out_path:
                report_path = Path(settings.workspace_path) / out_path
            else:
                reports_dir = Path(settings.workspace_path) / "reports"
                reports_dir.mkdir(parents=True, exist_ok=True)
                report_path = reports_dir / f"{safe_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"

            report_path.write_text(report_text, encoding="utf-8")

            tool_notebook_complete_step(
                name=safe_name, step_keyword="rapor",
                finding=f"Rapor: {report_path}"
            )

            notify(
                f"\u2705 <b>Arastirma tamamlandi!</b>\n\n"
                f"\U0001f4cc <b>Konu:</b> {topic[:80]}\n"
                f"\U0001f4ca <b>Kaynak:</b> {len(read_contents)} kaynak okundu\n"
                f"\u23f1 <b>Sure:</b> {elapsed} saniye\n\nDosya asagida \U0001f447",
                file_path=str(report_path),
            )

        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("[research_async] Hata: %s", exc, exc_info=True)
            try:
                from .notifier import notify as _n
                _n(f"\u274c <b>Arastirma hatasi:</b> {exc}")
            except Exception:
                pass

    threading.Thread(target=_run, daemon=True, name=f"research_{safe_name}").start()

    return {
        "success": True,
        "status": "started",
        "notebook": safe_name,
        "message": (
            f"Araştırma arka planda başlatıldı: {topic}\n"
            f"Bitince Telegram'a rapor gönderilecek. (~3-8 dakika)"
        ),
    }
