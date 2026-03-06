from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app import telegram_bridge as bridge


class FakeMessage:
    def __init__(self) -> None:
        self.photos: list[tuple[object, str]] = []
        self.texts: list[str] = []

    async def reply_photo(self, photo, caption: str = "") -> None:
        self.photos.append((photo, caption))

    async def reply_text(self, text: str, **_: object) -> None:
        self.texts.append(text)


class FakeQuery:
    def __init__(self, data: str) -> None:
        self.data = data
        self.message = FakeMessage()
        self.edits: list[str] = []

    async def answer(self, *args, **kwargs) -> None:
        return None

    async def edit_message_text(self, text: str, **_: object) -> None:
        self.edits.append(text)


@pytest.mark.asyncio
async def test_watcher_screenshot_callback_sends_photo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    screenshot_path = tmp_path / "watcher.png"
    screenshot_path.write_bytes(b"fake-image")

    monkeypatch.setattr(bridge, "_is_allowed", lambda update: True)
    monkeypatch.setattr(bridge, "_audit", lambda *args, **kwargs: None)

    from app.tools import super_agent

    monkeypatch.setattr(super_agent, "capture_notification_screenshot", lambda prefix="": str(screenshot_path))

    query = FakeQuery("watcher_screenshot")
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id="1"),
        callback_query=query,
    )

    await bridge.callback_handler(update, SimpleNamespace())

    assert len(query.message.photos) == 1
    assert query.message.photos[0][1] == "Güncel ekran görüntüsü"


@pytest.mark.asyncio
async def test_watcher_continue_callback_acknowledges(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bridge, "_is_allowed", lambda update: True)
    monkeypatch.setattr(bridge, "_audit", lambda *args, **kwargs: None)

    from app.tools import super_agent

    seen: dict[str, bool] = {"called": False}

    def _ack(*, keep_running: bool = True):
        seen["called"] = keep_running
        return {"success": True}

    monkeypatch.setattr(super_agent, "tool_ack_approval_completion_prompt", _ack)

    query = FakeQuery("watcher_continue")
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id="1"),
        callback_query=query,
    )

    await bridge.callback_handler(update, SimpleNamespace())

    assert seen["called"] is True
    assert query.edits == ["Onay izleyici devam ediyor."]
