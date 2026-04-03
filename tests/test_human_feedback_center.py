import tempfile
from pathlib import Path

from scripts.human_feedback_center import HumanFeedbackCenter


def _seed_files(base: Path) -> None:
    (base / "configs").mkdir(parents=True, exist_ok=True)
    (base / "logs").mkdir(parents=True, exist_ok=True)
    (base / "configs" / "sector_impact_mapping.yaml").write_text(
        "schema_version: v1.0\nmappings:\n  - event_keyword: 降息\n    sector: 科技\n",
        encoding="utf-8",
    )
    (base / "configs" / "premium_stock_pool.yaml").write_text(
        "schema_version: v1.0\nstocks:\n  - symbol: NVDA\n",
        encoding="utf-8",
    )


def test_load_and_update_configs():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _seed_files(root)
        center = HumanFeedbackCenter(base_dir=str(root))

        sector = center.get_sector_mapping()
        assert sector["schema_version"] == "v1.0"

        sector["mappings"].append(
            {
                "event_keyword": "油价上行",
                "sector": "航空",
                "direction": "SHORT",
                "impact_score": 0.66,
            }
        )
        center.update_sector_mapping(sector)
        refreshed = center.get_sector_mapping()
        assert len(refreshed["mappings"]) == 2
        assert "updated_at" in refreshed


def test_submit_and_export_feedback():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _seed_files(root)
        center = HumanFeedbackCenter(base_dir=str(root))

        resp = center.submit_feedback(
            trace_id="evt_demo_001",
            source_module="C",
            target_module="A",
            feedback_type="sector_direction_correction",
            original_value="LONG",
            corrected_value="SHORT",
            reason="盘后确认政策偏鹰",
        )
        assert resp["status"] == "ok"

        package = center.export_feedback_package("A")
        assert package["target_module"] == "A"
        assert package["count"] == 1
        assert package["items"][0]["trace_id"] == "evt_demo_001"
