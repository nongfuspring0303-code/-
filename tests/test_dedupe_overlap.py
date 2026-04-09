from scripts.ai_event_intel import _dedupe_items


def test_dedupe_detects_high_overlap():
    items = [
        {
            "headline": "Fed announces emergency liquidity action",
            "source_url": "https://www.federalreserve.gov/",
            "timestamp": "2026-04-09T12:00:00Z",
        },
        {
            "headline": "Fed announces emergency liquidity action now",
            "source_url": "https://www.federalreserve.gov/",
            "timestamp": "2026-04-09T12:01:00Z",
        },
    ]
    output = _dedupe_items(items, window_minutes=120, similarity_threshold=0.7, min_token_overlap=2)
    assert len(output) == 1


def test_dedupe_keeps_distinct_items():
    items = [
        {
            "headline": "Fed announces emergency liquidity action",
            "source_url": "https://www.federalreserve.gov/",
            "timestamp": "2026-04-09T12:00:00Z",
        },
        {
            "headline": "ECB announces policy update",
            "source_url": "https://www.ecb.europa.eu/",
            "timestamp": "2026-04-09T12:01:00Z",
        },
    ]
    output = _dedupe_items(items, window_minutes=120, similarity_threshold=0.7, min_token_overlap=2)
    assert len(output) == 2
