from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import List

from .models import ChatMessage


class SessionStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def _path(self, session_id: str) -> Path:
        safe = "".join(ch for ch in session_id if ch.isalnum() or ch in ("-", "_"))
        return self.base_dir / f"{safe}.json"

    def load(self, session_id: str) -> List[ChatMessage]:
        path = self._path(session_id)
        if not path.exists():
            return []

        with self._lock:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                # Keep a backup and reset broken session file.
                backup = path.with_suffix(path.suffix + ".corrupt")
                try:
                    path.replace(backup)
                except Exception:
                    pass
                return []
            except Exception:
                return []

        messages: List[ChatMessage] = []
        for item in data if isinstance(data, list) else []:
            try:
                messages.append(ChatMessage(**item))
            except Exception:
                continue
        return messages

    def save(self, session_id: str, messages: List[ChatMessage]) -> None:
        path = self._path(session_id)
        payload = [m.model_dump() for m in messages]
        content = json.dumps(payload, ensure_ascii=False, indent=2)

        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_suffix(path.suffix + ".tmp")
            tmp_path.write_text(content, encoding="utf-8")
            tmp_path.replace(path)

    def list_sessions(self) -> List[str]:
        with self._lock:
            return [p.stem for p in self.base_dir.glob("*.json")]
