from scripts.ai_event_intel import _deterministic_event_id


def test_event_id_deterministic_stable():
    headline = "Fed announces emergency liquidity action"
    source_url = "https://www.federalreserve.gov/"
    ts = "2026-04-09T12:00:00Z"
    a = _deterministic_event_id(headline, source_url, ts)
    b = _deterministic_event_id(headline, source_url, ts)
    assert a == b


def test_event_id_changes_on_headline():
    source_url = "https://www.federalreserve.gov/"
    ts = "2026-04-09T12:00:00Z"
    a = _deterministic_event_id("Fed announces emergency liquidity action", source_url, ts)
    b = _deterministic_event_id("Fed announces rate hike", source_url, ts)
    assert a != b
