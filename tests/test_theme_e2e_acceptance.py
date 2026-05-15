import json
from pathlib import Path

from theme_gate_policy import apply_theme_gate_constraints, validate_theme_contract
from verify_theme_replay import verify_replay_consistency

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "theme_acceptance"


def _load_replay_case(name: str) -> list[dict]:
    path = FIXTURE_DIR / f"{name}.jsonl"
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def _summarize_replay(records: list[dict]) -> dict[str, object]:
    report = verify_replay_consistency(records)
    consistency_break_reason = ""
    if not report["replay_consistency"]:
        if report["inconsistent_keys"]:
            consistency_break_reason = "inconsistent_keys:" + ",".join(report["inconsistent_keys"])
        elif report["contract_errors"]:
            consistency_break_reason = "contract_errors:" + ",".join(report["contract_errors"])
        else:
            consistency_break_reason = "unknown_replay_break"
    return {
        "report": report,
        "consistency_break_reason": consistency_break_reason,
    }


def test_theme_acceptance_positive_replay_passes_real_path():
    records = _load_replay_case("positive_replay")
    summary = _summarize_replay(records)

    assert summary["report"]["replay_consistency"] is True
    assert summary["report"]["total_records"] == 2
    assert summary["report"]["unique_keys"] == 1
    assert summary["report"]["inconsistent_keys"] == []
    assert summary["report"]["contract_errors"] == []
    assert summary["consistency_break_reason"] == ""

    resolved_output = apply_theme_gate_constraints(records[0]["output_snapshot"])
    assert resolved_output["contract_name"] == "theme_catalyst_engine"
    assert resolved_output["contract_version"] == "v1.0"
    assert resolved_output["producer_module"] == "theme_engine"
    assert resolved_output["route_to_theme_engine"] is True
    assert resolved_output["primary_theme"] == "Quantum Computing"
    assert resolved_output["basket_confirmation"] == "valid"
    assert resolved_output["trade_grade"] == "B"
    assert validate_theme_contract(resolved_output) == []


def test_theme_acceptance_inconsistent_replay_requires_break_reason():
    records = _load_replay_case("inconsistent_replay")
    summary = _summarize_replay(records)

    assert summary["report"]["replay_consistency"] is False
    assert summary["report"]["total_records"] == 2
    assert summary["report"]["unique_keys"] == 1
    assert summary["report"]["inconsistent_keys"] == ["evt-theme-inconsistent|v1|T0"]
    assert summary["consistency_break_reason"]
    assert summary["consistency_break_reason"].startswith("inconsistent_keys:")

    first_output = apply_theme_gate_constraints(records[0]["output_snapshot"])
    second_output = apply_theme_gate_constraints(records[1]["output_snapshot"])
    assert first_output["trade_grade"] == "B"
    assert second_output["trade_grade"] == "C"
    assert validate_theme_contract(first_output) == []
    assert validate_theme_contract(second_output) == []


def test_theme_acceptance_does_not_use_simulated_outputs():
    assert "_simulated_outputs" not in globals()
    assert (FIXTURE_DIR / "positive_replay.jsonl").is_file()
    assert (FIXTURE_DIR / "inconsistent_replay.jsonl").is_file()
