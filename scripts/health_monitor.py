#!/usr/bin/env python3
"""
C-7 系统健康监控。
收集 A/B 模块超时与降级信号，并给出实时健康状态。
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
import json


@dataclass
class HealthSignal:
    module: str
    signal_type: str
    severity: str
    message: str
    trace_id: str
    ts: str


class HealthMonitor:
    def __init__(self, base_dir: str | None = None):
        root = Path(base_dir) if base_dir else Path(__file__).resolve().parent.parent
        self.log_file = root / "logs" / "health_signals.jsonl"
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def report(
        self,
        *,
        module: str,
        signal_type: str,
        severity: str,
        message: str,
        trace_id: str,
    ) -> dict[str, Any]:
        signal = HealthSignal(
            module=module,
            signal_type=signal_type,
            severity=severity,
            message=message,
            trace_id=trace_id,
            ts=datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        )
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(signal), ensure_ascii=False) + "\n")
        return {"status": "ok", "signal": asdict(signal)}

    def _read_recent(self, minutes: int = 30) -> list[dict[str, Any]]:
        if not self.log_file.exists():
            return []
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        rows: list[dict[str, Any]] = []
        with open(self.log_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    ts = datetime.fromisoformat(row.get("ts", "").replace("Z", ""))
                except Exception:
                    continue
                if ts >= cutoff:
                    rows.append(row)
        return rows

    def status(self, window_minutes: int = 30) -> dict[str, Any]:
        rows = self._read_recent(window_minutes)
        modules = {"A": [], "B": [], "C": []}
        for row in rows:
            m = row.get("module")
            if m in modules:
                modules[m].append(row)

        def score(entries: list[dict[str, Any]]) -> int:
            penalty = 0
            for e in entries:
                sev = e.get("severity", "low")
                if sev == "high":
                    penalty += 30
                elif sev == "medium":
                    penalty += 15
                else:
                    penalty += 5
            return max(0, 100 - penalty)

        summary = {}
        for name, entries in modules.items():
            s = score(entries)
            level = "healthy" if s >= 80 else "warning" if s >= 60 else "critical"
            summary[name] = {
                "score": s,
                "level": level,
                "event_count": len(entries),
                "timeouts": sum(1 for e in entries if e.get("signal_type") == "timeout"),
                "degrades": sum(1 for e in entries if e.get("signal_type") == "degrade"),
            }

        return {
            "schema_version": "v1.0",
            "window_minutes": window_minutes,
            "generated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "modules": summary,
            "recent_signals": rows[-50:],
        }


if __name__ == "__main__":
    monitor = HealthMonitor()
    print(json.dumps(monitor.status(), ensure_ascii=False, indent=2))
