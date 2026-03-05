from __future__ import annotations

import json
import inspect
import html as html_lib
import ipaddress
import os
import platform
import psutil
import re
import shutil
import socket
import subprocess
import uuid
from urllib.parse import quote_plus, urlparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple, Optional
import xml.etree.ElementTree as ET

import httpx

from app.config import settings
from app.secrets import decrypt_text
from app.database import memory_store, memory_recall, get_tool_stats

import logging
import asyncio
logger = logging.getLogger(__name__)


import os
import re
import json


from datetime import datetime




def tool_create_word_document(path: str, title: str, content: str, style: str = "default") -> Dict[str, Any]:
    """Word belgesi olustur (HTML formatinda .html)."""
    target = _resolve_path(path)
    warnings: List[str] = []
    target, rerouted_from = _normalize_generated_target(target, "reports")
    if rerouted_from:
        warnings.append(f"Istenen yol workspace disindaydi, data altina yonlendirildi: {rerouted_from}")

    try:
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        body {{ font-family: Calibri, Arial, sans-serif; margin: 40px; }}
        h1 {{ color: #2c3e50; }}
        h2 {{ color: #34495e; }}
        p {{ line-height: 1.6; }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    {content.replace(chr(10), '<br>')}
    <hr>
    <p><small>Olusturulma: {datetime.now().strftime('%Y-%m-%d %H:%M')}</small></p>
</body>
</html>"""

        target.parent.mkdir(parents=True, exist_ok=True)
        if target.suffix.lower() != ".html":
            target = target.with_suffix(".html")
        target.write_text(html_content, encoding="utf-8")

        payload: Dict[str, Any] = {
            "path": str(target),
            "title": title,
            "size": len(html_content),
            "note": "HTML formatinda Word uyumlu belge",
        }
        if warnings:
            payload["warnings"] = warnings
        return payload
    except Exception as e:
        return {"error": str(e)}

def tool_create_markdown_report(
    path: str = "",
    title: str = "",
    sections: Optional[List[Dict[str, str]]] = None,
    content: str = "",
) -> Dict[str, Any]:
    """Markdown raporu olustur. Daha esnek input kabul eder."""
    try:
        warnings: List[str] = []
        clean_title = (title or "").strip() or "Rapor"
        clean_content = content or ""

        normalized_sections: List[Dict[str, str]] = []
        if isinstance(sections, list):
            for section in sections:
                if not isinstance(section, dict):
                    continue
                normalized_sections.append(
                    {
                        "title": str(section.get("title", "Bolum")),
                        "content": str(section.get("content", "")),
                    }
                )

        if not normalized_sections and clean_content.strip():
            normalized_sections.append({"title": "Detay", "content": clean_content})

        if not normalized_sections:
            normalized_sections.append({"title": "Detay", "content": "Icerik belirtilmedi."})

        if path:
            target = _resolve_path(path)
        else:
            stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            target = (settings.workspace_path / "reports" / f"report_{stamp}.md").resolve()
        target, rerouted_from = _normalize_generated_target(target, "reports")
        if rerouted_from:
            warnings.append(f"Istenen yol workspace disindaydi, data altina yonlendirildi: {rerouted_from}")

        lines = [f"# {clean_title}", "", f"*Olusturulma: {datetime.now().strftime('%Y-%m-%d %H:%M')}*", ""]
        for section in normalized_sections:
            lines.append(f"## {section.get('title', 'Bolum')}")
            lines.append("")
            lines.append(section.get("content", ""))
            lines.append("")

        report_text = "\n".join(lines)
        if target.suffix.lower() != ".md":
            target = target.with_suffix(".md")

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(report_text, encoding="utf-8")

        payload: Dict[str, Any] = {
            "path": str(target),
            "title": clean_title,
            "sections": len(normalized_sections),
            "size": len(report_text),
        }
        if warnings:
            payload["warnings"] = warnings
        return payload
    except Exception as e:
        return {"error": str(e)}

# =============================================================================
# SİSTEM BİLGİSİ ARAÇLARI
# =============================================================================

