from app.services import email_monitor


def test_triage_prompt_preserves_turkish_characters() -> None:
    assert "İzmir" in email_monitor._TRIAGE_PROMPT
    assert "Önizleme" in email_monitor._TRIAGE_PROMPT
    assert "Türkçe" in email_monitor._TRIAGE_PROMPT
