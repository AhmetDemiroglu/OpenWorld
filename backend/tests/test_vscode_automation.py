from app.tools import vscode_automation as va


def test_normalize_agent_key_maps_aliases() -> None:
    assert va.normalize_agent_key("Kimi Code") == "kimicode"
    assert va.normalize_agent_key("claude code") == "claudecode"
    assert va.normalize_agent_key("codex") == "codex"


def test_get_agent_strategy_has_expected_commands() -> None:
    strategy = va.get_agent_strategy("codex")
    assert strategy.display_name == "Codex"
    assert strategy.command_palette_sequence == ("New Codex Agent",)


def test_window_looks_ready_accepts_expected_markers() -> None:
    strategy = va.get_agent_strategy("kimicode")
    assert va._window_looks_ready("Kimi Code message input", strategy) is True
    assert va._window_looks_ready("GitHub Copilot panel", strategy) is False
