import tempfile
from pathlib import Path

from scripts.health_monitor import HealthMonitor


def test_report_and_status_summary():
    with tempfile.TemporaryDirectory() as tmp:
        monitor = HealthMonitor(base_dir=tmp)

        monitor.report(
            module="A",
            signal_type="timeout",
            severity="medium",
            message="A 模块处理超时",
            trace_id="evt_1",
        )
        monitor.report(
            module="B",
            signal_type="degrade",
            severity="high",
            message="B 模块触发 G7 降级",
            trace_id="evt_2",
        )

        data = monitor.status(window_minutes=60)
        assert data["modules"]["A"]["timeouts"] == 1
        assert data["modules"]["B"]["degrades"] == 1
        assert data["modules"]["B"]["level"] in {"warning", "critical"}
        assert len(data["recent_signals"]) == 2
