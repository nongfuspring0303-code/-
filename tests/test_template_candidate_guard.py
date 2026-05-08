from pathlib import Path

import pytest

from opportunity_score import OpportunityScorer


def _write_guard_config(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "schema_version: template_candidate_guard.v1",
                "threshold_status: proposed",
                "enforcement_mode: observe_only",
                "support_score_min: 0.5",
                "template_phrases:",
                "  - 该股可能受益于相关板块上涨",
                "  - 该公司属于科技板块",
                "  - 市场情绪改善可能利好该股",
                "  - 该公司属于相关板块",
                "  - 板块上涨将带动个股走强",
            ]
        ),
        encoding="utf-8",
    )


def _payload(rationale: str, *, support_score=None, legacy_event_broadcast=False):
    candidate = {
        "symbol": "NVDA",
        "sector": "科技",
        "direction": "LONG",
        "event_beta": 1.4,
        "supporting_sector": "科技",
        "rationale": rationale,
    }
    if support_score is not None:
        candidate["support_score"] = support_score
    if legacy_event_broadcast:
        candidate["legacy_event_broadcast"] = True
        candidate["sector_score_source"] = "legacy_event_broadcast"
    return {
        "trace_id": "evt_template_guard",
        "event_hash": "evt_hash_template_guard",
        "semantic_trace_id": "evt_live_template_guard",
        "schema_version": "v1.0",
        "primary_sector": "科技",
        "sectors": [
            {
                "name": "科技",
                "direction": "LONG",
                "impact_score": 0.92,
                "confidence": 0.95,
                "role": "primary",
                "sector_score_source": "semantic_sector",
            }
        ],
        "stock_candidates": [candidate],
    }


def test_template_guard_allows_business_exposure_rationale(tmp_path):
    cfg = tmp_path / "template_candidate_guard.yaml"
    _write_guard_config(cfg)
    scorer = OpportunityScorer(template_candidate_guard_path=str(cfg))

    out = scorer.build_opportunity_update(_payload("NVDA is directly exposed to AI server demand."))

    opp = out["opportunities"][0]
    assert out["template_guard_state"]["policy_load_status"] == "loaded"
    assert out["template_guard_state"]["support_score_min"] == 0.5
    assert opp["ticker_guard_status"] == "ticker_allowed"
    assert opp["symbol"] == "NVDA"
    assert opp["rationale"] == "NVDA is directly exposed to AI server demand."


@pytest.mark.parametrize(
    "rationale",
    [
        "TSMC supplies advanced chips to NVDA.",
        "Apple is a key customer of NVDA.",
        "AMD competes with NVDA in GPUs.",
        "NVDA is directly tied to AI server demand.",
    ],
)
def test_template_guard_allows_non_template_semantic_rationales(tmp_path, rationale):
    cfg = tmp_path / "template_candidate_guard.yaml"
    _write_guard_config(cfg)
    scorer = OpportunityScorer(template_candidate_guard_path=str(cfg))

    out = scorer.build_opportunity_update(_payload(rationale))

    opp = out["opportunities"][0]
    assert opp["ticker_guard_status"] == "ticker_allowed"
    assert opp["symbol"] == "NVDA"
    assert opp["supporting_sector"] == "科技"


def test_template_guard_blocks_template_phrase_rationale(tmp_path):
    cfg = tmp_path / "template_candidate_guard.yaml"
    _write_guard_config(cfg)
    scorer = OpportunityScorer(template_candidate_guard_path=str(cfg))

    out = scorer.build_opportunity_update(_payload("该公司属于科技板块"))

    opp = out["opportunities"][0]
    assert opp["ticker_guard_status"] == "sector_only"
    assert "template_rationale" in opp["ticker_guard_reason"]
    assert opp.get("symbol", "") == ""


def test_template_guard_missing_config_fails_safe_to_sector_only(tmp_path):
    missing_cfg = tmp_path / "missing_template_candidate_guard.yaml"
    scorer = OpportunityScorer(template_candidate_guard_path=str(missing_cfg))

    out = scorer.build_opportunity_update(_payload("NVDA is directly exposed to AI server demand."))

    opp = out["opportunities"][0]
    assert out["template_guard_state"]["policy_load_status"] == "failed"
    assert out["template_guard_state"]["enforcement_mode"] == "disabled"
    assert out["template_guard_state"]["policy_error_reason"] == "missing_config"
    assert opp["ticker_guard_status"] == "sector_only"
    assert opp.get("symbol", "") == ""


def test_template_guard_invalid_config_fails_safe_to_sector_only(tmp_path):
    invalid_cfg = tmp_path / "invalid_template_candidate_guard.yaml"
    invalid_cfg.write_text("template_guard: [broken", encoding="utf-8")
    scorer = OpportunityScorer(template_candidate_guard_path=str(invalid_cfg))

    out = scorer.build_opportunity_update(_payload("NVDA is directly exposed to AI server demand."))

    opp = out["opportunities"][0]
    assert out["template_guard_state"]["policy_load_status"] == "failed"
    assert out["template_guard_state"]["enforcement_mode"] == "disabled"
    assert out["template_guard_state"]["policy_error_reason"] == "invalid_config"
    assert opp["ticker_guard_status"] == "sector_only"
    assert opp.get("symbol", "") == ""
