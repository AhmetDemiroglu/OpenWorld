"""
Journal Service — Günlük not + kalıcı todo sistemi.

Notlar  : tarih bazlı  → {workspace}/notes/YYYY-MM-DD.json
Todo'lar: kalıcı dosya → {workspace}/notes/todos.json
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from ..config import settings

logger = logging.getLogger(__name__)

# ─── Dizin ───────────────────────────────────────────────────────────────────

def _notes_dir() -> Path:
    p = settings.workspace_path / "notes"
    p.mkdir(parents=True, exist_ok=True)
    return p

def _day_file(date_str: str) -> Path:
    return _notes_dir() / f"{date_str}.json"

def _todos_file() -> Path:
    return _notes_dir() / "todos.json"


# ─── Günlük notlar ───────────────────────────────────────────────────────────

def _load_day(date_str: str) -> List[Dict]:
    f = _day_file(date_str)
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return []

def _save_day(date_str: str, notes: List[Dict]) -> None:
    _day_file(date_str).write_text(
        json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def add_note(text: str, category: str = "genel") -> Dict:
    """Bugünün not defterine yeni bir not ekle."""
    today = datetime.now().strftime("%Y-%m-%d")
    notes = _load_day(today)
    entry = {
        "id": len(notes) + 1,
        "time": datetime.now().strftime("%H:%M"),
        "category": category,
        "text": text.strip(),
    }
    notes.append(entry)
    _save_day(today, notes)
    logger.info("Journal: note added #%d (%s)", entry["id"], category)
    return entry


def get_notes(date_str: Optional[str] = None) -> List[Dict]:
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
    return _load_day(date_str)


def get_recent_notes(days: int = 7) -> List[Dict]:
    result = []
    for i in range(days):
        d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        for note in reversed(_load_day(d)):
            result.append({**note, "date": d})
    return result


def format_notes_message(notes: List[Dict], date_label: str = "Bugün") -> str:
    if not notes:
        return f"📓 {date_label} için kayıtlı not yok."
    lines = [f"📓 <b>{date_label} – Notlar</b>\n"]
    for n in notes:
        prefix = "✅" if n.get("done") else "⬜" if n.get("category") == "todo" else "🕐"
        lines.append(f"{prefix} <b>{n.get('time', '')}</b>  [{n.get('category', 'genel')}]\n{n['text']}")
    return "\n\n".join(lines)


# ─── Todo sistemi (kalıcı, tarih bağımsız) ───────────────────────────────────

def _load_todos() -> List[Dict]:
    f = _todos_file()
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return []

def _save_todos(todos: List[Dict]) -> None:
    _todos_file().write_text(
        json.dumps(todos, ensure_ascii=False, indent=2), encoding="utf-8"
    )

def _next_todo_id(todos: List[Dict]) -> int:
    if not todos:
        return 1
    return max(t.get("id", 0) for t in todos) + 1


def add_todo(text: str, category: str = "genel") -> Dict:
    """Yeni bir todo ekle (tarih bağımsız, done takibli)."""
    todos = _load_todos()
    entry = {
        "id": _next_todo_id(todos),
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "done": False,
        "done_at": None,
        "category": category,
        "text": text.strip(),
    }
    todos.append(entry)
    _save_todos(todos)
    logger.info("Journal: todo added #%d", entry["id"])
    return entry


def complete_todo(todo_id: int) -> Optional[Dict]:
    """Todo'yu tamamlandı olarak işaretle. Bulunamazsa None döner."""
    todos = _load_todos()
    for t in todos:
        if t.get("id") == todo_id:
            t["done"] = True
            t["done_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            _save_todos(todos)
            logger.info("Journal: todo #%d completed", todo_id)
            return t
    return None


def delete_todo(todo_id: int) -> bool:
    todos = _load_todos()
    new = [t for t in todos if t.get("id") != todo_id]
    if len(new) == len(todos):
        return False
    _save_todos(new)
    return True


def get_pending_todos(category: Optional[str] = None) -> List[Dict]:
    todos = _load_todos()
    result = [t for t in todos if not t.get("done")]
    if category:
        result = [t for t in result if t.get("category") == category]
    return result


def get_all_todos(include_done: bool = False) -> List[Dict]:
    todos = _load_todos()
    if not include_done:
        return [t for t in todos if not t.get("done")]
    return todos


def format_todos_message(todos: List[Dict], title: str = "Yapılacaklar") -> str:
    if not todos:
        return f"✅ {title} listesi boş."
    pending = [t for t in todos if not t.get("done")]
    done = [t for t in todos if t.get("done")]
    lines = [f"📋 <b>{title}</b>\n"]
    if pending:
        for t in pending:
            cat = f" [{t.get('category', 'genel')}]" if t.get("category", "genel") != "genel" else ""
            lines.append(f"⬜ <b>#{t['id']}</b>{cat}  {t['created'][:10]}\n{t['text']}")
    if done:
        lines.append("\n<i>— Tamamlananlar —</i>")
        for t in done[-5:]:  # Son 5 tamamlanan
            lines.append(f"✅ <b>#{t['id']}</b>  {t.get('done_at', '')[:10]}\n<s>{t['text']}</s>")
    return "\n\n".join(lines)


# ─── AI Export ───────────────────────────────────────────────────────────────

def export_for_ai(include_notes_days: int = 0) -> str:
    """
    Tüm bekleyen todo'ları + (opsiyonel) son N günün notlarını
    AI'ye gönderilebilir temiz metin formatında döndürür.
    """
    sections: List[str] = []

    # Pending todos
    todos = get_pending_todos()
    if todos:
        todo_lines = ["## YAPILACAKLAR LİSTESİ\n"]
        for t in todos:
            cat = f" [{t['category']}]" if t.get("category", "genel") != "genel" else ""
            todo_lines.append(f"- [{t['id']}]{cat} {t['text']}  (eklendi: {t['created']})")
        sections.append("\n".join(todo_lines))

    # Recent notes
    if include_notes_days > 0:
        notes = get_recent_notes(days=include_notes_days)
        if notes:
            note_lines = [f"## SON {include_notes_days} GÜNÜN NOTLARI\n"]
            for n in notes:
                note_lines.append(f"- [{n.get('date','')} {n.get('time','')}] [{n.get('category','genel')}] {n['text']}")
            sections.append("\n".join(note_lines))

    if not sections:
        return "Kayıtlı todo veya not bulunamadı."

    header = f"# OpenWorld Not Defteri Dışa Aktarımı\nTarih: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
    return header + "\n\n".join(sections)
