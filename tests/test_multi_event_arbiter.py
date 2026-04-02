import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from multi_event_arbiter import MultiEventArbiter


def _event(headline: str, source: str, symbol: str, vix: float = 22.0):
    return {
        "headline": headline,
        "source": source,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "vix": vix,
        "vix_change_pct": 20,
        "spx_move_pct": 1.8,
        "sector_move_pct": 3.0,
        "entry_price": 100.0,
        "risk_per_share": 2.0,
        "direction": "long",
    }


def test_multi_event_dedup_and_conflict():
    arb = MultiEventArbiter()
    events = [
        _event("Fed action", "https://www.reuters.com/a1", "XLF", 30),
        _event("Fed action", "https://www.reuters.com/a1", "XLF", 30),  # duplicate
        _event("Tariff escalation", "https://www.reuters.com/a2", "XLF", 26),  # symbol conflict
        _event("Macro surprise", "https://www.reuters.com/a3", "XLI", 24),
    ]
    out = arb.run_batch(events)
    assert out["total_input"] == 4
    assert out["dropped_dedup"] >= 1
    assert out["dropped_conflict"] >= 1
    assert out["processed"] <= 3


def test_multi_event_respects_max_open_events():
    arb = MultiEventArbiter()
    # Build more than default max_open_events (5)
    events = []
    for i in range(8):
        events.append(_event(f"Event {i}", f"https://www.reuters.com/{i}", f"SYM{i}", 26))

    out = arb.run_batch(events)
    assert out["total_input"] == 8
    assert out["executed"] <= arb.max_open_events


def test_multi_event_dedup_normalizes_case_and_trailing_slash():
    arb = MultiEventArbiter()
    events = [
        _event("Fed Action", "https://www.REUTERS.com/a1/", "XLF", 30),
        _event("  fed action  ", "https://reuters.com/a1", "XLF", 30),
    ]
    out = arb.run_batch(events)
    assert out["total_input"] == 2
    assert out["processed"] == 1
    assert out["dropped_dedup"] == 1

