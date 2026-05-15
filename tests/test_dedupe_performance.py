import time

from scripts.ai_event_intel import _dedupe_items


def _make_item(headline: str, *, stamp: str = "2026-04-09T12:00:00Z") -> dict:
    return {
        "headline": headline,
        "source_url": "https://www.federalreserve.gov/",
        "timestamp": stamp,
    }


def test_dedupe_preserves_survivor_order_and_removes_duplicates():
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

    deduped = _dedupe_items(items, window_minutes=120, similarity_threshold=0.8)

    assert len(deduped) == 2
    assert [item["headline"] for item in deduped] == [duplicate_headline, distinct_headline]
    assert deduped[0] is items[0]
    assert deduped[1] is items[2]


def test_dedupe_scales_with_token_index():
    groups = 50
    duplicates_per_group = 4
    items = []
    for group in range(groups):
        headline = (
            f"Fed announces emergency liquidity action group {group} "
            f"alpha{group} beta{group} gamma{group} delta{group} epsilon{group} "
            f"zeta{group} eta{group} theta{group} iota{group} kappa{group}"
        )
        for dup in range(duplicates_per_group):
            items.append(_make_item(headline, stamp=f"2026-04-09T12:{dup:02d}:00Z"))

    start = time.perf_counter()
    deduped = _dedupe_items(items, window_minutes=120, similarity_threshold=0.8)
    elapsed = time.perf_counter() - start

    assert len(items) == 200
    assert len(deduped) == groups
    assert [item["headline"] for item in deduped[:3]] == [
        "Fed announces emergency liquidity action group 0 alpha0 beta0 gamma0 delta0 epsilon0 zeta0 eta0 theta0 iota0 kappa0",
        "Fed announces emergency liquidity action group 1 alpha1 beta1 gamma1 delta1 epsilon1 zeta1 eta1 theta1 iota1 kappa1",
        "Fed announces emergency liquidity action group 2 alpha2 beta2 gamma2 delta2 epsilon2 zeta2 eta2 theta2 iota2 kappa2",
    ]
    assert deduped[0] is items[0]
    assert deduped[1] is items[4]
    assert elapsed < 1.0
