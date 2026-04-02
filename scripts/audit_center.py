#!/usr/bin/env python3
"""
Audit Center for C3 - Enhanced audit and review system.
- Trace ID based full链路 tracing
- Review report generation
- Rule optimization suggestions
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


def _default_audit_dir() -> str:
    return str(Path(__file__).resolve().parent.parent / "logs")


def _default_config_path() -> str:
    return str(Path(__file__).resolve().parent.parent / "configs" / "edt-modules-config.yaml")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class AuditRecord:
    trace_id: str
    timestamp: str
    module: str
    action: str
    input_data: Dict[str, Any]
    output_data: Dict[str, Any]
    status: str
    errors: List[Dict[str, str]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class AuditCenter:
    def __init__(self, audit_dir: str | None = None, config_path: str | None = None):
        self.audit_dir = Path(audit_dir) if audit_dir else _default_audit_dir()
        self.config_path = Path(config_path) if config_path else _default_config_path()
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self.audit_file = self.audit_dir / "execution_audit.jsonl"
        self.trace_index_file = self.audit_dir / "trace_index.json"

    def record(self, trace_id: str, module: str, action: str, input_data: Dict[str, Any],
               output_data: Dict[str, Any], status: str, errors: List[Dict] = None,
               warnings: List[str] = None, metadata: Dict[str, Any] = None) -> None:
        record = {
            "trace_id": trace_id,
            "timestamp": _now_iso(),
            "module": module,
            "action": action,
            "input": input_data,
            "output": output_data,
            "status": status,
            "errors": errors or [],
            "warnings": warnings or [],
            "metadata": metadata or {},
        }
        with open(self.audit_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._update_trace_index(trace_id, module, status)

    def _update_trace_index(self, trace_id: str, module: str, status: str) -> None:
        index = {}
        if self.trace_index_file.exists():
            try:
                with open(self.trace_index_file, "r", encoding="utf-8") as f:
                    index = json.load(f)
            except Exception:
                index = {}

        if trace_id not in index:
            index[trace_id] = {"modules": [], "status": []}

        index[trace_id]["modules"].append(module)
        index[trace_id]["status"].append(status)
        index[trace_id]["last_updated"] = _now_iso()

        with open(self.trace_index_file, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False)

    def get_trace_records(self, trace_id: str) -> List[Dict[str, Any]]:
        records = []
        if not self.audit_file.exists():
            return records

        with open(self.audit_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    record = json.loads(line.strip())
                    if record.get("trace_id") == trace_id:
                        records.append(record)
                except Exception:
                    continue
        return records

    def generate_review_report(self, trace_id: str) -> Dict[str, Any]:
        records = self.get_trace_records(trace_id)
        if not records:
            return {"error": f"No records found for trace_id={trace_id}"}

        modules_executed = [r.get("module") for r in records]
        statuses = [r.get("status") for r in records]
        errors = [r.get("errors", []) for r in records if r.get("errors")]
        warnings = [r.get("warnings", []) for r in records if r.get("warnings")]

        final_status = "UNKNOWN"
        for r in records:
            if r.get("action") == "final" or r.get("module") == "ExitManager":
                final_status = r.get("output", {}).get("action", "UNKNOWN")
                break

        decision_reason = ""
        if records:
            last_record = records[-1]
            decision_reason = last_record.get("output", {}).get("reason", "")

        return {
            "trace_id": trace_id,
            "generated_at": _now_iso(),
            "modules_executed": modules_executed,
            "execution_summary": {
                "total_steps": len(records),
                "success_count": statuses.count("SUCCESS"),
                "error_count": len(errors),
                "warning_count": len(warnings),
            },
            "final_decision": final_status,
            "decision_reason": decision_reason,
            "errors": errors,
            "warnings": warnings,
            "recommendation": self._generate_recommendation(records),
        }

    def _generate_recommendation(self, records: List[Dict]) -> str:
        error_count = sum(1 for r in records if r.get("errors"))
        warning_count = sum(1 for r in records if r.get("warnings"))

        if error_count > 3:
            return "High error rate detected. Consider reviewing module configurations and timeout settings."
        elif warning_count > 5:
            return "Multiple warnings detected. Review logic and consider adding fallback handlers."
        elif error_count > 0:
            return "Errors detected in execution. Review error details and fix underlying issues."
        else:
            return "Execution completed successfully with no critical issues."

    def list_traces(self, limit: int = 50) -> List[str]:
        if not self.trace_index_file.exists():
            return []

        try:
            with open(self.trace_index_file, "r", encoding="utf-8") as f:
                index = json.load(f)
            traces = list(index.keys())
            traces.sort(reverse=True)
            return traces[:limit]
        except Exception:
            return []

    def query_by_trace_id(self, trace_id: str) -> Dict[str, Any]:
        return {
            "trace_id": trace_id,
            "records": self.get_trace_records(trace_id),
            "review_report": self.generate_review_report(trace_id),
        }


if __name__ == "__main__":
    center = AuditCenter()
    traces = center.list_traces(10)
    print(f"Recent traces: {traces[:5]}")
