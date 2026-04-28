"""Stage6 PR-7b: Outcome Engine replay consistency coverage.

Rule ID: S6-R006
Test ID: S6-018

This file verifies replay consistency for same-input reruns.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from outcome_attribution_engine import run_engine, _compute_idempotency_key

FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "stage6"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    recs = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    return recs


def test_replay_consistency_summary_identical(tmp_path):
    """Test ID S6-018: same fixture input twice must keep summary metrics stable."""
    logs_dir = FIXTURES_DIR / "outcome_logs"

    out1 = tmp_path / "replay1"
    out1.mkdir()
    result1 = run_engine(logs_dir=logs_dir, out_dir=out1)
    summary1 = _load_json(Path(result1["summary_path"]))

    out2 = tmp_path / "replay2"
    out2.mkdir()
    result2 = run_engine(logs_dir=logs_dir, out_dir=out2)
    summary2 = _load_json(Path(result2["summary_path"]))

    # Compare all numeric/metric fields (exclude timestamps)
    stable_fields = {
        "total_opportunities",
        "valid_outcome_count",
        "degraded_outcome_count",
        "invalid_outcome_count",
        "pending_outcome_count",
        "valid_resolved_t5_count",
        "hit_count_t5",
        "miss_count_t5",
        "avg_alpha_t5",
        "avg_return_t5",
        "hit_rate_t5",
        "execute_decision_count",
        "watch_decision_count",
        "block_decision_count",
        "overblocked_count",
        "correct_block_count",
        "missed_opportunity_count",
        "overblock_rate",
        "correct_block_rate",
        "missed_opportunity_rate",
        "benchmark_missing_count",
        "mapping_failure_count",
        "mapping_failure_rate",
        "score_monotonicity_status",
    }

    for field in stable_fields:
        val1 = summary1.get(field)
        val2 = summary2.get(field)
        assert val1 == val2, (
            f"Replay inconsistency: {field} differs ({val1} vs {val2})"
        )


def test_replay_consistency_outcome_records_identical(tmp_path):
    """Test ID S6-018: same fixture input twice must keep outcome rows stable."""
    logs_dir = FIXTURES_DIR / "outcome_logs"

    out1 = tmp_path / "replay1"
    out1.mkdir()
    result1 = run_engine(logs_dir=logs_dir, out_dir=out1)
    outcomes1 = _read_jsonl(Path(result1["outcome_path"]))

    out2 = tmp_path / "replay2"
    out2.mkdir()
    result2 = run_engine(logs_dir=logs_dir, out_dir=out2)
    outcomes2 = _read_jsonl(Path(result2["outcome_path"]))

    assert len(outcomes1) == len(outcomes2), (
        f"Record count mismatch: {len(outcomes1)} vs {len(outcomes2)}"
    )

    # Compare record by record (sorted by opportunity_id, excluding created_at)
    outcomes1_sorted = sorted(outcomes1, key=lambda o: o["opportunity_id"])
    outcomes2_sorted = sorted(outcomes2, key=lambda o: o["opportunity_id"])

    for o1, o2 in zip(outcomes1_sorted, outcomes2_sorted):
        # Verify same opportunity_id
        assert o1["opportunity_id"] == o2["opportunity_id"]

        # Compare all stable fields
        o1_stable = {k: v for k, v in o1.items() if k != "created_at"}
        o2_stable = {k: v for k, v in o2.items() if k != "created_at"}
        assert o1_stable == o2_stable, (
            f"Replay inconsistency for {o1['opportunity_id']} "
            f"(trace_id={o1.get('trace_id')})"
        )


def test_replay_consistency_score_buckets_identical(tmp_path):
    """Test ID S6-018: score bucket results must be identical across replays."""
    logs_dir = FIXTURES_DIR / "outcome_logs"

    out1 = tmp_path / "replay1"
    out1.mkdir()
    result1 = run_engine(logs_dir=logs_dir, out_dir=out1)
    buckets1 = _load_json(Path(result1["bucket_path"]))

    out2 = tmp_path / "replay2"
    out2.mkdir()
    result2 = run_engine(logs_dir=logs_dir, out_dir=out2)
    buckets2 = _load_json(Path(result2["bucket_path"]))

    # Compare all buckets
    for b1, b2 in zip(buckets1["buckets"], buckets2["buckets"]):
        assert b1["name"] == b2["name"]
        assert b1["sample_size"] == b2["sample_size"], (
            f"Bucket {b1['name']} sample_size differs"
        )
        assert b1.get("hit_rate_t5") == b2.get("hit_rate_t5"), (
            f"Bucket {b1['name']} hit_rate differs"
        )
        assert b1.get("avg_alpha_t5") == b2.get("avg_alpha_t5"), (
            f"Bucket {b1['name']} avg_alpha differs"
        )


def test_replay_consistency_failure_distribution_identical(tmp_path):
    """Failure reason distribution must be identical across replays."""
    logs_dir = FIXTURES_DIR / "outcome_logs"

    out1 = tmp_path / "replay1"
    out1.mkdir()
    result1 = run_engine(logs_dir=logs_dir, out_dir=out1)
    fail1 = _load_json(Path(result1["failure_path"]))

    out2 = tmp_path / "replay2"
    out2.mkdir()
    result2 = run_engine(logs_dir=logs_dir, out_dir=out2)
    fail2 = _load_json(Path(result2["failure_path"]))

    assert fail1 == fail2, "Failure distribution differs across replays"


def test_replay_consistency_mapping_attribution_identical(tmp_path):
    """Mapping attribution records must be identical across replays."""
    logs_dir = FIXTURES_DIR / "outcome_logs"

    out1 = tmp_path / "replay1"
    out1.mkdir()
    result1 = run_engine(logs_dir=logs_dir, out_dir=out1)
    map1 = _read_jsonl(Path(result1["mapping_path"]))

    out2 = tmp_path / "replay2"
    out2.mkdir()
    result2 = run_engine(logs_dir=logs_dir, out_dir=out2)
    map2 = _read_jsonl(Path(result2["mapping_path"]))

    # Sort by opportunity_id, exclude created_at
    map1_sorted = sorted(map1, key=lambda m: m["opportunity_id"])
    map2_sorted = sorted(map2, key=lambda m: m["opportunity_id"])

    assert len(map1_sorted) == len(map2_sorted)

    for m1, m2 in zip(map1_sorted, map2_sorted):
        m1_stable = {k: v for k, v in m1.items() if k != "created_at"}
        m2_stable = {k: v for k, v in m2.items() if k != "created_at"}
        assert m1_stable == m2_stable, (
            f"Mapping attribution differs for {m1['opportunity_id']}"
        )


def test_replay_consistency_alpha_report_identical(tmp_path):
    """Alpha report must be identical across replays."""
    logs_dir = FIXTURES_DIR / "outcome_logs"

    out1 = tmp_path / "replay1"
    out1.mkdir()
    result1 = run_engine(logs_dir=logs_dir, out_dir=out1)
    alpha1 = _load_json(Path(result1["alpha_path"]))

    out2 = tmp_path / "replay2"
    out2.mkdir()
    result2 = run_engine(logs_dir=logs_dir, out_dir=out2)
    alpha2 = _load_json(Path(result2["alpha_path"]))

    assert alpha1 == alpha2, "Alpha report differs across replays"


def test_replay_consistency_decision_suggestions_identical(tmp_path):
    """Decision suggestions must be identical across replays."""
    logs_dir = FIXTURES_DIR / "outcome_logs"

    out1 = tmp_path / "replay1"
    out1.mkdir()
    result1 = run_engine(logs_dir=logs_dir, out_dir=out1)
    sug1 = _load_json(Path(result1["suggestions_path"]))

    out2 = tmp_path / "replay2"
    out2.mkdir()
    result2 = run_engine(logs_dir=logs_dir, out_dir=out2)
    sug2 = _load_json(Path(result2["suggestions_path"]))

    assert sug1 == sug2, "Decision suggestions differ across replays"
