from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent
OPS = {"<", "<=", "=", ">=", ">"}


def test_ai_mapping_regression_policy_contract():
    path = ROOT / "configs" / "ai_mapping_regression_policy.yaml"
    assert path.exists(), f"missing file: {path}"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    datasets = data.get("datasets", {})
    assert isinstance(datasets, dict) and "benchmark" in datasets, "datasets.benchmark is required"
    benchmark = datasets["benchmark"]
    labels_file = benchmark.get("labels_file")
    assert labels_file, "datasets.benchmark.labels_file is required"
    labels_path = ROOT / str(labels_file)
    assert labels_path.exists(), f"benchmark labels file does not exist: {labels_path}"
    labels_data = yaml.safe_load(labels_path.read_text(encoding="utf-8")) or {}
    samples = labels_data.get("samples", [])
    assert isinstance(samples, list) and len(samples) > 0, "benchmark labels must contain samples > 0"

    gates = data.get("gates", {})
    assert isinstance(gates, dict), "gates must be a dict"
    for gate_name in ("hard", "target"):
        gate = gates.get(gate_name, {})
        assert isinstance(gate, dict) and gate, f"gates.{gate_name} must be non-empty dict"
        for metric, rule in gate.items():
            assert isinstance(rule, dict), f"gates.{gate_name}.{metric} must be dict"
            assert "op" in rule and "value" in rule, f"gates.{gate_name}.{metric} missing op/value"
            assert str(rule["op"]) in OPS, f"gates.{gate_name}.{metric}.op invalid: {rule['op']}"
