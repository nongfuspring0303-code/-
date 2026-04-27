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
