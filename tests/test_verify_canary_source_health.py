import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from canary_source_health import CanarySourceHealth
import verify_canary_source_health as verifier


def test_verify_canary_source_health_green_with_fresh_sample(tmp_path, monkeypatch):
    def fake_collect(self):
        record = {
            "record_type": "canary_fetch",
            "source_id": "reuters_rss_top_news",
            "source_url": "https://feeds.reuters.com/reuters/topNews",
            "source_kind": "rss",
            "trace_id": "CANARY-TEST",
            "fetched_at": "2026-04-10T02:00:00Z",
            "published_at": "2026-04-10T01:59:30Z",
            "is_canary": True,
            "fetch_status": "success",
            "fetch_latency_ms": 120.0,
            "freshness_lag_sec": 30.0,
            "new_item_count": 1,
            "items": [
                {
                    "source_id": "reuters_rss_top_news",
                    "source_url": "https://www.reuters.com/world/us/fed-policy-shift",
                    "headline": "Fed signals policy shift",
                    "published_at": "2026-04-10T01:59:30Z",
                    "trace_id": "CANARY-TEST-1",
                    "is_canary": True,
                    "source_kind": "rss",
                }
            ],
        }
        with open(self.health_log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.write_summary()
        return record

    monkeypatch.setattr(CanarySourceHealth, "collect_once", fake_collect)
    monkeypatch.setattr(sys, "argv", ["verify_canary_source_health.py", "--refresh", "--audit-dir", str(tmp_path)])
    assert verifier.main() == 0


def test_verify_canary_source_health_fails_without_samples(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["verify_canary_source_health.py", "--audit-dir", str(tmp_path)])
    assert verifier.main() == 1

