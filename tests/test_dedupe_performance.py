import time

from scripts.ai_event_intel import _dedupe_items


def _make_item(i: int) -> dict:
    return {
        "headline": f"Fed announces emergency liquidity action {i}",
        "source_url": "https://www.federalreserve.gov/",
        "timestamp": "2026-04-09T12:00:00Z",
    }


def test_dedupe_scales_with_token_index():
    items = [_make_item(i) for i in range(200)]
    start = time.time()
    _ = _dedupe_items(items, window_minutes=120, similarity_threshold=0.8)
    elapsed = time.time() - start
    # should remain fast for small batches
    assert elapsed < 1.0
