from __future__ import annotations

import json
from pathlib import Path
from typing import List

from .models import ChatMessage


class SessionStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        safe = "".join(ch for ch in session_id if ch.isalnum() or ch in ("-", "_"))
        return self.base_dir / f"{safe}.json"

    def load(self, session_id: str) -> List[ChatMessage]:
        path = self._path(session_id)
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return [ChatMessage(**item) for item in data]

    def save(self, session_id: str, messages: List[ChatMessage]) -> None:
        path = self._path(session_id)
        payload = [m.model_dump() for m in messages]
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_sessions(self) -> List[str]:
        return [p.stem for p in self.base_dir.glob("*.json")]

