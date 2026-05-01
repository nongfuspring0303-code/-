"""Stage6 Outcome Attribution Engine.

Member-C implementation for PR-7b.
Read-only consumption of Stage5 upstream evidence logs.
Generates outcome attribution records, summaries, and reports.

Usage:
    python3 scripts/outcome_attribution_engine.py \
      --logs-dir tests/fixtures/stage6/outcome_logs \
      --out-dir /tmp/stage6_outcome_test
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Schema versions
# ---------------------------------------------------------------------------
SCHEMA_OUTCOME = "stage6.outcome.v1"
SCHEMA_MAPPING = "stage6.mapping_attribution.v1"
SCHEMA_LOG_TRUST = "stage6.log_trust.v1"
SCHEMA_BUCKET = "stage6.outcome_by_score_bucket.v1"

# ---------------------------------------------------------------------------
# Failure reason enum (from schema + B's rules)
# ---------------------------------------------------------------------------
FAILURE_REASONS = frozenset({
    "mapping_wrong", "timing_wrong", "market_rejected", "source_bad",
    "risk_too_strict", "risk_too_loose", "provider_bad", "market_data_bad",
    "score_not_predictive", "gate_rule_wrong", "execution_missing",
    "join_key_missing", "benchmark_missing", "insufficient_sample",
})


def _require_policy_thresholds(policy: dict) -> dict:
    """Return policy['thresholds'] and fail fast if missing or malformed."""
    thresholds = policy.get("thresholds")
    if not isinstance(thresholds, dict):
        raise ValueError("Invalid policy: missing thresholds section")

    required_keys = (
        "long_hit_return_t5",
        "long_hit_alpha_t5",
        "long_miss_return_t5",
        "long_miss_alpha_t5",
        "short_hit_return_t5",
        "short_hit_alpha_t5",
        "short_miss_return_t5",
        "short_miss_alpha_t5",
    )
    missing = [k for k in required_keys if k not in thresholds]
    if missing:
        raise ValueError(f"Invalid policy.thresholds: missing required keys: {missing}")
    return thresholds


def _require_policy_stats(policy: dict) -> dict:
    """Return policy['stats'] and fail fast if missing or malformed."""
    stats = policy.get("stats")
    if not isinstance(stats, dict):
        raise ValueError("Invalid policy: missing stats section")
    required_keys = ("min_bucket_sample_size", "min_total_sample_size")
    missing = [k for k in required_keys if k not in stats]
    if missing:
        raise ValueError(f"Invalid policy.stats: missing required keys: {missing}")
    return stats


def _require_policy_score_buckets(policy: dict) -> list[dict]:
    """Return policy['score_buckets'] and fail fast if missing or malformed."""
    if "score_buckets" not in policy:
        raise ValueError("Invalid policy: missing score_buckets section")
    buckets = policy["score_buckets"]
    if not isinstance(buckets, list) or not buckets:
        raise ValueError("Invalid policy.score_buckets: must be a non-empty list")
    for idx, bucket in enumerate(buckets):
        if not isinstance(bucket, dict):
            raise ValueError(f"Invalid policy.score_buckets[{idx}]: must be an object")
        if not bucket.get("name"):
            raise ValueError(
                f"Invalid policy.score_buckets[{idx}]: missing required key 'name'"
            )
    return buckets


def _derive_failure_reasons(
    dq_reasons: list[str],
    *,
    is_pending: bool = False,
) -> list[str]:
    """Map lower-level data-quality reasons to canonical failure reasons."""
    dq = set(dq_reasons)

    if "join_key_missing" in dq:
        return ["join_key_missing"]
    if "benchmark_missing" in dq:
        return ["benchmark_missing"]
    if is_pending or "pending_t5" in dq:
        return ["insufficient_sample"]
    if "audit_only_decision" in dq:
        return ["gate_rule_wrong"]
    if (
        "market_data_default_used" in dq
        or "market_data_stale" in dq
        or "market_data_fallback_used" in dq
        or "invalid_price_series" in dq
    ):
        return ["market_data_bad"]
    if "provider_untrusted" in dq:
        return ["provider_bad"]
    if "provenance_field_missing" in dq or "mock_test_rejected" in dq:
        return ["source_bad"]
    if "symbol_missing" in dq or "direction_missing" in dq:
        return ["source_bad"]
    if "decision_price_missing" in dq or "decision_price_source_missing" in dq:
        return ["execution_missing"]
    if "decision_price_source_non_live" in dq:
        return ["market_data_bad"]
    return []

# ---------------------------------------------------------------------------
# Data quality classification helpers
# ---------------------------------------------------------------------------

def _classify_data_quality(
    record: dict,
    policy: dict,
    *,
    is_mock_or_test: bool = False,
    is_pending: bool = False,
) -> tuple[str, list[str]]:
    """Return (data_quality_label, reasons)."""
    dq_policy = policy.get("data_quality", {})
    invalid_conditions = set(dq_policy.get("invalid_if", []))
    degraded_conditions = set(dq_policy.get("degraded_if", []))

    reasons: list[str] = []

    # Check invalid conditions
    for cond in invalid_conditions:
        if _check_condition(record, cond):
            reasons.append(cond)

    if reasons:
        return ("invalid", reasons)

    # Mock/test exclusion
    if is_mock_or_test:
        return ("invalid", ["mock_test_rejected"])

    # Pending
    if is_pending:
        return ("pending", ["pending_t5"])

    # Check degraded conditions
    for cond in degraded_conditions:
        if _check_condition(record, cond):
            reasons.append(cond)

    if reasons:
        return ("degraded", reasons)

    return ("valid", [])


def _check_condition(record: dict, condition: str) -> bool:
    """Check a single data quality condition against a joined record."""
    if condition == "join_key_missing":
        # A valid join key requires both trace_id and event_hash.
        return (not record.get("trace_id")) or (not record.get("event_hash"))
    if condition == "symbol_missing":
        return not record.get("symbol")
    if condition == "direction_missing":
        return not record.get("direction")
    if condition == "decision_price_missing":
        return record.get("decision_price") is None
    if condition == "exit_price_missing_after_due":
        return record.get("exit_price_missing_after_due", False)
    if condition == "market_data_default_used":
        return record.get("market_data_default_used", False)
    if condition == "invalid_price_series":
        return record.get("invalid_price_series", False)
    if condition == "market_data_stale":
        return record.get("market_data_stale", False)
    if condition == "market_data_fallback_used":
        return record.get("market_data_fallback_used", False)
    if condition == "provider_untrusted":
        return record.get("provider_untrusted", False)
    if condition == "provenance_field_missing":
        return bool(record.get("provenance_field_missing"))
    if condition == "benchmark_missing":
        return record.get("benchmark_missing", False)
    if condition == "decision_price_source_missing":
        src = record.get("decision_price_source")
        return src is None or str(src).strip() in ("", "missing")
    if condition == "decision_price_source_non_live":
        src = record.get("decision_price_source")
        if src is None or str(src).strip() in ("", "missing"):
            return False  # already handled by decision_price_source_missing
        return str(src) != "live"
    return False


# ---------------------------------------------------------------------------
# Outcome label helpers (B's rules from the execution plan)
# ---------------------------------------------------------------------------

def _classify_execute_outcome(
    record: dict,
    policy: dict,
) -> tuple[str, Optional[str], list[str]]:
    """Classify EXECUTE decisions: hit/miss/neutral."""
    direction = record.get("direction", "")
    t5_return = record.get("t5_return")
    alpha_t5 = record.get("sector_relative_alpha_t5")
    thresholds = _require_policy_thresholds(policy)

    if direction == "LONG":
        ret_hit = thresholds["long_hit_return_t5"]
        alpha_hit = thresholds["long_hit_alpha_t5"]
        ret_miss = thresholds["long_miss_return_t5"]
        alpha_miss = thresholds["long_miss_alpha_t5"]

        if (t5_return is not None and t5_return >= ret_hit) or \
           (alpha_t5 is not None and alpha_t5 >= alpha_hit):
            return ("resolved_t5", "hit", [])
        elif (t5_return is not None and t5_return <= ret_miss) or \
             (alpha_t5 is not None and alpha_t5 <= alpha_miss):
            return ("resolved_t5", "miss", [])
        else:
            return ("resolved_t5", "neutral", [])

    elif direction == "SHORT":
        ret_hit = thresholds["short_hit_return_t5"]
        alpha_hit = thresholds["short_hit_alpha_t5"]
        ret_miss = thresholds["short_miss_return_t5"]
        alpha_miss = thresholds["short_miss_alpha_t5"]

        if (t5_return is not None and t5_return <= ret_hit) or \
           (alpha_t5 is not None and alpha_t5 <= alpha_hit):
            return ("resolved_t5", "hit", [])
        elif (t5_return is not None and t5_return >= ret_miss) or \
             (alpha_t5 is not None and alpha_t5 >= alpha_miss):
            return ("resolved_t5", "miss", [])
        else:
            return ("resolved_t5", "neutral", [])

    # Direction missing
    return ("resolved_t5", None, ["direction_missing"])


def _classify_watch_outcome(
    record: dict,
    policy: dict,
) -> tuple[str, Optional[str], list[str]]:
    """Classify WATCH decisions: missed_opportunity/correct_watch/neutral_watch."""
    direction = record.get("direction", "")
    t5_return = record.get("t5_return")
    alpha_t5 = record.get("sector_relative_alpha_t5")
    thresholds = _require_policy_thresholds(policy)

    # Determine what "hit" would mean for this direction
    if direction == "LONG":
        ret_hit = thresholds["long_hit_return_t5"]
        alpha_hit = thresholds["long_hit_alpha_t5"]
        ret_miss = thresholds["long_miss_return_t5"]
        alpha_miss = thresholds["long_miss_alpha_t5"]

        would_hit = (t5_return is not None and t5_return >= ret_hit) or \
                    (alpha_t5 is not None and alpha_t5 >= alpha_hit)
        would_miss = (t5_return is not None and t5_return <= ret_miss) or \
                     (alpha_t5 is not None and alpha_t5 <= alpha_miss)
    elif direction == "SHORT":
        ret_hit = thresholds["short_hit_return_t5"]
        alpha_hit = thresholds["short_hit_alpha_t5"]
        ret_miss = thresholds["short_miss_return_t5"]
        alpha_miss = thresholds["short_miss_alpha_t5"]

        would_hit = (t5_return is not None and t5_return <= ret_hit) or \
                    (alpha_t5 is not None and alpha_t5 <= alpha_hit)
        would_miss = (t5_return is not None and t5_return >= ret_miss) or \
                     (alpha_t5 is not None and alpha_t5 >= alpha_miss)
    else:
        # No direction info; treat as insufficient evidence
        return ("resolved_t5", "neutral_watch", ["direction_missing"])

    if would_hit:
        return ("resolved_t5", "missed_opportunity", [])
    elif would_miss:
        return ("resolved_t5", "correct_watch", [])
    else:
        return ("resolved_t5", "neutral_watch", [])


def _classify_block_outcome(
    record: dict,
    policy: dict,
) -> tuple[str, Optional[str], list[str]]:
    """Classify BLOCK decisions: correct_block/overblocked/neutral_block."""
    direction = record.get("direction", "")
    t5_return = record.get("t5_return")
    alpha_t5 = record.get("sector_relative_alpha_t5")
    thresholds = _require_policy_thresholds(policy)

    if direction == "LONG":
        ret_hit = thresholds["long_hit_return_t5"]
        alpha_hit = thresholds["long_hit_alpha_t5"]
        ret_miss = thresholds["long_miss_return_t5"]
        alpha_miss = thresholds["long_miss_alpha_t5"]

        would_hit = (t5_return is not None and t5_return >= ret_hit) or \
                    (alpha_t5 is not None and alpha_t5 >= alpha_hit)
        would_miss = (t5_return is not None and t5_return <= ret_miss) or \
                     (alpha_t5 is not None and alpha_t5 <= alpha_miss)
    elif direction == "SHORT":
        ret_hit = thresholds["short_hit_return_t5"]
        alpha_hit = thresholds["short_hit_alpha_t5"]
        ret_miss = thresholds["short_miss_return_t5"]
        alpha_miss = thresholds["short_miss_alpha_t5"]

        would_hit = (t5_return is not None and t5_return <= ret_hit) or \
                    (alpha_t5 is not None and alpha_t5 <= alpha_hit)
        would_miss = (t5_return is not None and t5_return >= ret_miss) or \
                     (alpha_t5 is not None and alpha_t5 >= alpha_miss)
    else:
        return ("resolved_t5", "neutral_block", ["direction_missing"])

    if would_miss:
        return ("resolved_t5", "correct_block", [])
    elif would_hit:
        return ("resolved_t5", "overblocked", [])
    else:
        return ("resolved_t5", "neutral_block", [])


def _should_be_pending(record: dict) -> bool:
    """Check if the record is pending (not enough time for T+5)."""
    return record.get("pending_t5", False) or record.get("outcome_status", "").startswith("pending")


def _is_mock_or_test(record: dict) -> bool:
    """Check if the record is from mock/test source."""
    source = record.get("log_source", "")
    return source in ("mock", "test", "fixture")


# ---------------------------------------------------------------------------
# Log readers
# ---------------------------------------------------------------------------

def _read_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file, skipping empty lines."""
    if not path.exists():
        return []
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def _normalize_gate_result(raw: str) -> Optional[str]:
    """Normalize gate_result to schema-allowed values: PASS, BLOCK, DEGRADED, or None."""
    if raw is None:
        return None
    raw_upper = str(raw).upper()
    if raw_upper in ("PASS", "PASSED"):
        return "PASS"
    if raw_upper in ("BLOCK", "BLOCKED"):
        return "BLOCK"
    if raw_upper == "DEGRADED":
        return "DEGRADED"
    if raw_upper == "WATCH":
        return "DEGRADED"  # WATCH is not a gate_result in schema; treat as degraded
    return None


