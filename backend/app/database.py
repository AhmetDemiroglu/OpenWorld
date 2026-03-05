"""
VERİTABANI ve HAFIZA SİSTEMİ
SQLite tabanlı session storage + uzun süreli hafıza
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional

from .config import settings

_DB_PATH = settings.data_path / "openworld.db"
_lock = RLock()


def _get_connection() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_database() -> None:
    """Veritabanı tablolarını oluştur."""
    with _lock:
        conn = _get_connection()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT,
                    name TEXT,
                    tool_call_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_sid ON sessions(session_id);

                CREATE TABLE IF NOT EXISTS tool_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    arguments TEXT,
                    result_summary TEXT,
                    success BOOLEAN DEFAULT 1,
                    duration_ms INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_tool_usage_sid ON tool_usage(session_id);
                CREATE INDEX IF NOT EXISTS idx_tool_usage_name ON tool_usage(tool_name);

                CREATE TABLE IF NOT EXISTS memory_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fact TEXT NOT NULL,
                    source TEXT DEFAULT 'conversation',
                    category TEXT DEFAULT 'general',
                    confidence REAL DEFAULT 0.7,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_accessed TIMESTAMP,
                    access_count INTEGER DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_memory_category ON memory_facts(category);

                CREATE TABLE IF NOT EXISTS user_preferences (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS smart_assistant_state (
                    feature_key TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS email_seen_log (
                    message_id TEXT PRIMARY KEY,
                    subject TEXT,
                    seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()
        finally:
            conn.close()


# =============================================================================
# SESSION MANAGEMENT (SQLite)
# =============================================================================


class SQLiteSessionStore:
    """SessionStore'un SQLite versiyonu - JSON fallback ile."""

    def __init__(self) -> None:
        init_database()

    def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        name: Optional[str] = None,
        tool_call_id: Optional[str] = None,
    ) -> None:
        with _lock:
            conn = _get_connection()
            try:
                conn.execute(
                    "INSERT INTO sessions (session_id, role, content, name, tool_call_id) VALUES (?, ?, ?, ?, ?)",
                    (session_id, role, content, name, tool_call_id),
                )
                conn.commit()
            finally:
                conn.close()

    def load_messages(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        with _lock:
            conn = _get_connection()
            try:
                rows = conn.execute(
                    "SELECT role, content, name, tool_call_id FROM sessions WHERE session_id =  ORDER BY id DESC LIMIT ?",
                    (session_id, limit),
                ).fetchall()
                messages = []
                for row in reversed(rows):
                    msg: Dict[str, Any] = {"role": row["role"], "content": row["content"]}
                    if row["name"]:
                        msg["name"] = row["name"]
                    if row["tool_call_id"]:
                        msg["tool_call_id"] = row["tool_call_id"]
                    messages.append(msg)
                return messages
            finally:
                conn.close()

    def list_sessions(self) -> List[Dict[str, Any]]:
        with _lock:
            conn = _get_connection()
            try:
                rows = conn.execute("""
                    SELECT session_id, COUNT(*) as msg_count,
                           MIN(created_at) as first_msg,
                           MAX(created_at) as last_msg
                    FROM sessions
                    GROUP BY session_id
                    ORDER BY last_msg DESC
                """).fetchall()
                return [
                    {
                        "session_id": row["session_id"],
                        "message_count": row["msg_count"],
                        "first_message": row["first_msg"],
                        "last_message": row["last_msg"],
                    }
                    for row in rows
                ]
            finally:
                conn.close()


# =============================================================================
# TOOL USAGE TRACKING
# =============================================================================


def log_tool_usage(
    session_id: str,
    tool_name: str,
    arguments: Optional[Dict[str, Any]] = None,
    result_summary: str = "",
    success: bool = True,
    duration_ms: int = 0,
) -> None:
    """Araç kullanımını logla."""
    with _lock:
        conn = _get_connection()
        try:
            args_json = json.dumps(arguments or {}, ensure_ascii=False)[:2000]
            conn.execute(
                "INSERT INTO tool_usage (session_id, tool_name, arguments, result_summary, success, duration_ms) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, tool_name, args_json, result_summary[:500], success, duration_ms),
            )
            conn.commit()
        finally:
            conn.close()


def get_tool_stats(days: int = 7) -> Dict[str, Any]:
    """Araç kullanım istatistikleri."""
    with _lock:
        conn = _get_connection()
        try:
            rows = conn.execute("""
                SELECT tool_name, COUNT(*) as count,
                       SUM(CASE WHEN success THEN 1 ELSE 0 END) as success_count,
                       AVG(duration_ms) as avg_duration
                FROM tool_usage
                WHERE created_at >= datetime('now', ?)
                GROUP BY tool_name
                ORDER BY count DESC
            """, (f"-{days} days",)).fetchall()
            return {
                "period_days": days,
                "tools": [
                    {
                        "name": row["tool_name"],
                        "count": row["count"],
                        "success_rate": round(row["success_count"] / max(row["count"], 1) * 100, 1),
                        "avg_duration_ms": round(row["avg_duration"] or 0),
                    }
                    for row in rows
                ],
            }
        finally:
            conn.close()


# =============================================================================
# UZUN SÜRELİ HAFIZA
# =============================================================================


def memory_store(
    fact: str,
    source: str = "conversation",
    category: str = "general",
    confidence: float = 0.7,
) -> Dict[str, Any]:
    """Uzun süreli hafızaya bilgi kaydet."""
    if not fact.strip():
        return {"error": "Fact bos olamaz."}

    with _lock:
        conn = _get_connection()
        try:
            # Benzer fact var mı kontrol et
            existing = conn.execute(
                "SELECT id, fact, confidence FROM memory_facts WHERE fact LIKE  LIMIT 1",
                (f"%{fact.strip()[:50]}%",),
            ).fetchone()

            if existing:
                # Güncelle ve confidence artır
                new_confidence = min(existing["confidence"] + 0.1, 1.0)
                conn.execute(
                    "UPDATE memory_facts SET confidence = ?, last_accessed = CURRENT_TIMESTAMP, access_count = access_count + 1 WHERE id = ?",
                    (new_confidence, existing["id"]),
                )
                conn.commit()
                return {
                    "action": "updated",
                    "fact": existing["fact"],
                    "confidence": new_confidence,
                }

            conn.execute(
                "INSERT INTO memory_facts (fact, source, category, confidence) VALUES (?, ?, ?, ?)",
                (fact.strip(), source, category, confidence),
            )
            conn.commit()
            return {
                "action": "stored",
                "fact": fact.strip(),
                "category": category,
                "confidence": confidence,
            }
        finally:
            conn.close()


def memory_recall(
    query: str = "",
    category: str = "",
    limit: int = 10,
) -> Dict[str, Any]:
    """Uzun süreli hafızadan bilgi hatırla."""
    with _lock:
        conn = _get_connection()
        try:
            conditions = []
            params: List[Any] = []

            if query.strip():
                # Keyword bazlı arama
                keywords = query.strip().split()
                for kw in keywords[:5]:
                    conditions.append("fact LIKE ?")
                    params.append(f"%{kw}%")

            if category.strip():
                conditions.append("category = ?")
                params.append(category)

            where = " AND ".join(conditions) if conditions else "1=1"

            rows = conn.execute(
                f"""SELECT id, fact, source, category, confidence, created_at, access_count
                    FROM memory_facts
                    WHERE {where}
                    ORDER BY confidence DESC, access_count DESC
                    LIMIT ?""",
                params + [min(limit, 50)],
            ).fetchall()

            # Access count güncelle
            for row in rows:
                conn.execute(
                    "UPDATE memory_facts SET last_accessed = CURRENT_TIMESTAMP, access_count = access_count + 1 WHERE id = ?",
                    (row["id"],),
                )
            conn.commit()

            facts = [
                {
                    "fact": row["fact"],
                    "source": row["source"],
                    "category": row["category"],
                    "confidence": row["confidence"],
                    "created": row["created_at"],
                }
                for row in rows
            ]

            return {
                "facts": facts,
                "count": len(facts),
                "query": query,
            }
        finally:
            conn.close()


def memory_get_context(limit: int = 10) -> List[str]:
    """Konuşma başlangıcında yüklenecek en önemli hatıralar."""
    with _lock:
        conn = _get_connection()
        try:
            rows = conn.execute(
                """SELECT fact FROM memory_facts
                   ORDER BY confidence DESC, access_count DESC, created_at DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
            return [row["fact"] for row in rows]
        finally:
            conn.close()


# =============================================================================
# KULLANICI TERCİHLERİ
# =============================================================================


def set_preference(key: str, value: str) -> None:
    with _lock:
        conn = _get_connection()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO user_preferences (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                (key, value),
            )
            conn.commit()
        finally:
            conn.close()


def get_preference(key: str, default: str = "") -> str:
    with _lock:
        conn = _get_connection()
        try:
            row = conn.execute("SELECT value FROM user_preferences WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else default
        finally:
            conn.close()


# =============================================================================
# SMART ASSISTANT & EMAIL MONITOR PERSISTENCE
# =============================================================================

def save_assistant_state(feature_key: str, state: Dict[str, Any]) -> None:
    with _lock:
        conn = _get_connection()
        try:
            state_str = json.dumps(state, ensure_ascii=False)
            conn.execute(
                "INSERT OR REPLACE INTO smart_assistant_state (feature_key, state_json, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                (feature_key, state_str),
            )
            conn.commit()
        finally:
            conn.close()

def load_assistant_state(feature_key: str) -> Dict[str, Any]:
    with _lock:
        conn = _get_connection()
        try:
            row = conn.execute("SELECT state_json FROM smart_assistant_state WHERE feature_key = ?", (feature_key,)).fetchone()
            if row and row["state_json"]:
                return json.loads(row["state_json"])
            return {}
        finally:
            conn.close()

def mark_email_seen(message_id: str, subject: str) -> None:
    with _lock:
        conn = _get_connection()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO email_seen_log (message_id, subject) VALUES (?, ?)",
                (message_id, subject[:200]),
            )
            conn.commit()
        finally:
            conn.close()


def unmark_email_seen(message_id: str) -> None:
    with _lock:
        conn = _get_connection()
        try:
            conn.execute("DELETE FROM email_seen_log WHERE message_id = ?", (message_id,))
            conn.commit()
        finally:
            conn.close()


def get_seen_emails(days: int = 7) -> List[Dict[str, str]]:
    with _lock:
        conn = _get_connection()
        try:
            rows = conn.execute(
                "SELECT message_id, subject FROM email_seen_log WHERE seen_at >= datetime('now', ?)",
                (f"-{days} days",)
            ).fetchall()
            return [{"id": r["message_id"], "subject": r["subject"]} for r in rows]
        finally:
            conn.close()


def migrate_json_sessions(json_dir: Path) -> Dict[str, Any]:
    """Mevcut JSON session dosyalarını SQLite'a import et."""
    if not json_dir.exists():
        return {"error": "JSON dizini bulunamadi.", "migrated": 0}

    init_database()
    migrated = 0
    errors = 0

    for json_file in json_dir.glob("*.json"):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                continue

            session_id = json_file.stem
            conn = _get_connection()
            try:
                # Zaten import edilmiş mi kontrol et
                existing = conn.execute(
                    "SELECT COUNT(*) as c FROM sessions WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                if existing["c"] > 0:
                    continue

                for item in data:
                    if not isinstance(item, dict):
                        continue
                    conn.execute(
                        "INSERT INTO sessions (session_id, role, content, name, tool_call_id) VALUES (?, ?, ?, ?, ?)",
                        (
                            session_id,
                            item.get("role", ""),
                            item.get("content", ""),
                            item.get("name"),
                            item.get("tool_call_id"),
                        ),
                    )
                conn.commit()
                migrated += 1
            finally:
                conn.close()
        except Exception:
            errors += 1

    return {
        "migrated": migrated,
        "errors": errors,
        "db_path": str(_DB_PATH),
    }
