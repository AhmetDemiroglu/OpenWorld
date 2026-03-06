from app.tools.screen_analyzer import ActionNeeded, ScreenState, _parse_llm_response


def test_parse_llm_response_for_completion() -> None:
    analysis = _parse_llm_response(
        '{"state":"completed","action":"notify_user","target_text":"","confidence":0.92,"reasoning":"done","options":[],"completion_summary":"işlem bitti"}'
    )
    assert analysis.state == ScreenState.COMPLETED
    assert analysis.action == ActionNeeded.NOTIFY_USER
    assert analysis.completion_summary == "işlem bitti"


def test_parse_llm_response_for_question() -> None:
    analysis = _parse_llm_response(
        '{"state":"question","action":"notify_user","target_text":"","confidence":0.88,"reasoning":"seçim bekleniyor","options":["A","B"],"completion_summary":""}'
    )
    assert analysis.state == ScreenState.QUESTION
    assert analysis.options == ["A", "B"]
