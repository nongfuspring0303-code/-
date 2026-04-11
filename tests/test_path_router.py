import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from transmission_engine.core.path_router import PathRouter


def _base_input(**overrides):
    payload = {
        "event_id": "ME-B-PR-001",
        "schema_version": "v1.1",
        "headline": "Rates and liquidity drive the market narrative",
        "summary": "Policy, prices, and sentiment all move together.",
    }
    payload.update(overrides)
    return payload


def test_path_router_emits_three_paths_with_required_fields_and_impact_chain():
    out = PathRouter().run(_base_input())

    assert out.status.value == "success"
    transmission_paths = out.data["transmission_paths"]
    impact_chain = out.data["impact_chain"]

    assert len(transmission_paths) >= 3
    assert {path["path_type"] for path in transmission_paths} == {
        "fundamental",
        "asset_pricing",
        "narrative",
    }
    for path in transmission_paths:
        assert {"path_id", "path_type", "horizon", "persistence", "confidence", "nodes", "edges"}.issubset(path.keys())
        assert path["confidence"] == round(path["confidence"], 2)
        assert isinstance(path["nodes"], list) and len(path["nodes"]) >= 2
        assert isinstance(path["edges"], list) and len(path["edges"]) >= 1

    assert len(impact_chain) >= 3
    for item in impact_chain:
        assert {"full_path", "score", "direction", "reason"}.issubset(item.keys())
        assert item["score"] == round(item["score"], 2)


def test_path_router_marks_degraded_status_when_nodes_or_edges_are_missing():
    out = PathRouter().run(
        _base_input(
            path_blueprints=[
                {
                    "path_type": "fundamental",
                    "path_id": "fund_custom",
                    "path_name": "fundamental_custom",
                    "nodes": ["ME-B-PR-001"],
                    "edges": [],
                }
            ]
        )
    )

    transmission_paths = {path["path_type"]: path for path in out.data["transmission_paths"]}
    impact_chain = out.data["impact_chain"]

    assert transmission_paths["fundamental"]["status"] == "degraded"
    assert "missing_edges" in impact_chain[0]["reason"] or "missing_nodes" in impact_chain[0]["reason"]
    assert all(path["path_type"] in {"fundamental", "asset_pricing", "narrative"} for path in out.data["transmission_paths"])
    assert any(path["status"] == "active" for path in out.data["transmission_paths"])
