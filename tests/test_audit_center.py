import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from audit_center import AuditCenter


def test_audit_record_and_query(tmp_path):
    center = AuditCenter(audit_dir=str(tmp_path))
    center.record(
        trace_id="TRC-1",
        module="LifecycleManager",
        action="transition",
        input_data={"a": 1},
        output_data={"state": "Active"},
        status="SUCCESS",
    )

    result = center.query_by_trace_id("TRC-1")
    assert result["trace_id"] == "TRC-1"
    assert len(result["records"]) == 1
    assert result["records"][0]["module"] == "LifecycleManager"


def test_audit_review_report_contains_summary(tmp_path):
    center = AuditCenter(audit_dir=str(tmp_path))
    center.record("TRC-2", "A", "step1", {}, {"ok": 1}, "SUCCESS")
    center.record("TRC-2", "B", "step2", {}, {"ok": 2}, "FAILED", errors=[{"code": "E", "message": "x"}])

    report = center.generate_review_report("TRC-2")
    assert report["trace_id"] == "TRC-2"
    assert report["execution_summary"]["total_steps"] == 2
    assert report["execution_summary"]["success_count"] == 1
    assert report["execution_summary"]["error_count"] == 1
