from __future__ import annotations

from full_workflow_runner import FullWorkflowRunner


def test_semantic_prepass_contract_shape_and_normalization() -> None:
    semantic_out = {
        "event_type": "sector",
        "sentiment": "positive",
        "confidence": 82,
        "recommended_stocks": ["QCOM", "AMD"],
        "transmission_candidates": ["semiconductor"],
    }
    out = FullWorkflowRunner._build_semantic_prepass_contract(
        semantic_out=semantic_out,
        headline="QCOM up 5% on NASDAQ",
    )

    required = {
        "route_type",
        "event_type",
        "event_direction",
        "anchor_entities",
        "semantic_confidence",
        "market_hint",
        "needs_full_semantic",
        "prepass_latency_ms",
    }
    assert required.issubset(set(out.keys()))
    assert out["route_type"] in {"company_anchor", "macro_event", "sector_event", "unknown"}
    assert out["event_direction"] in {"positive", "negative", "mixed", "neutral"}
    assert 0.0 <= out["semantic_confidence"] <= 1.0
    assert out["market_hint"] == "US"
    assert out["anchor_entities"] == ["QCOM", "AMD"]
    assert out["needs_full_semantic"] is True


def test_semantic_prepass_timeout_like_input_degrades_safely() -> None:
    semantic_out = {
        "event_type": "unknown",
        "sentiment": "neutral",
        "confidence": None,
        "recommended_stocks": [],
        "transmission_candidates": [],
    }
    out = FullWorkflowRunner._build_semantic_prepass_contract(
        semantic_out=semantic_out,
        headline="",
    )

    assert out["route_type"] == "unknown"
    assert out["semantic_confidence"] == 0.0
    assert out["event_direction"] == "neutral"
    assert out["anchor_entities"] == []
