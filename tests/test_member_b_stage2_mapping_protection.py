import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from workflow_runner import WorkflowRunner


FIXTURE_PATH = ROOT / "tests" / "fixtures" / "edt_goldens" / "member_b_stage2_non_regression_cases.json"
SUMMARY_FIELDS = [
    "semantic_event_type",
    "sector_candidates",
    "ticker_candidates",
    "a1_score",
    "theme_tags",
    "tradeable",
    "opportunity_count",
]


def _load_cases() -> list[dict]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return payload["cases"]


def _run_case(case: dict) -> tuple[dict, dict]:
    with tempfile.TemporaryDirectory() as tmpdir:
        logs_dir = Path(tmpdir) / "logs"
        runner = WorkflowRunner(
            audit_dir=str(logs_dir),
            request_store_path=str(Path(tmpdir) / "seen_request_ids.txt"),
        )
        out = runner.run(case["payload"])

        gate_record = json.loads((logs_dir / "decision_gate.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1])
        return out, gate_record


def test_member_b_stage2_mapping_protection_cases():
    for case in _load_cases():
        out, gate_record = _run_case(case)
        expected = case["expected"]
        final = out["final"]

        for field in SUMMARY_FIELDS:
            assert field in gate_record, f"missing {field} in {case['case_id']}"

        assert isinstance(gate_record["semantic_event_type"], str)
        assert isinstance(gate_record["sector_candidates"], list)
        assert isinstance(gate_record["ticker_candidates"], list)
        assert gate_record["a1_score"] is not None
        assert isinstance(gate_record["theme_tags"], list)
        assert isinstance(gate_record["tradeable"], bool)
        assert isinstance(gate_record["opportunity_count"], int)

        if case["case_id"] == "B-STAGE2-001":
            # Mapping-protection suite should not bind to execution strategy.
            # We only assert that complete data path is not rejected by output gate.
            output_gate = gate_record.get("output_gate", {})
            assert output_gate.get("blocked") is False
            assert "gate_contract_missing_" not in gate_record["final_reason"]
            assert "market_data_stale" not in gate_record["final_reason"]
            assert "market_data_default_used" not in gate_record["final_reason"]
            assert "market_data_fallback_used" not in gate_record["final_reason"]
            continue

        assert final["action"] == expected["final_action"]
        assert final["action"] != "EXECUTE"
        reason = gate_record["final_reason"]
        for fragment in expected["reason_contains"]:
            assert fragment in reason


def test_member_b_stage2_target_tracking_not_invented():
    case = _load_cases()[2]
    _, gate_record = _run_case(case)

    assert "target_tracking" not in gate_record
    assert gate_record["a1_score"] is not None
