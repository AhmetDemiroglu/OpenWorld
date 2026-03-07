from __future__ import annotations

from pathlib import Path

import pytest

import app.agent as agent_module
import app.database as database
from app.agent import AgentService
from app.memory import SessionStore


class FakeLLM:
    def __init__(self, content: str) -> None:
        self.content = content
        self.messages = []
        self.tools = []

    async def chat(self, messages, tools):
        self.messages = messages
        self.tools = tools
        return {"message": {"content": self.content}}


def _service(tmp_path: Path) -> AgentService:
    return AgentService(SessionStore(tmp_path / "sessions"))


@pytest.mark.asyncio
async def test_telegram_chat_mode_uses_full_tools_and_skips_forced_tool_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    fake_llm = FakeLLM("Iste siirin:\nMerhaba dunya")
    service.llm = fake_llm

    monkeypatch.setattr(agent_module, "get_tools_by_names", lambda names: [])

    def _unexpected_router(_: str):
        raise AssertionError("Telegram sohbet modunda semantic router kullanilmamali.")

    def _unexpected_execute(*args, **kwargs):
        raise AssertionError("Telegram sohbet modunda LLM istemeden arac calismamali.")

    monkeypatch.setattr(agent_module, "get_relevant_tools", _unexpected_router)
    monkeypatch.setattr(agent_module, "execute_tool", _unexpected_execute)
    monkeypatch.setattr(service, "_persist_recallable_memory", lambda *args, **kwargs: None)

    reply, steps, used_tools, media_files = await service.run(
        "telegram_test",
        "bana bir siir yaz",
        source="telegram",
    )

    assert reply == "Iste siirin:\nMerhaba dunya"
    assert steps == 1
    assert used_tools == []
    assert media_files == []
    assert fake_llm.tools == []
    assert any(
        msg["role"] == "system" and "[TELEGRAM SOHBET MODU]" in msg["content"]
        for msg in fake_llm.messages
    )


@pytest.mark.asyncio
async def test_telegram_chat_mode_injects_memory_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    fake_llm = FakeLLM("Tamam.")
    service.llm = fake_llm

    monkeypatch.setattr(agent_module, "get_tools_by_names", lambda names: [])
    monkeypatch.setattr(database, "memory_recall", lambda **kwargs: {"facts": [{"fact": "Kullanici sade cevap seviyor."}]})
    monkeypatch.setattr(database, "memory_get_context", lambda limit=10: [])
    monkeypatch.setattr(service, "_persist_recallable_memory", lambda *args, **kwargs: None)

    await service.run("telegram_memory", "beni hatirliyor musun", source="telegram")

    assert any(
        msg["role"] == "system" and "[UZUN SURELI HAFIZA BAGLAMI]" in msg["content"]
        for msg in fake_llm.messages
    )
    assert any("Kullanici sade cevap seviyor." in msg["content"] for msg in fake_llm.messages)


@pytest.mark.asyncio
async def test_telegram_chat_mode_auto_stores_explicit_memory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    service.llm = FakeLLM("Tamam, hatirlayacagim.")

    saved: dict[str, str] = {}

    def _store(*, fact: str, source: str = "conversation", category: str = "general", confidence: float = 0.7):
        saved["fact"] = fact
        saved["source"] = source
        saved["category"] = category
        saved["confidence"] = str(confidence)
        return {"action": "stored"}

    monkeypatch.setattr(agent_module, "get_tools_by_names", lambda names: [])
    monkeypatch.setattr(database, "memory_recall", lambda **kwargs: {"facts": []})
    monkeypatch.setattr(database, "memory_get_context", lambda limit=10: [])
    monkeypatch.setattr(database, "memory_store", _store)

    await service.run(
        "telegram_preference",
        "Bundan sonra bana Ahmet diye hitap et, bunu hatirla.",
        source="telegram",
    )

    assert saved["fact"] == "Bundan sonra bana Ahmet diye hitap et, bunu hatirla."
    assert saved["source"] == "telegram_auto_memory"
    assert saved["category"] == "preference"


@pytest.mark.asyncio
async def test_telegram_smalltalk_variants_skip_llm(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)

    class FailingLLM:
        async def chat(self, messages, tools):
            raise AssertionError("Kucuk sohbet LLM'e gitmemeli.")

    service.llm = FailingLLM()

    monkeypatch.setattr(database, "memory_recall", lambda **kwargs: {"facts": []})
    monkeypatch.setattr(database, "memory_get_context", lambda limit=10: [])

    reply, steps, used_tools, media_files = await service.run(
        "telegram_smalltalk",
        "neler yapiyorsun",
        source="telegram",
    )

    assert reply == "Buradayım ve hazırım. Ne yapmamı istiyorsun?"
    assert steps == 1
    assert used_tools == []
    assert media_files == []


def test_database_memory_store_and_recall_roundtrip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "openworld.db"
    monkeypatch.setattr(database, "_DB_PATH", db_path)

    database.init_database()
    result = database.memory_store(
        "Kullanici filtre kahve seviyor.",
        source="test",
        category="preference",
    )

    assert result["action"] in {"stored", "updated"}

    recalled = database.memory_recall("kahve", limit=5)
    assert recalled["count"] >= 1
    assert any("kahve" in item["fact"].lower() for item in recalled["facts"])


def test_reasoning_only_enabled_for_explicit_think_or_research(tmp_path: Path) -> None:
    service = _service(tmp_path)

    assert service._should_enable_reasoning(
        user_message="neler yapiyorsun",
        source="telegram",
        chat_mode=True,
        telegram_explicit_action=False,
        notebook_resume=None,
        used_tools=[],
    ) is False

    assert service._should_enable_reasoning(
        user_message="bunu biraz dusun ve cevap ver",
        source="telegram",
        chat_mode=True,
        telegram_explicit_action=False,
        notebook_resume=None,
        used_tools=[],
    ) is True

    assert service._should_enable_reasoning(
        user_message="OpenWorld klasorunu VS Code'da ac",
        source="telegram",
        chat_mode=True,
        telegram_explicit_action=True,
        notebook_resume=None,
        used_tools=["research_async"],
    ) is True
