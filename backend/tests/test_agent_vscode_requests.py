from pathlib import Path

from app.agent import AgentService
from app.memory import SessionStore


def _service(tmp_path: Path) -> AgentService:
    return AgentService(SessionStore(tmp_path / "sessions"))


def test_extract_vscode_agent_write_request_for_codex(tmp_path: Path) -> None:
    service = _service(tmp_path)
    request = service._extract_vscode_agent_write_request(
        "OpenWorld klasörünü VS Code ile aç, Codex'e 'testleri çalıştır ve düzelt' yaz"
    )
    assert request is not None
    assert request["target"] == "codex"
    assert "testleri çalıştır ve düzelt" in request["prompt"]


def test_detect_vscode_agent_targets(tmp_path: Path) -> None:
    service = _service(tmp_path)
    targets = service._detect_vscode_agent_targets("claude code ve codex ile bak")
    assert targets == ["codex", "claudecode"]
