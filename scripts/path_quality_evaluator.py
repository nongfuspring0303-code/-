#!/usr/bin/env python3
"""
PathQualityEvaluator (PR113)

Analysis-layer path quality evaluation engine.
Computes 7 accuracy dimensions from upstream analysis outputs and produces
a composite quality score with a letter grade.

Hard boundary:
- Output is for analysis review only.
- Must not be consumed by Gate/final_action/execution path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from edt_module_base import EDTModule, ModuleInput, ModuleOutput, ModuleStatus


class PathQualityEvaluator(EDTModule):
    """Evaluate quality of the analysis pipeline's predictions."""

    @staticmethod
    def _as_float(value: Any, name: str) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            raise ValueError(f"path_quality_eval policy invalid numeric value for {name}")

    def __init__(self, config_path: Optional[str] = None):
        if not config_path:
            default_policy = Path(__file__).resolve().parent.parent / "configs" / "path_quality_eval_policy.yaml"
            if not default_policy.exists():
                raise FileNotFoundError(f"path_quality_eval policy missing: {default_policy}")
            config_path = str(default_policy)
        else:
            p = Path(config_path)
            if not p.exists():
                raise FileNotFoundError(f"path_quality_eval policy missing: {p}")
        super().__init__("PathQualityEvaluator", "1.0.0", config_path)
        self._load_policy()

    def _load_policy(self) -> None:
        policy = self.config if isinstance(self.config, dict) else {}

        # --- dimensions ---
        dimensions = policy.get("dimensions")
        if not isinstance(dimensions, list) or len(dimensions) == 0:
            raise ValueError("path_quality_eval policy missing dimensions list")

        required_dims = {
            "path_accuracy",
            "validation_accuracy",
            "direction_relative_accuracy",
            "direction_absolute_accuracy",
            "dominant_driver_accuracy",
            "expectation_gap_accuracy",
            "execution_decision_quality",
        }
        actual_dims = set(dimensions)
        missing_dims = sorted(required_dims - actual_dims)
        if missing_dims:
            raise ValueError(f"path_quality_eval policy missing dimensions: {','.join(missing_dims)}")

        # --- weights ---
        weights = policy.get("weights")
        if not isinstance(weights, dict):
            raise ValueError("path_quality_eval policy missing weights")
        missing_weights = sorted(required_dims - set(weights.keys()))
        if missing_weights:
            raise ValueError(f"path_quality_eval policy missing weight keys: {','.join(missing_weights)}")

        validated_weights: Dict[str, float] = {}
        for dim in required_dims:
            w = self._as_float(weights[dim], f"weights.{dim}")
            if not (0.0 <= w <= 1.0):
                raise ValueError(f"path_quality_eval policy weight {dim} out of range [0,1]")
            validated_weights[dim] = w

        weight_sum = sum(validated_weights.values())
        if abs(weight_sum - 1.0) > 0.001:
            raise ValueError(f"path_quality_eval policy weights must sum to 1.0, got {weight_sum}")

        # --- status_scores ---
        status_scores = policy.get("status_scores")
        if not isinstance(status_scores, dict):
            raise ValueError("path_quality_eval policy missing status_scores")
        required_statuses = {"confirmed", "partial", "missing", "not_confirmed", "conflicted"}
        missing_statuses = sorted(required_statuses - set(status_scores.keys()))
        if missing_statuses:
            raise ValueError(f"path_quality_eval policy missing status_scores keys: {','.join(missing_statuses)}")

        validated_status_scores: Dict[str, float] = {}
        for status in required_statuses:
            s = self._as_float(status_scores[status], f"status_scores.{status}")
            if not (0.0 <= s <= 1.0):
                raise ValueError(f"path_quality_eval policy status_score {status} out of range [0,1]")
            validated_status_scores[status] = s

        # --- absolute_direction_scores ---
        abs_dir_scores = policy.get("absolute_direction_scores")
        if not isinstance(abs_dir_scores, dict):
            raise ValueError("path_quality_eval policy missing absolute_direction_scores")
        required_dirs = {"benefit", "hurt", "mixed", "uncertain", "watch"}
        missing_dirs = sorted(required_dirs - set(abs_dir_scores.keys()))
        if missing_dirs:
            raise ValueError(f"path_quality_eval policy missing absolute_direction_scores keys: {','.join(missing_dirs)}")

        validated_dir_scores: Dict[str, float] = {}
        for d in required_dirs:
            v = self._as_float(abs_dir_scores[d], f"absolute_direction_scores.{d}")
            if not (0.0 <= v <= 1.0):
                raise ValueError(f"path_quality_eval policy absolute_direction_score {d} out of range [0,1]")
            validated_dir_scores[d] = v

        # --- grade_bands ---
        grade_bands = policy.get("grade_bands")
        if not isinstance(grade_bands, dict):
            raise ValueError("path_quality_eval policy missing grade_bands")
        required_grades = {"excellent", "good", "acceptable", "poor", "failed"}
        missing_grades = sorted(required_grades - set(grade_bands.keys()))
        if missing_grades:
            raise ValueError(f"path_quality_eval policy missing grade_bands: {','.join(missing_grades)}")

        validated_bands: Dict[str, Dict[str, Any]] = {}
        for grade_key in required_grades:
            band = grade_bands[grade_key]
            if not isinstance(band, dict):
                raise ValueError(f"path_quality_eval policy grade_band {grade_key} must be an object")
            b_min = self._as_float(band.get("min"), f"grade_bands.{grade_key}.min")
            b_max = self._as_float(band.get("max"), f"grade_bands.{grade_key}.max")
            label = band.get("label")
            if not isinstance(label, str) or not label.strip():
                raise ValueError(f"path_quality_eval policy grade_band {grade_key} missing label")
            if not (0.0 <= b_min <= 1.0 and 0.0 <= b_max <= 1.0):
                raise ValueError(f"path_quality_eval policy grade_band {grade_key} range invalid")
            if b_min > b_max:
                raise ValueError(f"path_quality_eval policy grade_band {grade_key} min>max")
            validated_bands[grade_key] = {"min": b_min, "max": b_max, "label": label}

        self.weights = validated_weights
        self.status_scores = validated_status_scores
        self.direction_scores = validated_dir_scores
        self.grade_bands = validated_bands

    # ---- Input helpers (Fail-Fast, no silent fallback) ----

    @staticmethod
    def _required_float(raw: Dict[str, Any], key: str) -> tuple[float | None, str | None]:
        value = raw.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            return None, f"missing_critical_input_{key}"
        try:
            f = float(value)
            if not (0.0 <= f <= 1.0):
                return None, f"out_of_range_{key}"
            return f, None
        except (TypeError, ValueError):
            return None, f"invalid_critical_input_{key}"

    @staticmethod
    def _required_str(raw: Dict[str, Any], key: str, allowed: set[str]) -> tuple[str | None, str | None]:
        value = raw.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            return None, f"missing_critical_input_{key}"
        s = str(value).strip()
        if s not in allowed:
            return None, f"invalid_enum_{key}"
        return s, None

    def _compute_validation_accuracy(self, checks: Any) -> tuple[float | None, str | None]:
        """Compute validation_accuracy from market_validation checks array.

        Uses the blueprint formula: sum(weight * status_score) / sum(weight)
        """
        if not isinstance(checks, list) or len(checks) == 0:
            return None, "missing_critical_input_validation_checks"

        total_weighted_score = 0.0
        total_weight = 0.0
        for i, check in enumerate(checks):
            if not isinstance(check, dict):
                return None, f"invalid_validation_check_at_index_{i}"
            status = check.get("status")
            if status not in self.status_scores:
                return None, f"invalid_validation_check_status_at_index_{i}"
            raw_weight = check.get("weight")
            if raw_weight is None:
                return None, f"missing_validation_check_weight_at_index_{i}"
            try:
                weight = float(raw_weight)
            except (TypeError, ValueError):
                return None, f"invalid_validation_check_weight_at_index_{i}"
            if weight <= 0:
                return None, f"non_positive_validation_check_weight_at_index_{i}"
            total_weighted_score += weight * self.status_scores[status]
            total_weight += weight

        if total_weight <= 0:
            return None, "validation_checks_zero_total_weight"
        return round(total_weighted_score / total_weight, 4), None

    def _determine_grade(self, score: float) -> str:
        """Determine quality grade from composite score using grade_bands."""
        # Check from highest to lowest
        for band_key in ["excellent", "good", "acceptable", "poor"]:
            band = self.grade_bands[band_key]
            if score >= band["min"]:
                return str(band["label"])
        return str(self.grade_bands["failed"]["label"])

    def execute(self, input_data: ModuleInput) -> ModuleOutput:
        raw = input_data.raw_data

        # --- 1. path_accuracy (from path_confidence) ---
        path_accuracy, err = self._required_float(raw, "path_confidence")
        if err:
            return ModuleOutput(
                status=ModuleStatus.FAILED, data={},
                errors=[{"code": "MISSING_CRITICAL_INPUT_PATH_CONFIDENCE", "message": err}],
            )

        # --- 2. validation_accuracy (from validation_checks array) ---
        validation_accuracy, err = self._compute_validation_accuracy(raw.get("validation_checks"))
        if err:
            return ModuleOutput(
                status=ModuleStatus.FAILED, data={},
                errors=[{"code": "MISSING_CRITICAL_INPUT_VALIDATION_CHECKS", "message": err}],
            )

        # --- 3. direction_relative_accuracy (from relative_direction_score) ---
        dir_rel, err = self._required_float(raw, "relative_direction_score")
        if err:
            return ModuleOutput(
                status=ModuleStatus.FAILED, data={},
                errors=[{"code": "MISSING_CRITICAL_INPUT_RELATIVE_DIRECTION", "message": err}],
            )

        # --- 4. direction_absolute_accuracy (from absolute_direction enum) ---
        abs_dir, abs_err = self._required_str(
            raw, "absolute_direction", set(self.direction_scores.keys())
        )
        if abs_err:
            return ModuleOutput(
                status=ModuleStatus.FAILED, data={},
                errors=[{"code": "MISSING_CRITICAL_INPUT_ABSOLUTE_DIRECTION", "message": abs_err}],
            )
        dir_abs = self.direction_scores[abs_dir]

        # --- 5. dominant_driver_accuracy (from driver_confidence) ---
        driver_acc, err = self._required_float(raw, "driver_confidence")
        if err:
            return ModuleOutput(
                status=ModuleStatus.FAILED, data={},
                errors=[{"code": "MISSING_CRITICAL_INPUT_DRIVER_CONFIDENCE", "message": err}],
            )

        # --- 6. expectation_gap_accuracy (from gap_score, normalized 0-1) ---
        gap_acc, err = self._required_float(raw, "gap_score")
        if err:
            return ModuleOutput(
                status=ModuleStatus.FAILED, data={},
                errors=[{"code": "MISSING_CRITICAL_INPUT_GAP_SCORE", "message": err}],
            )

        # --- 7. execution_decision_quality (from execution_confidence) ---
        exec_quality, err = self._required_float(raw, "execution_confidence")
        if err:
            return ModuleOutput(
                status=ModuleStatus.FAILED, data={},
                errors=[{"code": "MISSING_CRITICAL_INPUT_EXECUTION_CONFIDENCE", "message": err}],
            )

        # --- Composite score ---
        composite = round(
            self.weights["path_accuracy"] * path_accuracy
            + self.weights["validation_accuracy"] * validation_accuracy
            + self.weights["direction_relative_accuracy"] * dir_rel
            + self.weights["direction_absolute_accuracy"] * dir_abs
            + self.weights["dominant_driver_accuracy"] * driver_acc
            + self.weights["expectation_gap_accuracy"] * gap_acc
            + self.weights["execution_decision_quality"] * exec_quality,
            4,
        )

        grade = self._determine_grade(composite)

        data = {
            "path_accuracy": round(path_accuracy, 4),
            "validation_accuracy": round(validation_accuracy, 4),
            "direction_relative_accuracy": round(dir_rel, 4),
            "direction_absolute_accuracy": round(dir_abs, 4),
            "dominant_driver_accuracy": round(driver_acc, 4),
            "expectation_gap_accuracy": round(gap_acc, 4),
            "execution_decision_quality": round(exec_quality, 4),
            "composite_score": composite,
            "grade": grade,
        }
        return ModuleOutput(status=ModuleStatus.SUCCESS, data=data)
