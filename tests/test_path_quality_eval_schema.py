from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from path_quality_evaluator import PathQualityEvaluator


def _load_schema() -> dict:
    return json.loads((ROOT / "schemas" / "path_quality_eval.schema.json").read_text(encoding="utf-8"))


def _valid_input() -> dict:
    return {
        "path_confidence": 0.78,
        "validation_checks": [
            {"asset": "crude_oil", "expected": "up", "observed": "up", "status": "confirmed", "weight": 0.40},
            {"asset": "vix", "expected": "up", "observed": "flat", "status": "not_confirmed", "weight": 0.25},
            {"asset": "10y_yield", "expected": "up", "observed": "up", "status": "confirmed", "weight": 0.35},
        ],
        "relative_direction_score": 0.65,
        "absolute_direction": "benefit",
        "driver_confidence": 0.70,
        "gap_score": 0.55,
        "execution_confidence": 0.45,
    }


def test_path_quality_schema_validates_evaluator_output() -> None:
    schema = _load_schema()
    out = PathQualityEvaluator().run(_valid_input())
    assert out.status.value == "success"
    jsonschema.validate(out.data, schema)
    assert set(out.data.keys()) == {
        "path_accuracy",
        "validation_accuracy",
        "direction_relative_accuracy",
        "direction_absolute_accuracy",
        "dominant_driver_accuracy",
        "expectation_gap_accuracy",
        "execution_decision_quality",
        "composite_score",
        "grade",
    }


def test_path_quality_schema_rejects_invalid_grade() -> None:
    schema = _load_schema()
    bad = {
        "path_accuracy": 0.5,
        "validation_accuracy": 0.5,
        "direction_relative_accuracy": 0.5,
        "direction_absolute_accuracy": 0.5,
        "dominant_driver_accuracy": 0.5,
        "expectation_gap_accuracy": 0.5,
        "execution_decision_quality": 0.5,
        "composite_score": 0.5,
        "grade": "INVALID_GRADE",
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_path_quality_missing_path_confidence_fails() -> None:
    inp = _valid_input()
    del inp["path_confidence"]
    out = PathQualityEvaluator().run(inp)
    assert out.status.value == "failed"
    assert out.errors and out.errors[0]["code"] == "MISSING_CRITICAL_INPUT_PATH_CONFIDENCE"


def test_path_quality_missing_validation_checks_fails() -> None:
    inp = _valid_input()
    del inp["validation_checks"]
    out = PathQualityEvaluator().run(inp)
    assert out.status.value == "failed"
    assert out.errors and out.errors[0]["code"] == "MISSING_CRITICAL_INPUT_VALIDATION_CHECKS"


def test_path_quality_missing_gap_score_fails() -> None:
    inp = _valid_input()
    del inp["gap_score"]
    out = PathQualityEvaluator().run(inp)
    assert out.status.value == "failed"
    assert out.errors and out.errors[0]["code"] == "MISSING_CRITICAL_INPUT_GAP_SCORE"


def test_path_quality_missing_execution_confidence_fails() -> None:
    inp = _valid_input()
    del inp["execution_confidence"]
    out = PathQualityEvaluator().run(inp)
    assert out.status.value == "failed"
    assert out.errors and out.errors[0]["code"] == "MISSING_CRITICAL_INPUT_EXECUTION_CONFIDENCE"


def test_path_quality_missing_driver_confidence_fails() -> None:
    inp = _valid_input()
    del inp["driver_confidence"]
    out = PathQualityEvaluator().run(inp)
    assert out.status.value == "failed"
    assert out.errors and out.errors[0]["code"] == "MISSING_CRITICAL_INPUT_DRIVER_CONFIDENCE"


def test_path_quality_missing_absolute_direction_fails() -> None:
    inp = _valid_input()
    del inp["absolute_direction"]
    out = PathQualityEvaluator().run(inp)
    assert out.status.value == "failed"
    assert out.errors and out.errors[0]["code"] == "MISSING_CRITICAL_INPUT_ABSOLUTE_DIRECTION"


def test_path_quality_invalid_absolute_direction_enum_fails() -> None:
    inp = _valid_input()
    inp["absolute_direction"] = "bogus_direction"
    out = PathQualityEvaluator().run(inp)
    assert out.status.value == "failed"
    assert "ABSOLUTE_DIRECTION" in out.errors[0]["code"]


def test_path_quality_missing_relative_direction_fails() -> None:
    inp = _valid_input()
    del inp["relative_direction_score"]
    out = PathQualityEvaluator().run(inp)
    assert out.status.value == "failed"
    assert out.errors and out.errors[0]["code"] == "MISSING_CRITICAL_INPUT_RELATIVE_DIRECTION"


def test_path_quality_boundary_excellent_grade() -> None:
    inp = _valid_input()
    inp["path_confidence"] = 0.95
    inp["relative_direction_score"] = 0.90
    inp["driver_confidence"] = 0.85
    inp["gap_score"] = 0.90
    inp["execution_confidence"] = 0.80
    inp["absolute_direction"] = "benefit"
    inp["validation_checks"] = [
        {"asset": "oil", "expected": "up", "observed": "up", "status": "confirmed", "weight": 1.0},
    ]
    out = PathQualityEvaluator().run(inp)
    assert out.status.value == "success"
    assert out.data["grade"] == "Excellent"
    assert out.data["composite_score"] >= 0.80


def test_path_quality_boundary_failed_grade() -> None:
    inp = _valid_input()
    inp["path_confidence"] = 0.10
    inp["relative_direction_score"] = 0.05
    inp["driver_confidence"] = 0.10
    inp["gap_score"] = 0.05
    inp["execution_confidence"] = 0.10
    inp["absolute_direction"] = "uncertain"
    inp["validation_checks"] = [
        {"asset": "oil", "expected": "up", "observed": "down", "status": "conflicted", "weight": 1.0},
    ]
    out = PathQualityEvaluator().run(inp)
    assert out.status.value == "success"
    assert out.data["grade"] == "Failed"
    assert out.data["composite_score"] < 0.20


def test_path_quality_out_of_range_score_fails() -> None:
    inp = _valid_input()
    inp["path_confidence"] = 1.5  # out of [0,1]
    out = PathQualityEvaluator().run(inp)
    assert out.status.value == "failed"


def test_path_quality_validation_check_invalid_status_fails() -> None:
    inp = _valid_input()
    inp["validation_checks"] = [
        {"asset": "oil", "expected": "up", "observed": "up", "status": "BOGUS", "weight": 0.5},
    ]
    out = PathQualityEvaluator().run(inp)
    assert out.status.value == "failed"
