import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from run_c_module_stack import (
    load_runtime_config,
    resolve_history_file_path,
    validate_mock_mode,
)


def test_validate_mock_mode_rejects_invalid_values():
    try:
        validate_mock_mode("enabled")
        assert False, "expected ValueError"
    except ValueError:
        assert True


def test_validate_mock_mode_normalizes_case():
    assert validate_mock_mode("On") == "on"
    assert validate_mock_mode("AUTO") == "auto"


def test_resolve_history_file_path_project_relative():
    path = resolve_history_file_path("logs/event_bus_history.jsonl")
    assert path is not None
    assert path.endswith("logs/event_bus_history.jsonl")
    assert Path(path).is_absolute()


def test_load_runtime_config_raises_on_invalid_yaml(tmp_path):
    config_file = tmp_path / "broken.yaml"
    config_file.write_text("runtime: [\n", encoding="utf-8")
    try:
        load_runtime_config(config_file)
        assert False, "expected ValueError"
    except ValueError:
        assert True


def test_load_runtime_config_raises_on_non_mapping_root(tmp_path):
    config_file = tmp_path / "list_root.yaml"
    config_file.write_text("- item\n", encoding="utf-8")
    try:
        load_runtime_config(config_file)
        assert False, "expected ValueError"
    except ValueError:
        assert True
