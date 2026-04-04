from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent


def test_conduction_mapping_config_has_categories():
    cfg_path = ROOT / "configs" / "edt-modules-config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    mapping = cfg.get("modules", {}).get("ConductionMapper", {}).get("params", {}).get("event_conduction", {})
    assert mapping, "event_conduction mapping is required"
    for category in ["A", "B", "C", "D", "E", "F", "G"]:
        assert category in mapping, f"missing category {category} in event_conduction"
        entry = mapping[category]
        assert "macro" in entry and "sector" in entry


def test_conduction_mapping_config_has_time_scales():
    cfg_path = ROOT / "configs" / "edt-modules-config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    scales = cfg.get("modules", {}).get("ConductionMapper", {}).get("params", {}).get("time_scales", [])
    assert "intraday" in scales
    assert "overnight" in scales
    assert "multiweek" in scales


def test_sector_impact_mapping_file_exists():
    mapping_path = ROOT / "configs" / "sector_impact_mapping.yaml"
    assert mapping_path.exists()
    payload = yaml.safe_load(mapping_path.read_text(encoding="utf-8")) or {}
    assert payload.get("mapping")
