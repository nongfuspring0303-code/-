"""Stage6 PR-7b: Outcome Engine idempotency coverage.

Rule ID: S6-R005
Test ID: S6-017

This file verifies same-key reruns are idempotent when the engine writes into
the same output target more than once.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from outcome_attribution_engine import run_engine

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


def _without_generated_at(payload: dict) -> dict:
    return {k: v for k, v in payload.items() if k != "generated_at"}


def _run_same_target_twice(tmp_path: Path) -> tuple[dict, dict]:
    logs_dir = FIXTURES_DIR / "outcome_logs"
    out_dir = tmp_path / "same-target"
    out_dir.mkdir()

    first = run_engine(logs_dir=logs_dir, out_dir=out_dir)
    first_snapshot = {
        "summary": _load_json(Path(first["summary_path"])),
        "outcomes": _read_jsonl(Path(first["outcome_path"])),
        "mapping": _read_jsonl(Path(first["mapping_path"])),
        "failure": _load_json(Path(first["failure_path"])),
    }

    second = run_engine(logs_dir=logs_dir, out_dir=out_dir)
    second_snapshot = {
        "summary": _load_json(Path(second["summary_path"])),
        "outcomes": _read_jsonl(Path(second["outcome_path"])),
        "mapping": _read_jsonl(Path(second["mapping_path"])),
        "failure": _load_json(Path(second["failure_path"])),
    }

    return first_snapshot, second_snapshot


def test_s6_017_same_output_target_keeps_summary_stable(tmp_path):
    """Test ID S6-017: rerunning the same output target must not drift summary metrics."""
    first, second = _run_same_target_twice(tmp_path)

    assert _without_generated_at(first["summary"]) == _without_generated_at(second["summary"]), (
        "S6-017 violation: summary metrics changed after rerunning the same output target"
    )


def test_s6_017_same_output_target_does_not_duplicate_outcomes(tmp_path):
    """Test ID S6-017: rerunning the same output target must not duplicate outcome rows."""
    first, second = _run_same_target_twice(tmp_path)

    first_ids = [row["opportunity_id"] for row in first["outcomes"]]
    second_ids = [row["opportunity_id"] for row in second["outcomes"]]

    assert len(second["outcomes"]) == len(first["outcomes"]), (
        "S6-017 violation: rerun changed opportunity_outcome row count"
    )
    assert len(second_ids) == len(set(second_ids)), (
        "S6-017 violation: duplicate opportunity_id rows found after rerun"
    )
    assert first_ids == second_ids, (
        "S6-017 violation: rerun changed opportunity_outcome ordering or membership"
    )


def test_s6_017_same_output_target_does_not_duplicate_mapping_rows(tmp_path):
    """Test ID S6-017: rerunning the same output target must not duplicate mapping rows."""
    first, second = _run_same_target_twice(tmp_path)

    first_keys = [(row["trace_id"], row["opportunity_id"]) for row in first["mapping"]]
    second_keys = [(row["trace_id"], row["opportunity_id"]) for row in second["mapping"]]

    assert len(second["mapping"]) == len(first["mapping"]), (
        "S6-017 violation: rerun changed mapping_attribution row count"
    )
    assert len(second_keys) == len(set(second_keys)), (
        "S6-017 violation: duplicate mapping_attribution rows found after rerun"
    )
    assert first_keys == second_keys, (
        "S6-017 violation: rerun changed mapping_attribution ordering or membership"
    )


def test_s6_017_same_output_target_keeps_failure_distribution_stable(tmp_path):
    """Test ID S6-017: rerunning the same output target must not drift failure stats."""
    first, second = _run_same_target_twice(tmp_path)

    assert first["failure"] == second["failure"], (
        "S6-017 violation: failure distribution changed after rerunning the same output target"
    )
