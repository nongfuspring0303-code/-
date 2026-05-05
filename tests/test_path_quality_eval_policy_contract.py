from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from path_quality_evaluator import PathQualityEvaluator


def _load_policy() -> dict:
    return yaml.safe_load((ROOT / "configs" / "path_quality_eval_policy.yaml").read_text(encoding="utf-8"))


def _load_schema() -> dict:
    return json.loads((ROOT / "schemas" / "path_quality_eval.schema.json").read_text(encoding="utf-8"))


def test_path_quality_policy_versions_present() -> None:
    policy = _load_policy()
    assert policy.get("schema_version") == "stage6.path_quality_eval_policy.v1"
    assert policy.get("mode") == "analysis_only"
    assert policy.get("guardrails", {}).get("analysis_only") is True
    assert policy.get("guardrails", {}).get("allow_runtime_consumer") is False


def test_path_quality_schema_grade_enums_align_with_policy() -> None:
    policy = _load_policy()
    schema = _load_schema()
    policy_labels = sorted([b["label"] for b in policy["grade_bands"].values()])
    schema_grades = sorted(schema["properties"]["grade"]["enum"])
    assert policy_labels == schema_grades


def test_path_quality_policy_weights_sum_to_one() -> None:
    policy = _load_policy()
    weights = policy["weights"]
    total = sum(float(v) for v in weights.values())
    assert abs(total - 1.0) < 0.001


def test_path_quality_policy_status_scores_cover_all_statuses() -> None:
    policy = _load_policy()
    required = {"confirmed", "partial", "missing", "not_confirmed", "conflicted"}
    actual = set(policy["status_scores"].keys())
    assert required <= actual


def test_path_quality_policy_direction_scores_cover_all_directions() -> None:
    policy = _load_policy()
    required = {"benefit", "hurt", "mixed", "uncertain", "watch"}
    actual = set(policy["absolute_direction_scores"].keys())
    assert required <= actual


def test_path_quality_weight_change_affects_runtime(tmp_path: Path) -> None:
    policy = _load_policy()
    # Shift all weight to path_accuracy
    policy["weights"] = {
        "path_accuracy": 1.0,
        "validation_accuracy": 0.0,
        "direction_relative_accuracy": 0.0,
        "direction_absolute_accuracy": 0.0,
        "dominant_driver_accuracy": 0.0,
        "expectation_gap_accuracy": 0.0,
        "execution_decision_quality": 0.0,
    }
    policy_path = tmp_path / "path_quality_eval_policy.yaml"
    policy_path.write_text(yaml.safe_dump(policy, allow_unicode=True, sort_keys=False), encoding="utf-8")

    builder = PathQualityEvaluator(config_path=str(policy_path))
    out = builder.run({
        "path_confidence": 0.95,
        "validation_checks": [{"asset": "x", "expected": "up", "observed": "up", "status": "confirmed", "weight": 1.0}],
        "relative_direction_score": 0.10,
        "absolute_direction": "uncertain",
        "driver_confidence": 0.10,
        "gap_score": 0.10,
        "execution_confidence": 0.10,
    })
    assert out.status.value == "success"
    # With 100% weight on path_accuracy=0.95, composite should be ~0.95
    assert out.data["composite_score"] >= 0.90


def test_path_quality_policy_missing_file_fails_fast(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yaml"
    with pytest.raises(FileNotFoundError):
        PathQualityEvaluator(config_path=str(missing))


def test_path_quality_policy_invalid_weight_value_fails(tmp_path: Path) -> None:
    policy = _load_policy()
    policy["weights"]["path_accuracy"] = "bad-number"
    policy_path = tmp_path / "bad.yaml"
    policy_path.write_text(yaml.safe_dump(policy, allow_unicode=True, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValueError):
        PathQualityEvaluator(config_path=str(policy_path))


def test_path_quality_policy_weights_not_summing_to_one_fails(tmp_path: Path) -> None:
    policy = _load_policy()
    policy["weights"]["path_accuracy"] = 0.99  # will make sum > 1
    policy_path = tmp_path / "bad_sum.yaml"
    policy_path.write_text(yaml.safe_dump(policy, allow_unicode=True, sort_keys=False), encoding="utf-8")
    with pytest.raises(ValueError):
        PathQualityEvaluator(config_path=str(policy_path))
