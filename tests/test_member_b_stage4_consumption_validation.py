import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from workflow_runner import WorkflowRunner


FIXTURE_PATH = ROOT / "tests" / "fixtures" / "edt_goldens" / "member_b_stage4_consumption_cases.json"
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


def _compute_runtime_metrics(evaluated: list[tuple[dict, dict]]) -> dict:
    total = len(evaluated)
    assert total > 0

    null_like_count = 0
    fallback_used_count = 0
    default_used_count = 0
    manual_review_count = 0
    placeholder_like_count = 0

    for out, gate_record in evaluated:
        if not gate_record["sector_candidates"]:
            null_like_count += 1
        if not gate_record["ticker_candidates"]:
            null_like_count += 1
        if gate_record["a1_score"] is None:
            null_like_count += 1
        if not gate_record["theme_tags"]:
            null_like_count += 1

        reason = str(gate_record.get("final_reason", ""))
        default_used = bool(gate_record.get("market_data_default_used")) or "market_data_default_used" in reason
        fallback_used = bool(gate_record.get("market_data_fallback_used")) or "market_data_fallback_used" in reason
        if default_used:
            default_used_count += 1
        if fallback_used:
            fallback_used_count += 1

        if out["final"]["action"] in {"WATCH", "PENDING_CONFIRM", "BLOCK"}:
            manual_review_count += 1

        # Placeholder/template leakage should remain near-zero in consumer fields.
        inspect_values = []
        for key in ("sector_candidates", "ticker_candidates", "theme_tags"):
            inspect_values.extend(str(v).lower() for v in gate_record.get(key, []))
        if any("placeholder" in value or "template" in value for value in inspect_values):
            placeholder_like_count += 1

    total_fields = total * 4
    return {
        "sample_size": total,
        "null_rate": null_like_count / max(total_fields, 1),
        "fallback_used_ratio": fallback_used_count / total,
        "default_used_ratio": default_used_count / total,
        "manual_review_ratio": manual_review_count / total,
        "placeholder_leakage_ratio": placeholder_like_count / total,
    }


def test_stage4_b_consumption_cases_preserve_summary_fields():
    for case in _load_cases():
        if case.get("reference_only"):
            continue

        out, gate_record = _run_case(case)

        for field in SUMMARY_FIELDS:
            assert field in gate_record, f"missing {field} in {case['case_id']}"

        assert isinstance(gate_record["sector_candidates"], list)
        assert isinstance(gate_record["ticker_candidates"], list)
        assert isinstance(gate_record["theme_tags"], list)
        assert gate_record["a1_score"] is not None

        expected_fragments = case["expected"]["reason_contains"]
        if expected_fragments:
            reason = str(gate_record.get("final_reason", ""))
            for fragment in expected_fragments:
                assert fragment in reason, f"{fragment} not found in {case['case_id']}"
        else:
            assert out["final"]["action"] in {"EXECUTE", "WATCH", "PENDING_CONFIRM", "BLOCK"}


def test_stage4_b_a1_theme_tags_semantics_stable():
    for case in _load_cases():
        if case.get("reference_only"):
            continue
        _, gate_record = _run_case(case)

        assert gate_record["a1_score"] == case["payload"]["a1_score"]
        assert gate_record["theme_tags"] == case["payload"]["theme_tags"]


def test_stage4_b_quality_guardrails():
    evaluated = []
    for case in _load_cases():
        if case.get("reference_only"):
            continue
        out, gate_record = _run_case(case)
        evaluated.append((out, gate_record))

    metrics = _compute_runtime_metrics(evaluated)

    # B-side guardrails for non-regression visibility and consumer quality.
    assert metrics["null_rate"] <= 0.01
    assert metrics["fallback_used_ratio"] <= 0.5
    assert metrics["default_used_ratio"] <= 0.5
    assert metrics["manual_review_ratio"] <= 1.0
    assert metrics["placeholder_leakage_ratio"] <= 0.01


def test_stage4_b_runtime_metrics_snapshot():
    evaluated = []
    for case in _load_cases():
        if case.get("reference_only"):
            continue
        out, gate_record = _run_case(case)
        evaluated.append((out, gate_record))

    metrics = _compute_runtime_metrics(evaluated)
    # Snapshot values from current stable Stage4 implementation over B fixture set.
    assert metrics["sample_size"] == 6
    assert metrics["null_rate"] == 0.0
    assert metrics["fallback_used_ratio"] == 2 / 6
    assert metrics["default_used_ratio"] == 0.0
    assert metrics["manual_review_ratio"] == 2 / 6
    assert metrics["placeholder_leakage_ratio"] == 0.0


def test_stage4_b_replay_idempotent_path_reference():
    case = next(c for c in _load_cases() if c["case_id"] == "B-S4-006")

    with tempfile.TemporaryDirectory() as tmpdir:
        logs_dir = Path(tmpdir) / "logs"
        runner = WorkflowRunner(
            audit_dir=str(logs_dir),
            request_store_path=str(Path(tmpdir) / "seen_request_ids.txt"),
        )
        first = runner.run(case["payload"])
        second = runner.run(case["payload"])

        assert first["final"]["action"] in {"EXECUTE", "WATCH", "PENDING_CONFIRM", "BLOCK"}
        assert second["final"]["action"] == "DUPLICATE_IGNORED"
