"""Smoke test for ai_mapping_regression_eval CLI.

Tests that run_ai_mapping_regression_eval.py exits 0 and produces
the expected gate/output keys. Output goes to tmp dir only.
"""
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "ai_mapping_regression_eval"


def _ensure_fixtures():
    """Create minimal fixture files if they do not exist."""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    policy = FIXTURES_DIR / "policy_fixture.yaml"
    if not policy.exists():
        policy.write_text("""
schema_version: "1.0"
gates:
  hard:
    empty_mapping_rate:
      op: "<"
      value: 0.05
    healthcare_misroute_count:
      op: "="
      value: 0
  target:
    stock_quality_mean:
      op: ">="
      value: 20.0
""", encoding="utf-8")

    prev_sc = FIXTURES_DIR / "scorecard_prev.jsonl"
    if not prev_sc.exists():
        prev_sc.write_text(
            json.dumps({"trace_id": "prev-001", "semantic_event_type": "energy",
                        "sector_candidates": ["Energy"], "sector_quality_score": 100,
                        "ticker_quality_score": 100, "ai_confidence": 80}) + "\n" +
            json.dumps({"trace_id": "prev-002", "semantic_event_type": "geo_political",
                        "sector_candidates": ["Energy"], "sector_quality_score": 100,
                        "ticker_quality_score": 100, "ai_confidence": 80}) + "\n",
            encoding="utf-8")

    new_sc = FIXTURES_DIR / "scorecard_new.jsonl"
    if not new_sc.exists():
        new_sc.write_text(
            json.dumps({"trace_id": "new-001", "semantic_event_type": "energy",
                        "sector_candidates": ["Energy"], "sector_quality_score": 100,
                        "ticker_quality_score": 100, "ai_confidence": 80}) + "\n" +
            json.dumps({"trace_id": "new-002", "semantic_event_type": "geo_political",
                        "sector_candidates": ["Energy"], "sector_quality_score": 100,
                        "ticker_quality_score": 100, "ai_confidence": 80}) + "\n",
            encoding="utf-8")


def test_ai_mapping_regression_eval_smoke(tmp_path):
    """CLI smoke test: exits 0, produces gate + group keys."""
    _ensure_fixtures()

    policy = FIXTURES_DIR / "policy_fixture.yaml"
    prev_sc = FIXTURES_DIR / "scorecard_prev.jsonl"
    new_sc = FIXTURES_DIR / "scorecard_new.jsonl"
    out_json = tmp_path / "eval_out.json"
    out_md = tmp_path / "eval_out.md"

    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "run_ai_mapping_regression_eval.py"),
         "--policy", str(policy),
         "--prev-scorecard", str(prev_sc),
         "--new-scorecard", str(new_sc),
         "--out-json", str(out_json),
         "--out-md", str(out_md)],
        capture_output=True, text=True, timeout=30,
    )

    # Must exit clean
    assert result.returncode == 0, f"returncode={result.returncode}\nstderr={result.stderr}"

    # JSON output must contain expected keys
    assert out_json.exists(), f"out_json not found: {out_json}"
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data.get("label_rows", 0) > 0, f"label_rows should be >0, got {data.get('label_rows')}"
    assert data.get("label_warnings", []) == [], f"label_warnings should be empty, got {data.get('label_warnings')}"
    assert "gate" in data, f"missing gate key: {list(data.keys())}"
    assert "v_new" in data, f"missing v_new key"
    assert "delta" in data, f"missing delta key"

    gate = data["gate"]
    assert "hard_pass" in gate, f"missing hard_pass in gate"
    assert "target_pass" in gate, f"missing target_pass in gate"

    v_new = data["v_new"]
    assert "groups" in v_new, f"missing v_new.groups"
    assert "overall" in v_new["groups"], f"missing v_new.groups.overall"
    delta = data["delta"]
    assert "groups" in delta, "missing delta.groups"
    assert "overall" in delta["groups"], "missing delta.groups.overall"

    # Output must be in tmp dir only, not in reports/
    assert "reports" not in str(out_json), f"output leaked to reports: {out_json}"
    assert "logs" not in str(out_json), f"output leaked to logs: {out_json}"


def test_ai_mapping_regression_eval_smoke_exposes_invalid_labels(tmp_path):
    """Invalid labels must surface warnings explicitly (no silent pass)."""
    _ensure_fixtures()
    bad_labels = tmp_path / "bad_labels.yaml"
    bad_labels.write_text(
        """
schema_version: "1.0"
samples:
  - sample_id: "bad-001"
    event_hash: "hash-only"
    logged_at: "2026-05-04T00:00:00Z"
    event_type_expected: "energy"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    policy = FIXTURES_DIR / "policy_fixture.yaml"
    prev_sc = FIXTURES_DIR / "scorecard_prev.jsonl"
    new_sc = FIXTURES_DIR / "scorecard_new.jsonl"
    out_json = tmp_path / "eval_out_bad_labels.json"
    out_md = tmp_path / "eval_out_bad_labels.md"
    policy_with_bad_labels = tmp_path / "policy_with_bad_labels.yaml"
    policy_with_bad_labels.write_text(
        f"""
schema_version: "1.0"
datasets:
  benchmark:
    labels_file: "{bad_labels}"
gates:
  hard:
    empty_mapping_rate:
      op: "<"
      value: 1.0
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "run_ai_mapping_regression_eval.py"),
         "--policy", str(policy_with_bad_labels),
         "--prev-scorecard", str(prev_sc),
         "--new-scorecard", str(new_sc),
         "--out-json", str(out_json),
         "--out-md", str(out_md)],
        capture_output=True, text=True, timeout=30,
    )

    assert result.returncode == 0, f"returncode={result.returncode}\nstderr={result.stderr}"
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data.get("label_rows", 0) == 0
    assert any("missing trace_id" in str(x) for x in data.get("label_warnings", [])), data.get("label_warnings", [])
