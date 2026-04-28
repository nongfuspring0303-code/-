from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_metric_dictionary() -> dict:
    return yaml.safe_load(
        (REPO_ROOT / "configs" / "metric_dictionary.yaml").read_text(encoding="utf-8")
    )


def test_stage6_metric_dictionary_has_required_core_metrics() -> None:
    data = _load_metric_dictionary()
    stage6_metrics = data.get("stage6_metrics", {})

    required = {
        "hit_rate_t5",
        "avg_alpha_t5",
        "avg_return_t5",
        "score_monotonicity",
        "mapping_failure_rate",
        "overblock_rate",
        "missed_opportunity_rate",
        "correct_block_rate",
        "execute_outcome_coverage_rate",
        "valid_outcome_count",
        "degraded_outcome_count",
        "invalid_outcome_count",
        "pending_outcome_count",
    }
    assert required.issubset(set(stage6_metrics.keys()))


def test_stage6_metric_dictionary_has_provider_and_fallback_metrics() -> None:
    data = _load_metric_dictionary()
    stage6_metrics = data.get("stage6_metrics", {})

    expected = {
        "fallback_rate",
        "provider_failed_count",
        "orphan_replay",
        "market_data_default_used_in_execute_count",
        "missing_opportunity_but_execute_count",
    }
    assert expected.issubset(set(stage6_metrics.keys()))


def test_stage6_metric_entries_have_minimum_fields() -> None:
    data = _load_metric_dictionary()
    stage6_metrics = data.get("stage6_metrics", {})

    # Keep the validation lightweight but deterministic: each metric entry
    # must have enough metadata to be auditable in review.
    required_fields = {"definition", "formula", "data_source", "output_file", "owner"}
    for metric_name, metric_cfg in stage6_metrics.items():
        assert required_fields.issubset(
            set(metric_cfg.keys())
        ), f"{metric_name} missing required metadata"


def test_metric_dictionary_preserves_legacy_stage4_stage5_metrics() -> None:
    data = _load_metric_dictionary()
    metrics = data.get("metrics", {})

    assert "ai_confidence" in metrics
    assert "ai_a0_event_strength" in metrics
    assert "ai_expectation_gap" in metrics

    enumerations = data.get("enumerations", {})
    assert "market_data_provenance" in enumerations
    assert "semantic" in enumerations
    assert "fallback_reason" in enumerations["market_data_provenance"]
    assert "fallback_reason" in enumerations["semantic"]


def test_metric_dictionary_preserves_legacy_fallback_reason_values() -> None:
    data = _load_metric_dictionary()
    enumerations = data["enumerations"]

    market_fallback = set(enumerations["market_data_provenance"]["fallback_reason"])
    semantic_fallback = set(enumerations["semantic"]["fallback_reason"])

    assert "" in market_fallback
    assert "NO_PRICE_RESOLVED" in market_fallback
    assert "FALLBACK_PARTIAL" in market_fallback
    assert "PARTIAL_PRICE_RESOLVED" in market_fallback

    assert "" in semantic_fallback
    assert "semantic_disabled" in semantic_fallback
    assert "emergency_disabled" in semantic_fallback
    assert "full_enable_disabled" in semantic_fallback
    assert "timeout" in semantic_fallback
    assert "provider_error" in semantic_fallback
    assert "api_key_missing" in semantic_fallback
    assert "confidence_below_threshold" in semantic_fallback
    assert "chain_missing" in semantic_fallback