def _make_join_key(record: dict) -> Optional[str]:
    """Create a join key from trace_id and event_hash.

    A complete join key requires both fields. If only one field is present,
    return a partial key so the record can still be grouped for auditing,
    but the record will be marked join_key_invalid downstream.
    """
    tid = record.get("trace_id", "")
    ehash = record.get("event_hash", "")
    if tid and ehash:
        return f"{tid}|{ehash}"
    if tid:
        return f"{tid}|"
    if ehash:
        return f"|{ehash}"
    return None


# ---------------------------------------------------------------------------
# Log trust reporting
# ---------------------------------------------------------------------------

def _build_log_trust(
    opp_id: str,
    log_source: str,
    join_key_valid: bool,
    timestamp_valid: bool,
    data_quality: str,
    data_quality_reasons: list[str],
    missing_join_fields: list[str],
) -> dict:
    """Build a log_trust record."""
    return {
        "schema_version": SCHEMA_LOG_TRUST,
        "opportunity_id": opp_id,
        "log_source": log_source,
        "join_key_valid": join_key_valid,
        "timestamp_valid": timestamp_valid,
        "join_key_type": "trace_id|event_hash",
        "missing_join_fields": missing_join_fields,
        "data_quality": data_quality,
        "data_quality_reasons": data_quality_reasons,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Score bucket assignment
# ---------------------------------------------------------------------------

def _assign_score_bucket(score: Optional[float], policy: dict) -> Optional[str]:
    """Assign score to a bucket based on policy."""
    if score is None:
        return None
    buckets = _require_policy_score_buckets(policy)
    for bucket in buckets:
        name = bucket["name"]
        mn = bucket.get("min")
        mx = bucket.get("max")
        if mn is not None and score < mn:
            continue
        if mx is not None and score >= mx:
            continue
        return name
    return None


# ---------------------------------------------------------------------------
# Score monotonicity
# ---------------------------------------------------------------------------

def _compute_monotonicity(
    buckets_data: list[dict],
    policy: dict,
) -> dict:
    """Compute score monotonicity across buckets."""
    stats = _require_policy_stats(policy)
    min_sample = stats["min_bucket_sample_size"]
    min_total = stats["min_total_sample_size"]

    total_samples = sum(b["sample_size"] for b in buckets_data)

    # Check if any bucket has insufficient sample
    for b in buckets_data:
        if b["sample_size"] < min_sample:
            return {
                "status": "insufficient_sample",
                "reason": f"bucket {b['name']} has {b['sample_size']} samples, min required {min_sample}",
                "total_samples": total_samples,
                "min_required_total": min_total,
            }

    if total_samples < min_total:
        return {
            "status": "insufficient_sample",
            "reason": f"total samples {total_samples} below min {min_total}",
            "total_samples": total_samples,
            "min_required_total": min_total,
        }

    # Check monotonicity of avg_alpha_t5
    alphas = [b.get("avg_alpha_t5") for b in buckets_data if b.get("avg_alpha_t5") is not None]
    hit_rates = [b.get("hit_rate_t5") for b in buckets_data if b.get("hit_rate_t5") is not None]

    alpha_monotonic = all(
        alphas[i] >= alphas[i + 1]
        for i in range(len(alphas) - 1)
        if alphas[i] is not None and alphas[i + 1] is not None
    )

    hr_monotonic = all(
        hit_rates[i] >= hit_rates[i + 1]
        for i in range(len(hit_rates) - 1)
        if hit_rates[i] is not None and hit_rates[i + 1] is not None
    )

    if alpha_monotonic and hr_monotonic:
        return {"status": "passed", "total_samples": total_samples}
    elif alpha_monotonic:
        return {
            "status": "passed_with_warning",
            "warning": "avg_alpha_t5 monotonic but hit_rate_t5 not monotonic",
            "total_samples": total_samples,
        }
    else:
        return {"status": "failed", "total_samples": total_samples}


# ---------------------------------------------------------------------------
# Summary statistics
# ---------------------------------------------------------------------------

def _compute_summary(opportunities: list[dict]) -> dict:
    """Compute outcome summary statistics."""
    total = len(opportunities)
    valid = [o for o in opportunities if o["data_quality"] == "valid"]
    degraded = [o for o in opportunities if o["data_quality"] == "degraded"]
    invalid = [o for o in opportunities if o["data_quality"] == "invalid"]
    pending = [o for o in opportunities if o["data_quality"] == "pending"]
    matured = [o for o in opportunities if o["data_quality"] != "pending"]

    resolved_valid = [o for o in valid if "resolved" in o.get("outcome_status", "")]
    hits = [o for o in resolved_valid if o.get("outcome_label") == "hit"]
    misses = [o for o in resolved_valid if o.get("outcome_label") == "miss"]

    execute_decisions = [o for o in opportunities if o.get("action_after_gate") == "EXECUTE"]
    watch_decisions = [o for o in opportunities if o.get("action_after_gate") == "WATCH"]
    block_decisions = [o for o in opportunities if o.get("action_after_gate") == "BLOCK"]

    overblocked = [o for o in opportunities if o.get("outcome_label") == "overblocked"]
    correct_block = [o for o in opportunities if o.get("outcome_label") == "correct_block"]
    missed_opp = [o for o in opportunities if o.get("outcome_label") == "missed_opportunity"]

    # avg_alpha_t5
    alphas = [o.get("sector_relative_alpha_t5") for o in resolved_valid
              if o.get("sector_relative_alpha_t5") is not None]
    avg_alpha = sum(alphas) / len(alphas) if alphas else None

    # avg_return_t5
    returns = [o.get("t5_return") for o in resolved_valid
               if o.get("t5_return") is not None]
    avg_return = sum(returns) / len(returns) if returns else None

    # Benchmark missing count (detected from data_quality_reasons)
    benchmark_missing_count = sum(
        1 for o in resolved_valid
        if "benchmark_missing" in o.get("data_quality_reasons", [])
    )

    # Mapping failures
    mapping_failures = sum(
        1 for o in opportunities
        if "join_key_missing" in o.get("data_quality_reasons", []) or
           o.get("outcome_status") == "invalid_join_key"
    )

    # Coverage metrics required by metric_dictionary
    execute_with_outcome_count = sum(
        1 for o in execute_decisions if o.get("outcome_status") is not None
    )
    linked_outcome_count = sum(
        1 for o in opportunities if o.get("trace_id") and o.get("event_hash")
    )
    records_requiring_failure_reason = [
        o for o in opportunities
        if o.get("data_quality") in ("degraded", "invalid", "pending") or o.get("failure_reasons")
    ]
    records_with_primary_failure_reason = sum(
        1 for o in records_requiring_failure_reason if o.get("primary_failure_reason")
    )

    return {
        "total_opportunities": total,
        "valid_outcome_count": len(valid),
        "degraded_outcome_count": len(degraded),
        "invalid_outcome_count": len(invalid),
        "pending_outcome_count": len(pending),
        "valid_resolved_t5_count": len(resolved_valid),
        "hit_count_t5": len(hits),
        "miss_count_t5": len(misses),
        "avg_alpha_t5": round(avg_alpha, 2) if avg_alpha is not None else None,
        "avg_return_t5": round(avg_return, 2) if avg_return is not None else None,
        "hit_rate_t5": round(len(hits) / len(resolved_valid), 4) if resolved_valid else None,
        "execute_decision_count": len(execute_decisions),
        "watch_decision_count": len(watch_decisions),
        "block_decision_count": len(block_decisions),
        "overblocked_count": len(overblocked),
        "correct_block_count": len(correct_block),
        "missed_opportunity_count": len(missed_opp),
        "overblock_rate": round(len(overblocked) / len(block_decisions), 4) if block_decisions else None,
        "correct_block_rate": round(len(correct_block) / len(block_decisions), 4) if block_decisions else None,
        "missed_opportunity_rate": round(len(missed_opp) / len(watch_decisions), 4) if watch_decisions else None,
        "benchmark_missing_count": benchmark_missing_count,
        "mapping_failure_count": mapping_failures,
        "mapping_failure_rate": round(mapping_failures / total, 4) if total else None,
        "outcome_record_coverage_rate": round(
            (len(valid) + len(degraded) + len(invalid) + len(pending)) / total, 4
        ) if total else None,
        "resolved_outcome_coverage_rate": round(
            (len(valid) + len(degraded) + len(invalid)) / len(matured), 4
        ) if matured else None,
        "pending_outcome_rate": round(len(pending) / total, 4) if total else None,
        "execute_outcome_coverage_rate": round(
            execute_with_outcome_count / len(execute_decisions), 4
        ) if execute_decisions else None,
        "join_key_link_rate": round(linked_outcome_count / total, 4) if total else None,
        "failure_reason_coverage_rate": round(
            records_with_primary_failure_reason / len(records_requiring_failure_reason), 4
        ) if records_requiring_failure_reason else None,
    }


def _compute_failure_distribution(opportunities: list[dict]) -> dict:
    """Compute distribution of failure reasons."""
    dist: dict[str, int] = defaultdict(int)
    for o in opportunities:
        reasons = {
            reason
            for reason in [o.get("primary_failure_reason"), *o.get("failure_reasons", [])]
            if reason
        }
        for reason in reasons:
            dist[reason] += 1
    return dict(sorted(dist.items()))


def _compute_score_buckets(opportunities: list[dict], policy: dict) -> list[dict]:
    """Compute per-bucket statistics for valid resolved outcomes."""
    valid_resolved = [
        o for o in opportunities
        if o["data_quality"] == "valid" and "resolved" in o.get("outcome_status", "")
    ]

    buckets_map: dict[str, list[dict]] = defaultdict(list)
    for o in valid_resolved:
        bucket = o.get("score_bucket")
        if bucket:
            buckets_map[bucket].append(o)

    bucket_order = [b["name"] for b in _require_policy_score_buckets(policy)]
    result = []
    for name in bucket_order:
        recs = buckets_map.get(name, [])
        hits = [r for r in recs if r.get("outcome_label") == "hit"]
        alphas = [r.get("sector_relative_alpha_t5") for r in recs
                  if r.get("sector_relative_alpha_t5") is not None]

        result.append({
            "name": name,
            "sample_size": len(recs),
            "hit_rate_t5": round(len(hits) / len(recs), 4) if recs else None,
            "avg_alpha_t5": round(sum(alphas) / len(alphas), 2) if alphas else None,
        })
    return result


def _compute_alpha_report(opportunities: list[dict], policy: dict) -> dict:
    """Compute alpha report (benchmark-relative performance)."""
    valid_resolved = [
        o for o in opportunities
        if o["data_quality"] == "valid" and "resolved" in o.get("outcome_status", "")
    ]

    # Exclude benchmark_missing from alpha primary stats
    alpha_eligible = [
        o for o in valid_resolved
        if "benchmark_missing" not in o.get("data_quality_reasons", [])
    ]
    benchmark_missing_excluded = sum(
        1 for o in valid_resolved
        if "benchmark_missing" in o.get("data_quality_reasons", [])
    )

    alphas = [o.get("sector_relative_alpha_t5") for o in alpha_eligible
              if o.get("sector_relative_alpha_t5") is not None]
    returns = [o.get("t5_return") for o in alpha_eligible
               if o.get("t5_return") is not None]
    benchmarks = [o.get("benchmark_return_t5") for o in alpha_eligible
                  if o.get("benchmark_return_t5") is not None]

    return {
        "alpha_eligible_count": len(alpha_eligible),
        "benchmark_missing_excluded": benchmark_missing_excluded,
        "mean_alpha_t5": round(sum(alphas) / len(alphas), 4) if alphas else None,
        "mean_return_t5": round(sum(returns) / len(returns), 4) if returns else None,
        "mean_benchmark_return_t5": round(sum(benchmarks) / len(benchmarks), 4) if benchmarks else None,
        "positive_alpha_count": sum(1 for a in alphas if a > 0),
        "negative_alpha_count": sum(1 for a in alphas if a < 0),
        "zero_alpha_count": sum(1 for a in alphas if a == 0),
    }


def _compute_decision_suggestions(opportunities: list[dict]) -> list[dict]:
    """Generate decision suggestions for human review only."""
    suggestions = []
    for o in opportunities:
        if o.get("outcome_label") in ("overblocked",):
            suggestions.append({
                "opportunity_id": o["opportunity_id"],
                "suggestion_type": "review_block_rules",
                "action_after_gate": o.get("action_after_gate"),
                "outcome_label": o["outcome_label"],
                "rationale": "Blocked opportunity later proved profitable. Consider reviewing gate rules.",
                "requires_human_review": True,
            })
        elif o.get("outcome_label") == "missed_opportunity":
            suggestions.append({
                "opportunity_id": o["opportunity_id"],
                "suggestion_type": "review_watch_rules",
                "action_after_gate": o.get("action_after_gate"),
                "outcome_label": o["outcome_label"],
                "rationale": "Watched opportunity later proved profitable. Consider adjusting watch criteria.",
                "requires_human_review": True,
            })
    return suggestions


# ---------------------------------------------------------------------------
# Outcome record builder
# ---------------------------------------------------------------------------

def _build_outcome_record(
    opportunity_id: str,
    joined: dict,
    policy: dict,
    is_pending: bool,
    is_mock_or_test: bool,
) -> dict:
    """Build a single opportunity_outcome record."""
    action_after_gate = joined.get("action_after_gate", "UNKNOWN")
    data_quality, dq_reasons = _classify_data_quality(
        joined, policy, is_mock_or_test=is_mock_or_test, is_pending=is_pending,
    )

    # Determine outcome status and label
    outcome_status = "pending_t5" if (is_pending and not is_mock_or_test) else "resolved_t5"
    outcome_label: Optional[str] = None
    failure_reasons: list[str] = []

    if data_quality == "valid" and not is_pending:
        if action_after_gate == "EXECUTE":
            outcome_status, outcome_label, failure_reasons = _classify_execute_outcome(joined, policy)
        elif action_after_gate == "WATCH":
            outcome_status, outcome_label, failure_reasons = _classify_watch_outcome(joined, policy)
        elif action_after_gate == "BLOCK":
            outcome_status, outcome_label, failure_reasons = _classify_block_outcome(joined, policy)
        elif action_after_gate in ("PENDING_CONFIRM", "UNKNOWN"):
            # Audit-only: cannot be hit/miss, cannot be valid
            data_quality = "degraded"
            dq_reasons.append("audit_only_decision")
            outcome_label = None

    # Handle data quality issues that affect outcome
    if data_quality in ("degraded", "invalid", "pending"):
        outcome_label = None
        # Map lower-level data quality issues onto the canonical failure enum.
        failure_reasons.extend(
            reason for reason in _derive_failure_reasons(dq_reasons, is_pending=is_pending)
            if reason in FAILURE_REASONS
        )

    # Handle specific failure reason conditions
    if joined.get("benchmark_missing"):
        if "benchmark_missing" not in failure_reasons:
            failure_reasons.append("benchmark_missing")

    if "join_key_missing" in dq_reasons:
        outcome_status = "invalid_join_key"
        if "join_key_missing" not in failure_reasons:
            failure_reasons.append("join_key_missing")

    if "symbol_missing" in dq_reasons:
        outcome_status = "symbol_untradeable"

    if "invalid_price_series" in dq_reasons:
        outcome_status = "invalid_price_series"

    if "market_data_default_used" in dq_reasons or "market_data_fallback_used" in dq_reasons:
        outcome_status = "insufficient_market_data"

    # Ensure pending outcomes don't emit hit/miss
    if is_pending:
        outcome_label = None
        data_quality = "pending"

    # Unique failure reasons
    failure_reasons = sorted(set(failure_reasons))
    primary_failure_reason: Optional[str] = None
    if failure_reasons:
        primary_failure_reason = failure_reasons[0]

    score = joined.get("score")
    score_bucket = _assign_score_bucket(score, policy)

    record = {
        "schema_version": SCHEMA_OUTCOME,
        "opportunity_id": opportunity_id,
        "trace_id": joined.get("trace_id"),
        "event_trace_id": joined.get("event_trace_id"),
        "request_id": joined.get("request_id"),
        "batch_id": joined.get("batch_id"),
        "event_hash": joined.get("event_hash"),
        "decision_id": joined.get("decision_id"),
        "execution_id": joined.get("execution_id"),
        "symbol": joined.get("symbol"),
        "direction": joined.get("direction"),
        "action_before_gate": joined.get("action_before_gate"),
        "action_after_gate": action_after_gate,
        "gate_result": joined.get("gate_result"),
        "triggered_rules": joined.get("triggered_rules", []),
        "reject_reason_code": joined.get("reject_reason_code"),
        "score": score,
        "score_bucket": score_bucket,
        "grade": joined.get("grade"),
        "event_type": joined.get("event_type"),
        "sector": joined.get("sector"),
        "market_regime": joined.get("market_regime"),
        "decision_ts": joined.get("decision_ts"),
        "decision_price": joined.get("decision_price"),
        "actual_entry_ts": joined.get("actual_entry_ts"),
        "actual_entry_price": joined.get("actual_entry_price"),
        "entry_price_type": joined.get("entry_price_type"),
        "benchmark_symbol": joined.get("benchmark_symbol"),
        "sector_benchmark_symbol": joined.get("sector_benchmark_symbol"),
        "t1_return": joined.get("t1_return"),
        "t5_return": joined.get("t5_return"),
        "t20_return": joined.get("t20_return"),
        "benchmark_return_t5": joined.get("benchmark_return_t5"),
        "sector_relative_alpha_t5": joined.get("sector_relative_alpha_t5"),
        "max_drawdown_t5": joined.get("max_drawdown_t5"),
        "max_upside_t5": joined.get("max_upside_t5"),
        "outcome_status": outcome_status,
        "outcome_label": outcome_label,
        "primary_failure_reason": primary_failure_reason,
        "failure_reasons": failure_reasons,
        "data_quality": data_quality,
        "data_quality_reasons": dq_reasons,
        "provenance_field_missing": joined.get("provenance_field_missing", []),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return record


# ---------------------------------------------------------------------------
# Mapping attribution builder
# ---------------------------------------------------------------------------

def _build_mapping_attribution(opportunity_id: str, joined: dict, outcome: Optional[dict] = None) -> dict:
    """Build mapping attribution record."""
    mapping_status = "mapping_success"
    mapping_failure: Optional[str] = None

    # Prefer the finalized outcome-level data quality reasons so mapping status
    # stays semantically aligned with outcome classification.
    dq_reasons = []
    if outcome is not None:
        dq_reasons = outcome.get("data_quality_reasons", []) or []
    if not dq_reasons:
        dq_reasons = joined.get("data_quality_reasons", []) or []
    if "join_key_missing" in dq_reasons:
        mapping_status = "join_key_missing"
        mapping_failure = "join_key_missing"
    elif joined.get("mapping_failure"):
        mapping_status = "mapping_wrong"
        mapping_failure = joined.get("mapping_failure")

    return {
        "schema_version": SCHEMA_MAPPING,
        "opportunity_id": opportunity_id,
        "trace_id": joined.get("trace_id"),
        "mapping_status": mapping_status,
        "mapping_failure_reason": mapping_failure,
        "mapped_sector": joined.get("sector"),
        "mapped_industry": joined.get("industry"),
        "confidence_score": joined.get("confidence_score"),
        "provenance_field_missing": joined.get("provenance_field_missing", []),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Core engine
# ---------------------------------------------------------------------------

def _compute_idempotency_key(opportunity_id: str) -> str:
    """Generate a stable idempotency key for an opportunity."""
    return hashlib.sha256(opportunity_id.encode()).hexdigest()[:32]


def run_engine(
    logs_dir: Path,
    out_dir: Path,
    policy_path: Optional[Path] = None,
    metric_dictionary_path: Optional[Path] = None,
    horizon: str = "t5",
    emit_report: bool = True,
) -> dict:
    """Run the outcome attribution engine.

    Returns a dict with paths to generated files.
    """
    import datetime as dt

    # Resolve paths
    if policy_path is None:
        policy_path = REPO_ROOT / "configs" / "outcome_scoring_policy.yaml"
    if metric_dictionary_path is None:
        metric_dictionary_path = REPO_ROOT / "configs" / "metric_dictionary.yaml"

    # Load policy
    with open(policy_path, "r", encoding="utf-8") as f:
        policy = yaml.safe_load(f)

    # Load metric dictionary
    with open(metric_dictionary_path, "r", encoding="utf-8") as f:
        metric_dict = yaml.safe_load(f)

    # Read input logs
    decision_gate_logs = _read_jsonl(logs_dir / "decision_gate.jsonl")
    execution_emit_logs = _read_jsonl(logs_dir / "execution_emit.jsonl")
    replay_write_logs = _read_jsonl(logs_dir / "replay_write.jsonl")
    trace_scorecard_logs = _read_jsonl(logs_dir / "trace_scorecard.jsonl")
    market_data_logs = _read_jsonl(logs_dir / "market_data_provenance.jsonl")

    # Index logs by join key
    def _index_by_key(logs: list[dict]) -> dict[str, list[dict]]:
        idx: dict[str, list[dict]] = defaultdict(list)
        for rec in logs:
            key = _make_join_key(rec)
            if key:
                idx[key].append(rec)
        return idx

    decision_idx = _index_by_key(decision_gate_logs)
    execution_idx = _index_by_key(execution_emit_logs)
    replay_idx = _index_by_key(replay_write_logs)
    scorecard_idx = _index_by_key(trace_scorecard_logs)
    market_idx = _index_by_key(market_data_logs)

    # Collect all unique join keys
    all_keys = set()
    all_keys.update(decision_idx.keys())
    all_keys.update(execution_idx.keys())
    all_keys.update(replay_idx.keys())
    all_keys.update(scorecard_idx.keys())
    all_keys.update(market_idx.keys())

    # Join and build outcome records
    opportunities: list[dict] = []
    mapping_attributions: list[dict] = []
    log_trust_records: list[dict] = []

    opp_counter = 0
    for key in sorted(all_keys):
        opp_counter += 1
        opportunity_id = f"opp-{opp_counter:06d}"

        # Gather related records
        decisions = decision_idx.get(key, [])
        executions = execution_idx.get(key, [])
        replays = replay_idx.get(key, [])
        scorecards = scorecard_idx.get(key, [])
        market_records = market_idx.get(key, [])

        # Build joined record
        joined: dict = {}

        # From decision_gate
        if decisions:
            d = decisions[0]
            # Normalize gate_result: schema allows only PASS/BLOCK/DEGRADED/null
            raw_gate = d.get("gate_result", "")
            gate_result = _normalize_gate_result(raw_gate)
            joined.update({
                "trace_id": d.get("trace_id"),
                "event_trace_id": d.get("event_trace_id"),
                "request_id": d.get("request_id"),
                "batch_id": d.get("batch_id"),
                "event_hash": d.get("event_hash"),
                "action_after_gate": d.get("final_action_after_gate") or d.get("final_action", "UNKNOWN"),
                "action_before_gate": d.get("final_action_before_gate"),
                "gate_result": gate_result,
                "triggered_rules": d.get("triggered_rules", []),
                "reject_reason_code": d.get("reject_reason_code"),
                "decision_ts": d.get("logged_at"),
            })
            # Try to get score from gate output
            gate_output = d.get("gate_output", {})
            joined["score"] = gate_output.get("decision_summary", {}).get("score") if isinstance(gate_output, dict) else None

        # From trace_scorecard
        if scorecards:
            s = scorecards[0]
            decision_price = s.get("decision_price")
            decision_price_source = s.get("decision_price_source")
            # Backward compatibility for legacy scorecards:
            # when decision_price exists but source is missing, treat it as live.
            if decision_price is not None and (decision_price_source is None or str(decision_price_source).strip() == ""):
                decision_price_source = "live"
            joined.update({
                "event_type": s.get("semantic_event_type"),
                "sector": (s.get("sector_candidates", [None]) or [None])[0],
                "symbol": _extract_symbol(s),
                "direction": _extract_direction(s),
                "scores": s.get("scores"),
                "grade": (s.get("scores") or {}).get("grade"),
                "a1_score": s.get("a1_score"),
                # Outcome attribution fields
                "t5_return": s.get("t5_return"),
                "t1_return": s.get("t1_return"),
                "t20_return": s.get("t20_return"),
                "sector_relative_alpha_t5": s.get("sector_relative_alpha_t5"),
                "benchmark_return_t5": s.get("benchmark_return_t5"),
                "benchmark_missing": s.get("benchmark_missing", False),
                "pending_t5": s.get("pending_t5", False),
                "log_source": s.get("log_source", ""),
                "decision_price": decision_price,
                "decision_price_source": decision_price_source,
                "decision_prices_by_symbol": s.get("decision_prices_by_symbol", {}),
                "benchmark_symbol": s.get("benchmark_symbol"),
                "sector_benchmark_symbol": s.get("sector_benchmark_symbol"),
            })
            # Try to get score from scores block
            if "score" not in joined or joined["score"] is None:
                sc = s.get("scores", {})
                joined["score"] = sc.get("total_score")

        # From market_data
        if market_records:
            m = market_records[0]
            joined.update({
                "market_data_default_used": m.get("market_data_default_used", False),
                "market_data_stale": m.get("market_data_stale", False),
                "market_data_fallback_used": m.get("market_data_fallback_used", False),
                "provenance_field_missing": m.get("provenance_field_missing", []),
                "market_data_source": m.get("market_data_source"),
            })

        # From execution_emit
        if executions:
            e = executions[0]
            joined.update({
                "execution_id": e.get("execution_id"),
                "actual_entry_ts": e.get("actual_entry_ts"),
                "actual_entry_price": e.get("actual_entry_price"),
                "decision_price": e.get("decision_price"),
                "entry_price_type": e.get("entry_price_type"),
            })

        # From replay_write
        if replays:
            r = replays[0]
            joined.update({
                "decision_id": r.get("event_hash"),
            })

        # Check join key validity
        join_key_valid = bool(joined.get("trace_id") and joined.get("event_hash"))

        # Prefer per-symbol decision price context when available (symbol-first).
        # This makes decision_price/source evaluation symbol-aware instead of event-level only.
        by_symbol = joined.get("decision_prices_by_symbol")
        sym = joined.get("symbol")
        if isinstance(by_symbol, dict) and sym and isinstance(by_symbol.get(sym), dict):
            sym_ctx = by_symbol.get(sym) or {}
            if "decision_price" in sym_ctx:
                joined["decision_price"] = sym_ctx.get("decision_price")
            if "decision_price_source" in sym_ctx:
                joined["decision_price_source"] = sym_ctx.get("decision_price_source")
            if "needs_price_refresh" in sym_ctx:
                joined["needs_price_refresh"] = sym_ctx.get("needs_price_refresh")

        missing_join_fields: list[str] = []
        if not joined.get("trace_id"):
            missing_join_fields.append("trace_id")
        if not joined.get("event_hash"):
            missing_join_fields.append("event_hash")

        # Determine log_source
        log_source = "fixture"

        # Determine pending and mock/test status
        is_pending = _should_be_pending(joined)
        is_mock = _is_mock_or_test(joined)

        # Build outcome record
        outcome = _build_outcome_record(
            opportunity_id, joined, policy, is_pending, is_mock,
        )
        opportunities.append(outcome)

        # Build mapping attribution
        mapping = _build_mapping_attribution(opportunity_id, joined, outcome)
        mapping_attributions.append(mapping)

        # Build log trust
        log_trust = _build_log_trust(
            opportunity_id, log_source, join_key_valid,
            timestamp_valid=bool(joined.get("decision_ts")),
            data_quality=outcome["data_quality"],
            data_quality_reasons=outcome["data_quality_reasons"],
            missing_join_fields=missing_join_fields,
        )
        log_trust_records.append(log_trust)

    # Compute statistics
    summary = _compute_summary(opportunities)
    failure_dist = _compute_failure_distribution(opportunities)
    score_buckets = _compute_score_buckets(opportunities, policy)
    monotonicity = _compute_monotonicity(score_buckets, policy)
    alpha_report = _compute_alpha_report(opportunities, policy)
    decision_suggestions = _compute_decision_suggestions(opportunities)

    # Ensure output directory
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write output files
    generated_at = datetime.now(timezone.utc).isoformat()

    # opportunity_outcome.jsonl
    outcome_path = out_dir / "opportunity_outcome.jsonl"
    with open(outcome_path, "w", encoding="utf-8") as f:
        for o in opportunities:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")

    # outcome_summary.json
    summary_path = out_dir / "outcome_summary.json"
    summary_full = {
        "schema_version": "stage6.outcome_summary.v1",
        "generated_at": generated_at,
        "horizon": horizon,
        **summary,
        "score_monotonicity_status": monotonicity["status"],
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_full, f, ensure_ascii=False, indent=2)

    # outcome_by_score_bucket.json
    bucket_path = out_dir / "outcome_by_score_bucket.json"
    bucket_output = {
        "schema_version": SCHEMA_BUCKET,
        "generated_at": generated_at,
        "buckets": score_buckets,
    }
    with open(bucket_path, "w", encoding="utf-8") as f:
        json.dump(bucket_output, f, ensure_ascii=False, indent=2)

    # score_monotonicity_report.json
    mono_path = out_dir / "score_monotonicity_report.json"
    with open(mono_path, "w", encoding="utf-8") as f:
        json.dump(monotonicity, f, ensure_ascii=False, indent=2)

    # failure_reason_distribution.json
    fail_path = out_dir / "failure_reason_distribution.json"
    with open(fail_path, "w", encoding="utf-8") as f:
        json.dump(failure_dist, f, ensure_ascii=False, indent=2)

    # alpha_report.json
    alpha_path = out_dir / "alpha_report.json"
    with open(alpha_path, "w", encoding="utf-8") as f:
        json.dump(alpha_report, f, ensure_ascii=False, indent=2)

    # log_trust_report.json
    trust_path = out_dir / "log_trust_report.json"
    trust_summary = {
        "schema_version": "stage6.log_trust_report.v1",
        "generated_at": generated_at,
        "total_records": len(log_trust_records),
        "join_key_valid_count": sum(1 for lt in log_trust_records if lt["join_key_valid"]),
        "join_key_invalid_count": sum(1 for lt in log_trust_records if not lt["join_key_valid"]),
        "records": log_trust_records,
    }
    with open(trust_path, "w", encoding="utf-8") as f:
        json.dump(trust_summary, f, ensure_ascii=False, indent=2)

    # mapping_attribution.jsonl
    mapping_path = out_dir / "mapping_attribution.jsonl"
    with open(mapping_path, "w", encoding="utf-8") as f:
        for m in mapping_attributions:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")

    # decision_suggestions.json
    suggestions_path = out_dir / "decision_suggestions.json"
    with open(suggestions_path, "w", encoding="utf-8") as f:
        json.dump(decision_suggestions, f, ensure_ascii=False, indent=2)

    # outcome_report.md (if --emit-report)
    report_path = None
    if emit_report:
        report_path = out_dir / "outcome_report.md"
        report_content = _generate_markdown_report(
            summary, monotonicity, failure_dist, alpha_report, score_buckets, generated_at,
        )
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_content)

    return {
        "outcome_path": str(outcome_path),
        "summary_path": str(summary_path),
        "bucket_path": str(bucket_path),
        "mono_path": str(mono_path),
        "failure_path": str(fail_path),
        "alpha_path": str(alpha_path),
        "trust_path": str(trust_path),
        "mapping_path": str(mapping_path),
        "suggestions_path": str(suggestions_path),
        "report_path": str(report_path) if report_path else None,
        "total_opportunities": len(opportunities),
        "idempotency_key": _compute_idempotency_key(
            hashlib.sha256(json.dumps(summary, sort_keys=True).encode()).hexdigest()
        ),
    }


def _extract_symbol(scorecard: dict) -> Optional[str]:
    """Extract symbol from stock_candidates in trace_scorecard."""
    candidates = scorecard.get("stock_candidates", [])
    if candidates and isinstance(candidates, list) and len(candidates) > 0:
        return candidates[0].get("symbol") if isinstance(candidates[0], dict) else None
    return None


def _extract_direction(scorecard: dict) -> Optional[str]:
    """Extract direction from stock_candidates in trace_scorecard."""
    candidates = scorecard.get("stock_candidates", [])
    if candidates and isinstance(candidates, list) and len(candidates) > 0:
        d = candidates[0].get("direction") if isinstance(candidates[0], dict) else None
        if d:
            return d.upper()
    return None


def _generate_markdown_report(
    summary: dict,
    monotonicity: dict,
    failure_dist: dict,
    alpha_report: dict,
    score_buckets: list[dict],
    generated_at: str,
) -> str:
    """Generate a human-readable Markdown outcome report."""
    lines = [
        "# Stage6 Outcome Attribution Report",
        "",
        f"Generated: {generated_at}",
        "",
        "## Summary Statistics",
        "",
        f"- **Total Opportunities**: {summary.get('total_opportunities', 0)}",
        f"- **Valid Outcomes**: {summary.get('valid_outcome_count', 0)}",
        f"- **Degraded Outcomes**: {summary.get('degraded_outcome_count', 0)}",
        f"- **Invalid Outcomes**: {summary.get('invalid_outcome_count', 0)}",
        f"- **Pending Outcomes**: {summary.get('pending_outcome_count', 0)}",
        f"- **Valid Resolved (T+5)**: {summary.get('valid_resolved_t5_count', 0)}",
        "",
        "## Performance Metrics",
        "",
        f"- **Hit Rate (T+5)**: {summary.get('hit_rate_t5', 'N/A')}",
        f"- **Hit Count**: {summary.get('hit_count_t5', 0)}",
        f"- **Miss Count**: {summary.get('miss_count_t5', 0)}",
        f"- **Avg Alpha (T+5)**: {summary.get('avg_alpha_t5', 'N/A')}",
        f"- **Avg Return (T+5)**: {summary.get('avg_return_t5', 'N/A')}",
        "",
        "## Gate Quality",
        "",
        f"- **Overblock Rate**: {summary.get('overblock_rate', 'N/A')} ({summary.get('overblocked_count', 0)}/{summary.get('block_decision_count', 0)})",
        f"- **Correct Block Rate**: {summary.get('correct_block_rate', 'N/A')} ({summary.get('correct_block_count', 0)}/{summary.get('block_decision_count', 0)})",
        f"- **Missed Opportunity Rate**: {summary.get('missed_opportunity_rate', 'N/A')} ({summary.get('missed_opportunity_count', 0)}/{summary.get('watch_decision_count', 0)})",
        "",
        "## Score Monotonicity",
        "",
        f"- **Status**: {monotonicity.get('status', 'N/A')}",
    ]

    if monotonicity.get("reason"):
        lines.append(f"- **Reason**: {monotonicity['reason']}")
    if monotonicity.get("warning"):
        lines.append(f"- **Warning**: {monotonicity['warning']}")

    lines.extend([
        "",
        "## Score Buckets",
        "",
        "| Bucket | Samples | Hit Rate | Avg Alpha |",
        "|--------|---------|----------|-----------|",
    ])
    for b in score_buckets:
        lines.append(
            f"| {b['name']} | {b['sample_size']} | "
            f"{b.get('hit_rate_t5', 'N/A')} | {b.get('avg_alpha_t5', 'N/A')} |"
        )

    lines.extend([
        "",
        "## Alpha Report",
        "",
        f"- **Alpha-eligible count**: {alpha_report.get('alpha_eligible_count', 0)}",
        f"- **Benchmark-missing excluded**: {alpha_report.get('benchmark_missing_excluded', 0)}",
        f"- **Mean Alpha (T+5)**: {alpha_report.get('mean_alpha_t5', 'N/A')}",
        f"- **Mean Return (T+5)**: {alpha_report.get('mean_return_t5', 'N/A')}",
        f"- **Mean Benchmark Return**: {alpha_report.get('mean_benchmark_return_t5', 'N/A')}",
        f"- **Positive Alpha**: {alpha_report.get('positive_alpha_count', 0)}",
        f"- **Negative Alpha**: {alpha_report.get('negative_alpha_count', 0)}",
    ])

    if failure_dist:
        lines.extend([
            "",
            "## Failure Reason Distribution",
            "",
        ])
        for reason, count in sorted(failure_dist.items(), key=lambda x: -x[1]):
            lines.append(f"- **{reason}**: {count}")

    lines.extend([
        "",
        "---",
        "",
        "*This report is for human review only. Do not auto-consume by production execution modules.*",
    ])

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage6 Outcome Attribution Engine (PR-7b)",
    )
    parser.add_argument(
        "--logs-dir", required=True, type=Path,
        help="Directory containing input log files (decision_gate.jsonl, etc.)",
    )
    parser.add_argument(
        "--out-dir", required=True, type=Path,
        help="Directory to write output files",
    )
    parser.add_argument(
        "--policy", type=Path, default=None,
        help="Path to outcome_scoring_policy.yaml (default: configs/outcome_scoring_policy.yaml)",
    )
    parser.add_argument(
        "--metric-dictionary", type=Path, default=None,
        help="Path to metric_dictionary.yaml (default: configs/metric_dictionary.yaml)",
    )
    parser.add_argument(
        "--horizon", type=str, default="t5",
        choices=["t1", "t5", "t20"],
        help="Outcome horizon (default: t5)",
    )
    parser.add_argument(
        "--emit-report", action="store_true",
        help="Also generate outcome_report.md (enabled by default)",
    )
    parser.set_defaults(emit_report=True)

    args = parser.parse_args()

    if not args.logs_dir.is_dir():
        print(f"ERROR: logs-dir not found: {args.logs_dir}", file=sys.stderr)
        sys.exit(1)

    result = run_engine(
        logs_dir=args.logs_dir,
        out_dir=args.out_dir,
        policy_path=args.policy,
        metric_dictionary_path=args.metric_dictionary,
        horizon=args.horizon,
        emit_report=args.emit_report,
    )

    print(f"Engine completed. {result['total_opportunities']} opportunities processed.")
    print(f"Output: {args.out_dir}")
    for label, path_key in [
        ("Opportunity outcomes", "outcome_path"),
        ("Summary", "summary_path"),
        ("Score buckets", "bucket_path"),
        ("Monotonicity", "mono_path"),
        ("Failure distribution", "failure_path"),
        ("Alpha report", "alpha_path"),
        ("Log trust", "trust_path"),
        ("Mapping attribution", "mapping_path"),
        ("Decision suggestions", "suggestions_path"),
    ]:
        print(f"  {label}: {result[path_key]}")
    if result["report_path"]:
        print(f"  Report: {result['report_path']}")


if __name__ == "__main__":
    main()
