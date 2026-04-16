#!/usr/bin/env python3
"""Theme gate policy helpers for member B.

This module keeps theme-side gate rules out of runner core logic.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping

import yaml


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CODEBOOK_PATH = ROOT / "configs" / "theme_error_codebook.yaml"
REQUIRED_CONTRACT_FIELDS = ("contract_name", "contract_version", "producer_module", "safe_to_consume")
REQUIRED_ERROR_CODES = (
    "CONFIG_MISSING",
    "CONFIG_INVALID",
    "THEME_MAPPING_FAILED",
    "BASKET_EMPTY",
    "MARKET_DATA_MISSING",
    "VALIDATION_SKIPPED",
    "STATE_ENGINE_INSUFFICIENT_DATA",
    "DOWNSTREAM_OUTPUT_DEGRADED",
)
GATE_DEGRADED_ACTION = "DEGRADED"
GATE_BLOCK_ACTION = "BLOCK"


def load_theme_error_codebook(path: str | Path | None = None) -> dict[str, Any]:
    codebook_path = Path(path) if path else DEFAULT_CODEBOOK_PATH
    payload = yaml.safe_load(codebook_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise TypeError(f"Invalid codebook payload in {codebook_path}")
    return payload


def validate_theme_error_codebook(codebook: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    codes = codebook.get("codes", {}) if isinstance(codebook, Mapping) else {}
    if not isinstance(codes, Mapping):
        return ["codebook.codes must be a mapping"]

    missing_codes = [code for code in REQUIRED_ERROR_CODES if code not in codes]
    errors.extend(f"missing_required_code:{code}" for code in missing_codes)

    for code in REQUIRED_ERROR_CODES:
        spec = codes.get(code)
        if not isinstance(spec, Mapping):
            errors.append(f"{code}: spec_missing_or_invalid")
            continue
        for field in ("status", "error_code", "fallback_reason", "degraded_mode", "safe_to_consume", "retryable", "missing_dependencies"):
            if field not in spec:
                errors.append(f"{code}: missing_field:{field}")
        if not spec.get("fallback_reason"):
            errors.append(f"{code}: fallback_reason_required")
        if not spec.get("error_code"):
            errors.append(f"{code}: error_code_required")
        if bool(spec.get("safe_to_consume")) is False and not spec.get("fallback_reason"):
            errors.append(f"{code}: unsafe_entries_must_define_fallback_reason")

    return errors


def apply_theme_gate_constraints(output: Mapping[str, Any]) -> dict[str, Any]:
    """Apply B-level gate constraints without mutating the source object."""
    normalized = copy.deepcopy(dict(output))
    safe_to_consume = bool(normalized.get("safe_to_consume"))
    conflict_flag = bool(normalized.get("conflict_flag"))
    trade_grade = str(normalized.get("trade_grade", "") or "").upper()

    gate_view = dict(normalized)
    gate_view.setdefault("final_action", "ALLOW")
    gate_view.setdefault("prohibit_execute", False)

    if not safe_to_consume:
        gate_view["final_action"] = GATE_DEGRADED_ACTION
        gate_view["prohibit_execute"] = True
        if not gate_view.get("fallback_reason"):
            gate_view["fallback_reason"] = gate_view.get("error_code") or "UNKNOWN_FALLBACK"

    if conflict_flag and trade_grade == "A":
        gate_view["trade_grade"] = "C"
        gate_view["final_action"] = GATE_BLOCK_ACTION
        gate_view["prohibit_execute"] = True
        gate_view.setdefault("gate_reason", "CONFLICT_FLAG_BLOCKED_A_GRADE")

    return gate_view


def validate_theme_contract(output: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED_CONTRACT_FIELDS:
        if field not in output or output.get(field) in (None, ""):
            errors.append(f"missing_required_field:{field}")

    if bool(output.get("safe_to_consume")) is False and not output.get("fallback_reason"):
        errors.append("fallback_reason_required_when_safe_to_consume_false")

    gate_view = apply_theme_gate_constraints(output)
    if bool(output.get("safe_to_consume")) is False:
        if gate_view.get("final_action") != GATE_DEGRADED_ACTION:
            errors.append("unsafe_output_must_force_final_action_degraded")
        if gate_view.get("prohibit_execute") is not True:
            errors.append("unsafe_output_must_prohibit_execute")

    if bool(output.get("conflict_flag")) and str(output.get("trade_grade", "")).upper() == "A":
        if gate_view.get("trade_grade") == "A":
            errors.append("conflict_a_must_not_remain_a_grade")
        if gate_view.get("final_action") != GATE_BLOCK_ACTION:
            errors.append("conflict_a_must_be_blocked")
        if gate_view.get("prohibit_execute") is not True:
            errors.append("conflict_a_must_prohibit_execute")

    return errors
