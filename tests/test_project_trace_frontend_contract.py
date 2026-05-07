from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_trace_detail_dom_contract_markers_exist():
    html = _read("canvas/index.html")
    js = _read("canvas/app.js")

    assert 'data-module="TraceDetailPanel"' in html
    assert 'data-key="trace_detail.panel"' in html
    assert 'data-state="PENDING"' in html

    required_modules = [
        "LifecycleFatigueCard",
        "ExecutionSuggestionCard",
        "PathQualityEvalCard",
        "TraceScorecardCard",
        "PipelineStageCard",
    ]
    for module in required_modules:
        assert f'moduleName: \'{module}\'' in js

    required_keys = [
        "execution_suggestion.trade_type",
        "path_quality_eval.composite_score",
        "trace_scorecard.final_action",
        "pipeline_stage.stage",
    ]
    for key in required_keys:
        assert key in js

    for state in ["MISSING", "FAILED", "PENDING", "STALE"]:
        assert state in js


def test_trace_detail_ui_safe_render_guard_exists():
    js = _read("canvas/app.js")
    assert "safeText" in js
    assert "safeNumber" in js
    assert "safePercent" in js
    assert "API_RESPONSE_INVALID" in js
    assert "currentTraceAnalysis" in js
    assert "moduleState" in js
    assert "moduleHasError" in js
    assert "FAILED" in js
