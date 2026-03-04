"""
ARASTIRMA NOT DEFTERİ SİSTEMİ
Modelin karmaşık görevlerde bağlamı koruması için markdown tabanlı not defteri.
Görev parçalama, adım takibi ve bağlam yenileme sağlar.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import settings

_NOTEBOOK_DIR = settings.workspace_path / "notebooks"


def _ensure_dir() -> Path:
    _NOTEBOOK_DIR.mkdir(parents=True, exist_ok=True)
    return _NOTEBOOK_DIR


def _sanitize_name(name: str) -> str:
    safe = re.sub(r'[^\w\s\-]', '', name.strip())
    safe = re.sub(r'\s+', '_', safe)
    return safe[:60] or "not_defteri"


def _notebook_path(name: str) -> Path:
    return _ensure_dir() / f"{_sanitize_name(name)}.md"


def _read_notebook(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _parse_steps(content: str) -> List[Dict[str, Any]]:
    """Markdown içeriğinden adım listesini parse et."""
    steps: List[Dict[str, Any]] = []
    for match in re.finditer(
        r'^- \[([ xX])\] (.+)$', content, re.MULTILINE
    ):
        done = match.group(1).lower() == 'x'
        steps.append({"text": match.group(2).strip(), "done": done})
    return steps


# =============================================================================
# TOOL FONKSİYONLARI
# =============================================================================


def tool_notebook_create(
    name: str,
    goal: str = "",
    steps: str = "",
) -> Dict[str, Any]:
    """Yeni araştırma/görev not defteri oluştur.

    Args:
        name: Not defteri adı (ör: "Iran_ABD_Arastirma")
        goal: Ana hedef/görev açıklaması
        steps: Adımlar (satır satır, her satır bir adım)
    """
    try:
        path = _notebook_path(name)

        lines = [
            f"# {name.strip()}",
            f"**Oluşturma:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC",
            f"**Durum:** Devam Ediyor",
            "",
        ]

        if goal:
            lines.extend([
                "## Hedef",
                goal.strip(),
                "",
            ])

        if steps:
            lines.append("## Adimlar")
            for step in steps.strip().split('\n'):
                step = step.strip().lstrip('-').lstrip('0123456789.').strip()
                if step:
                    lines.append(f"- [ ] {step}")
            lines.append("")

        lines.extend([
            "## Notlar",
            "",
            "---",
            "",
        ])

        content = "\n".join(lines)
        path.write_text(content, encoding="utf-8")

        return {
            "success": True,
            "path": str(path),
            "name": name,
            "step_count": len(steps.strip().split('\n')) if steps else 0,
            "message": "Not defteri olusturuldu. Adim adim ilerle, her adimda not ekle.",
        }
    except Exception as e:
        return {"error": str(e)}


def tool_notebook_add_note(
    name: str,
    note: str,
    section: str = "Notlar",
) -> Dict[str, Any]:
    """Not defterine not/bulgu ekle. Bağlamı korumak için her adımda kullan.

    Args:
        name: Not defteri adı
        note: Eklenecek not (bulgu, sonuç, gözlem)
        section: Hangi bölüme eklenecek (varsayılan: Notlar)
    """
    try:
        path = _notebook_path(name)
        content = _read_notebook(path)
        if not content:
            return {"error": f"Not defteri bulunamadi: {name}. Once notebook_create ile olustur."}

        timestamp = datetime.utcnow().strftime('%H:%M')
        new_note = f"- [{timestamp}] {note.strip()}"

        # Bölümü bul ve not ekle
        section_header = f"## {section}"
        if section_header in content:
            # Bölümün sonuna (bir sonraki ## veya --- öncesine) ekle
            parts = content.split(section_header, 1)
            after = parts[1]
            # Sonraki bölüm veya ayırıcıyı bul
            next_section = re.search(r'\n(## |\n---)', after)
            if next_section:
                insert_pos = next_section.start()
                after = after[:insert_pos] + "\n" + new_note + after[insert_pos:]
            else:
                after = after.rstrip() + "\n" + new_note + "\n"
            content = parts[0] + section_header + after
        else:
            # Bölüm yoksa oluştur
            content = content.rstrip() + f"\n\n{section_header}\n{new_note}\n"

        path.write_text(content, encoding="utf-8")

        # Mevcut durumu özetle
        steps = _parse_steps(content)
        done_count = sum(1 for s in steps if s["done"])
        pending = [s["text"] for s in steps if not s["done"]]

        result: Dict[str, Any] = {
            "success": True,
            "path": str(path),
            "total_notes": content.count("\n- ["),
        }
        if steps:
            result["progress"] = f"{done_count}/{len(steps)} adim tamamlandi"
            if pending:
                result["next_step"] = pending[0]
                result["remaining_steps"] = len(pending)
        return result
    except Exception as e:
        return {"error": str(e)}


def tool_notebook_complete_step(
    name: str,
    step_keyword: str,
    finding: str = "",
) -> Dict[str, Any]:
    """Bir adımı tamamlandı olarak işaretle ve bulgu ekle.

    Args:
        name: Not defteri adı
        step_keyword: Tamamlanan adımdaki anahtar kelime (eşleşme için)
        finding: Bu adımdan elde edilen bulgu/sonuç
    """
    try:
        path = _notebook_path(name)
        content = _read_notebook(path)
        if not content:
            return {"error": f"Not defteri bulunamadi: {name}"}

        # Adımı bul ve tamamla
        keyword_lower = step_keyword.lower()
        lines = content.split('\n')
        matched = False
        for i, line in enumerate(lines):
            if re.match(r'^- \[ \] ', line) and keyword_lower in line.lower():
                lines[i] = line.replace("- [ ] ", "- [x] ", 1)
                if finding:
                    lines.insert(i + 1, f"  > **Bulgu:** {finding.strip()}")
                matched = True
                break

        if not matched:
            return {"error": f"Adim bulunamadi: '{step_keyword}'. Mevcut adimlari kontrol et."}

        content = '\n'.join(lines)
        path.write_text(content, encoding="utf-8")

        steps = _parse_steps(content)
        done_count = sum(1 for s in steps if s["done"])
        pending = [s["text"] for s in steps if not s["done"]]

        result: Dict[str, Any] = {
            "success": True,
            "progress": f"{done_count}/{len(steps)} adim tamamlandi",
        }
        if pending:
            result["next_step"] = pending[0]
            result["remaining_steps"] = len(pending)
        else:
            result["message"] = "Tum adimlar tamamlandi!"
            # Durumu güncelle
            content = content.replace("**Durum:** Devam Ediyor", "**Durum:** Tamamlandi")
            path.write_text(content, encoding="utf-8")

        return result
    except Exception as e:
        return {"error": str(e)}


def tool_notebook_status(name: str) -> Dict[str, Any]:
    """Not defterinin mevcut durumunu oku - bağlamı yenile.
    Her yeni LLM turunda bu aracı çağırarak nerede kaldığını hatırla.

    Args:
        name: Not defteri adı
    """
    try:
        path = _notebook_path(name)
        content = _read_notebook(path)
        if not content:
            return {"error": f"Not defteri bulunamadi: {name}"}

        steps = _parse_steps(content)
        done_count = sum(1 for s in steps if s["done"])
        pending = [s["text"] for s in steps if not s["done"]]
        completed = [s["text"] for s in steps if s["done"]]

        # Son notları çıkar
        notes: List[str] = []
        for match in re.finditer(r'^- \[\d{2}:\d{2}\] (.+)$', content, re.MULTILINE):
            notes.append(match.group(1))

        # Hedefi cikar
        goal_match = re.search(r'^## Hedef\s*\n(.+?)(?=\n##|\Z)', content, re.MULTILINE | re.DOTALL)
        goal = goal_match.group(1).strip() if goal_match else ""
        
        result: Dict[str, Any] = {
            "path": str(path),
            "name": name,
            "goal": goal,
            "total_steps": len(steps),
            "completed_steps": done_count,
            "completed_list": completed,
            "pending_steps": pending,
            "recent_notes": notes[-8:] if notes else [],
            "total_notes": len(notes),
        }

        if pending:
            result["next_step"] = pending[0]
            result["message"] = (
                f"{done_count}/{len(steps)} adim tamamlandi. "
                f"Siradaki: {pending[0]}"
            )
        else:
            if steps:
                result["message"] = "Tum adimlar tamamlandi!"
            else:
                result["message"] = "Not defteri adim icermiyor, sadece notlar mevcut."

        # Tam içeriği de ver (model bağlamı yenileyebilsin)
        if len(content) <= 4000:
            result["full_content"] = content
        else:
            result["full_content"] = content[:4000] + "\n...(kesildi)"

        return result
    except Exception as e:
        return {"error": str(e)}


def tool_notebook_list() -> Dict[str, Any]:
    """Mevcut tüm not defterlerini listele."""
    try:
        _ensure_dir()
        notebooks: List[Dict[str, Any]] = []
        for f in sorted(_NOTEBOOK_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
            content = f.read_text(encoding="utf-8")
            steps = _parse_steps(content)
            done = sum(1 for s in steps if s["done"])
            status = "Tamamlandi" if (steps and done == len(steps)) else "Devam Ediyor" if steps else "Not Defteri"
            notebooks.append({
                "name": f.stem,
                "status": status,
                "progress": f"{done}/{len(steps)}" if steps else "-",
                "modified": datetime.fromtimestamp(f.stat().st_mtime).strftime('%Y-%m-%d %H:%M'),
            })
        return {
            "notebooks": notebooks,
            "count": len(notebooks),
            "directory": str(_NOTEBOOK_DIR),
        }
    except Exception as e:
        return {"error": str(e)}


def tool_notebook_add_step(name: str, step: str) -> Dict[str, Any]:
    """Not defterine yeni adım ekle (devam eden iş için).

    Args:
        name: Not defteri adı
        step: Yeni adım açıklaması
    """
    try:
        path = _notebook_path(name)
        content = _read_notebook(path)
        if not content:
            return {"error": f"Not defteri bulunamadi: {name}"}

        new_step = f"- [ ] {step.strip()}"

        # Adimlar bölümüne ekle
        if "## Adimlar" in content:
            # Son adımdan sonra ekle
            lines = content.split('\n')
            last_step_idx = -1
            for i, line in enumerate(lines):
                if re.match(r'^- \[[ xX]\] ', line):
                    last_step_idx = i
                # Bulgu satırlarını atla
                elif line.strip().startswith('> **Bulgu:**'):
                    continue

            if last_step_idx >= 0:
                # Bulgu satırını da atla
                insert_at = last_step_idx + 1
                while insert_at < len(lines) and lines[insert_at].strip().startswith('> **Bulgu:**'):
                    insert_at += 1
                lines.insert(insert_at, new_step)
                content = '\n'.join(lines)
            else:
                content = content.replace("## Adimlar\n", f"## Adimlar\n{new_step}\n")
        else:
            # Adımlar bölümü yoksa oluştur
            content = content.replace("## Notlar", f"## Adimlar\n{new_step}\n\n## Notlar")

        path.write_text(content, encoding="utf-8")

        steps = _parse_steps(content)
        return {
            "success": True,
            "total_steps": len(steps),
            "new_step": step.strip(),
        }
    except Exception as e:
        return {"error": str(e)}
