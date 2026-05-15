import time

from scripts.ai_event_intel import _dedupe_items


def _make_item(headline: str, *, stamp: str = "2026-04-09T12:00:00Z") -> dict:
    return {
        "headline": headline,
        "source_url": "https://www.federalreserve.gov/",
        "timestamp": stamp,
    }


def test_dedupe_scales_with_token_index():
    duplicate_headline = "Fed announces emergency liquidity action for banks"
    distinct_headline = "Fed announces emergency liquidity action for markets"

    items = [
        _make_item(duplicate_headline),
        _make_item(duplicate_headline),
        _make_item(distinct_headline),
        _make_item(distinct_headline),
        _make_item(duplicate_headline, stamp="2026-04-09T12:01:00Z"),
        _make_item(distinct_headline, stamp="2026-04-09T12:01:00Z"),
    ]

    start = time.perf_counter()
    deduped = _dedupe_items(items, window_minutes=120, similarity_threshold=0.8)
    elapsed = time.perf_counter() - start

    assert len(deduped) == 2
    assert [item["headline"] for item in deduped] == [duplicate_headline, distinct_headline]
    assert deduped[0] is items[0]
    assert deduped[1] is items[2]
    assert elapsed < 1.0
