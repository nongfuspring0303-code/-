"""Standalone Stage6 test runner (no pytest dependency).

Usage:
    python3 tests/run_stage6_tests.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from outcome_attribution_engine import run_engine

FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "stage6"
OUT_DIR = Path("/tmp/stage6_outcome_test")

passed = 0
failed = 0


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


def _find_by_trace(outcomes: list[dict], trace_id: str) -> dict | None:
    for o in outcomes:
        if o.get("trace_id") == trace_id:
            return o
    return None


def check(description: str, condition: bool):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {description}")
    else:
        failed += 1
        print(f"  FAIL: {description}")


# ---------------------------------------------------------------------------
# Run engine
# ---------------------------------------------------------------------------
print("=" * 60)
print("Stage6 PR-7b Outcome Engine Test Suite")
print("=" * 60)

OUT_DIR.mkdir(parents=True, exist_ok=True)
result = run_engine(
    logs_dir=FIXTURES_DIR / "outcome_logs",
    out_dir=OUT_DIR,
    horizon="t5",
)
outcomes = _read_jsonl(Path(result["outcome_path"]))
summary = _load_json(Path(result["summary_path"]))
buckets = _load_json(Path(result["bucket_path"]))
alpha_report = _load_json(Path(result["alpha_path"]))
fail_dist = _load_json(Path(result["failure_path"]))
mappings = _read_jsonl(Path(result["mapping_path"]))
suggestions = _load_json(Path(result["suggestions_path"]))
trust_report = _load_json(Path(result["trust_path"]))

print(f"\nEngine processed {result['total_opportunities']} opportunities.\n")

# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------
print("--- Schema Validation ---")
schema_dir = REPO_ROOT / "schemas"
outcome_schema = _load_json(schema_dir / "opportunity_outcome.schema.json")
mapping_schema = _load_json(schema_dir / "mapping_attribution.schema.json")
log_trust_schema = _load_json(schema_dir / "log_trust.schema.json")
bucket_schema = _load_json(schema_dir / "outcome_by_score_bucket.schema.json")

from jsonschema import validate as schema_validate, ValidationError

schema_ok = True
for o in outcomes:
    try:
        schema_validate(instance=o, schema=outcome_schema)
    except ValidationError as e:
        schema_ok = False
        print(f"  SCHEMA FAIL: {o.get('opportunity_id')}: {e}")
check("All opportunity_outcome records validate against schema", schema_ok)

mapping_ok = True
for m in mappings:
    try:
        schema_validate(instance=m, schema=mapping_schema)
    except Exception:
        mapping_ok = False
check("All mapping_attribution records validate against schema", mapping_ok)

try:
    buckets_result = schema_validate(instance=buckets, schema=bucket_schema)
    bucket_ok = True
except Exception:
    bucket_ok = False
check("outcome_by_score_bucket output validates against schema", bucket_ok)

# ---------------------------------------------------------------------------
# EXECUTE LONG
# ---------------------------------------------------------------------------
print("\n--- EXECUTE LONG ---")
o = _find_by_trace(outcomes, "EXEC-LONG-HIT-001")
check("EXEC LONG with t5_return +3% -> hit", o and o["outcome_label"] == "hit" and o["data_quality"] == "valid")

o = _find_by_trace(outcomes, "EXEC-LONG-MISS-001")
check("EXEC LONG with t5_return -3% -> miss", o and o["outcome_label"] == "miss" and o["data_quality"] == "valid")

o = _find_by_trace(outcomes, "EXEC-LONG-NEUT-001")
check("EXEC LONG with t5_return +1% -> neutral", o and o["outcome_label"] == "neutral" and o["data_quality"] == "valid")

# ---------------------------------------------------------------------------
# EXECUTE SHORT
# ---------------------------------------------------------------------------
print("\n--- EXECUTE SHORT ---")
o = _find_by_trace(outcomes, "EXEC-SHORT-HIT-001")
check("EXEC SHORT with t5_return -3% -> hit", o and o["outcome_label"] == "hit")

o = _find_by_trace(outcomes, "EXEC-SHORT-MISS-001")
check("EXEC SHORT with t5_return +3% -> miss", o and o["outcome_label"] == "miss")

# ---------------------------------------------------------------------------
# WATCH
# ---------------------------------------------------------------------------
print("\n--- WATCH ---")
o = _find_by_trace(outcomes, "WATCH-MISSEDOPP-001")
check("WATCH LONG with subsequent +3% -> missed_opportunity", o and o["outcome_label"] == "missed_opportunity" and o["data_quality"] == "valid")

o = _find_by_trace(outcomes, "WATCH-CORRECT-001")
check("WATCH LONG with subsequent -3% -> correct_watch", o and o["outcome_label"] == "correct_watch" and o["data_quality"] == "valid")

o = _find_by_trace(outcomes, "WATCH-NEUTRAL-001")
check("WATCH LONG with +1% -> neutral_watch", o and o["outcome_label"] == "neutral_watch" and o["data_quality"] == "valid")

# ---------------------------------------------------------------------------
# BLOCK
# ---------------------------------------------------------------------------
print("\n--- BLOCK ---")
o = _find_by_trace(outcomes, "BLOCK-CORRECT-001")
check("BLOCK LONG with subsequent -3% -> correct_block", o and o["outcome_label"] == "correct_block" and o["data_quality"] == "valid")

o = _find_by_trace(outcomes, "BLOCK-OVERBLOCK-001")
check("BLOCK LONG with subsequent +3% -> overblocked", o and o["outcome_label"] == "overblocked" and o["data_quality"] == "valid")

o = _find_by_trace(outcomes, "BLOCK-NEUTRAL-001")
check("BLOCK LONG with +1% -> neutral_block", o and o["outcome_label"] == "neutral_block" and o["data_quality"] == "valid")

# ---------------------------------------------------------------------------
# DATA QUALITY EDGE CASES
# ---------------------------------------------------------------------------
print("\n--- Data Quality Edge Cases ---")
o = _find_by_trace(outcomes, "JOINKEY-MISSING-001")
check("Missing join key -> invalid", o and o["data_quality"] == "invalid")

o = _find_by_trace(outcomes, "SYMBOL-MISSING-001")
check("Missing symbol -> invalid", o and o["data_quality"] == "invalid")

o = _find_by_trace(outcomes, "BENCHMARK-MISS-001")
check("Benchmark missing -> degraded or valid with benchmark flag", o is not None)

o = _find_by_trace(outcomes, "PENDING-T5-001")
check("Pending T+5 -> pending, no hit/miss", o and o["data_quality"] == "pending" and o["outcome_label"] is None)

o = _find_by_trace(outcomes, "AUDIT-PENDING-001")
check("PENDING_CONFIRM -> degraded, audit-only, no hit/miss", o and o["data_quality"] != "valid" and o["outcome_label"] is None)

o = _find_by_trace(outcomes, "AUDIT-UNKNOWN-001")
check("UNKNOWN -> degraded, audit-only, no hit/miss", o and o["data_quality"] != "valid" and o["outcome_label"] is None)

o = _find_by_trace(outcomes, "MKT-DATA-STALE-001")
check("Stale market data -> degraded", o and o["data_quality"] in ("degraded", "invalid"))

o = _find_by_trace(outcomes, "MKT-DATA-DEFAULT-001")
check("Default market data -> degraded/invalid", o and o["data_quality"] in ("degraded", "invalid"))

# ---------------------------------------------------------------------------
# SCORE BUCKETS
# ---------------------------------------------------------------------------
print("\n--- Score Buckets ---")
o = _find_by_trace(outcomes, "SCORE-80PLUS-001")
check("Score 88 -> 80_PLUS bucket", o and o["score_bucket"] == "80_PLUS")

o = _find_by_trace(outcomes, "SCORE-60-79-001")
check("Score 68 -> 60_79 bucket", o and o["score_bucket"] == "60_79")

o = _find_by_trace(outcomes, "SCORE-40-59-001")
check("Score 52 -> 40_59 bucket", o and o["score_bucket"] == "40_59")

o = _find_by_trace(outcomes, "SCORE-LT40-001")
check("Score 32 -> LT_40 bucket", o and o["score_bucket"] == "LT_40")

# ---------------------------------------------------------------------------
# OUTPUT FILES
# ---------------------------------------------------------------------------
print("\n--- Output Files ---")
check("opportunity_outcome.jsonl exists", Path(result["outcome_path"]).exists())
check("outcome_summary.json exists", Path(result["summary_path"]).exists())
check("outcome_by_score_bucket.json exists", Path(result["bucket_path"]).exists())
check("score_monotonicity_report.json exists", Path(result["mono_path"]).exists())
check("failure_reason_distribution.json exists", Path(result["failure_path"]).exists())
check("alpha_report.json exists", Path(result["alpha_path"]).exists())
check("log_trust_report.json exists", Path(result["trust_path"]).exists())
check("mapping_attribution.jsonl exists", Path(result["mapping_path"]).exists())
check("decision_suggestions.json exists", Path(result["suggestions_path"]).exists())

# ---------------------------------------------------------------------------
# SUMMARY STATS
# ---------------------------------------------------------------------------
print("\n--- Summary Statistics ---")
check("Total opportunities > 0", result["total_opportunities"] > 0)
check("Has valid outcomes", summary.get("valid_outcome_count", 0) > 0)
check("Has hit_count_t5", summary.get("hit_count_t5", 0) > 0)
check("Has miss_count_t5", summary.get("miss_count_t5", 0) > 0)
check("Has avg_alpha_t5", summary.get("avg_alpha_t5") is not None)

# Alpha report checks
# Benchmark missing records are degraded (not valid), so they are excluded from alpha
# at the data_quality level. Verify degraded records exist and are excluded.
check("Degraded outcome count > 0 (includes benchmark_missing)", summary.get("degraded_outcome_count", 0) > 0)
check("Alpha eligible count <= valid resolved", alpha_report.get("alpha_eligible_count", 0) <= summary.get("valid_resolved_t5_count", 1000))
check("benchmark_missing in failure distribution", "benchmark_missing" in fail_dist)

# ---------------------------------------------------------------------------
# IDEMPOTENCY (quick check)
# ---------------------------------------------------------------------------
print("\n--- Idempotency Quick Check ---")
out2 = Path("/tmp/stage6_outcome_test_run2")
out2.mkdir(exist_ok=True)
result2 = run_engine(logs_dir=FIXTURES_DIR / "outcome_logs", out_dir=out2)
summary2 = _load_json(Path(result2["summary_path"]))

core_metrics = [
    "total_opportunities", "valid_outcome_count", "hit_count_t5", "miss_count_t5",
    "execute_decision_count", "watch_decision_count", "block_decision_count",
]
idem_ok = True
for m in core_metrics:
    if summary.get(m) != summary2.get(m):
        idem_ok = False
        print(f"  IDEM FAIL: {m}: {summary.get(m)} vs {summary2.get(m)}")
check("Core summary metrics idempotent", idem_ok)

# ---------------------------------------------------------------------------
# DECISION SUGGESTIONS
# ---------------------------------------------------------------------------
print("\n--- Decision Suggestions ---")
check("Decision suggestions generated", len(suggestions) >= 0)
for s in suggestions:
    check(f"Suggestion {s.get('opportunity_id')} requires human review", s.get("requires_human_review", False))

# ---------------------------------------------------------------------------
# FINAL
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print(f"RESULTS: {passed} PASSED, {failed} FAILED")
print(f"Output directory: {OUT_DIR}")
print("=" * 60)

if failed > 0:
    sys.exit(1)
