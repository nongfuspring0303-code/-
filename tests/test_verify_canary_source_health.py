import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from canary_source_health import CanarySourceHealth
import verify_canary_source_health as verifier


def test_verify_canary_source_health_green_with_fresh_sample(tmp_path, monkeypatch):
    def fake_collect(self):
        fetched_at = datetime.now(timezone.utc)
        published_at = fetched_at - timedelta(seconds=30)
        record = {
            "record_type": "canary_fetch",
            "source_id": "sina_live_feed",
            "source_url": "http://zhibo.sina.com.cn/api/zhibo/feed",
            "primary_source_url": "http://zhibo.sina.com.cn/api/zhibo/feed",
            "source_kind": "json",
            "trace_id": "CANARY-TEST",
            "fetched_at": fetched_at.isoformat().replace("+00:00", "Z"),
            "published_at": published_at.isoformat().replace("+00:00", "Z"),
            "is_canary": True,
            "fetch_status": "success",
            "fetch_latency_ms": 120.0,
            "freshness_lag_sec": 30.0,
            "new_item_count": 1,
            "items": [
                {
                    "source_id": "sina_live_feed",
                    "source_url": "https://finance.sina.cn/7x24/2026-04-10/detail-test.d.html",
                    "headline": "Fed signals policy shift",
                    "published_at": published_at.isoformat().replace("+00:00", "Z"),
                    "trace_id": "CANARY-TEST-1",
                    "is_canary": True,
                    "source_kind": "json",
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
