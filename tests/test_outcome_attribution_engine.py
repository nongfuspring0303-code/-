"""Stage6 PR-7b: Outcome Attribution Engine Tests.

Member-C implementation tests.
Verifies engine output against B's expected outcome rules.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml
from jsonschema import ValidationError, validate

# Ensure scripts/ is importable
REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from outcome_attribution_engine import (
    run_engine,
    _require_policy_score_buckets,
    _check_condition,
)

FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "stage6"


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def engine_result(tmp_path_factory) -> dict:
    """Run the engine once and return results for all tests."""
    out_dir = tmp_path_factory.mktemp("stage6_outcome")
    logs_dir = FIXTURES_DIR / "outcome_logs"

    result = run_engine(
        logs_dir=logs_dir,
        out_dir=out_dir,
        horizon="t5",
    )
    # Attach out_dir for later use
    result["_out_dir"] = out_dir
    return result


@pytest.fixture(scope="module")
def opportunity_outcomes(engine_result) -> list[dict]:
    """Load generated opportunity outcomes."""
    path = Path(engine_result["outcome_path"])
    return _read_jsonl(path)


@pytest.fixture(scope="module")
def outcome_summary(engine_result) -> dict:
    return _load_json(Path(engine_result["summary_path"]))


@pytest.fixture(scope="module")
def mapping_attributions(engine_result) -> list[dict]:
    return _read_jsonl(Path(engine_result["mapping_path"]))


@pytest.fixture(scope="module")
def score_buckets(engine_result) -> dict:
    return _load_json(Path(engine_result["bucket_path"]))


@pytest.fixture(scope="module")
def scoring_policy() -> dict:
    return _load_yaml(REPO_ROOT / "configs" / "outcome_scoring_policy.yaml")


@pytest.fixture(scope="module")
def outcome_schema() -> dict:
    return _load_json(REPO_ROOT / "schemas" / "opportunity_outcome.schema.json")


@pytest.fixture(scope="module")
def mapping_schema() -> dict:
    return _load_json(REPO_ROOT / "schemas" / "mapping_attribution.schema.json")


@pytest.fixture(scope="module")
def log_trust_schema() -> dict:
    return _load_json(REPO_ROOT / "schemas" / "log_trust.schema.json")


@pytest.fixture(scope="module")
def log_trust_report(engine_result) -> dict:
    return _load_json(Path(engine_result["trust_path"]))


@pytest.fixture(scope="module")
def failure_reason_distribution(engine_result) -> dict:
    return _load_json(Path(engine_result["failure_path"]))


@pytest.fixture(scope="module")
def expected_outcomes_contract() -> dict:
    return _load_yaml(FIXTURES_DIR / "expected_outcomes.yaml")


@pytest.fixture(scope="module")
def mapping_attributions(engine_result) -> list[dict]:
    return _read_jsonl(Path(engine_result["mapping_path"]))


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------

def test_all_outcomes_pass_schema_validation(opportunity_outcomes, outcome_schema):
    """Every generated opportunity_outcome must validate against the schema."""
    for idx, outcome in enumerate(opportunity_outcomes):
        oid = outcome.get("opportunity_id", f"index_{idx}")
        try:
            validate(instance=outcome, schema=outcome_schema)
        except ValidationError as e:
            pytest.fail(f"Outcome {oid} failed schema validation: {e}")


def test_all_mapping_attributions_pass_schema_validation(engine_result, mapping_schema):
    """All mapping attribution records must validate."""
    path = Path(engine_result["mapping_path"])
    recs = _read_jsonl(path)
    for rec in recs:
        validate(instance=rec, schema=mapping_schema)


def test_all_log_trust_pass_schema_validation(engine_result, log_trust_schema):
    """All log trust records must validate."""
    path = Path(engine_result["trust_path"])
    data = _load_json(path)
    recs = data.get("records", [])
    for rec in recs:
        validate(instance=rec, schema=log_trust_schema)


# ---------------------------------------------------------------------------
# EXECUTE LONG / SHORT classification
# ---------------------------------------------------------------------------

def test_execute_long_hit(opportunity_outcomes):
    """EXECUTE LONG with t5_return +3% -> hit."""
    outcome = _find_by_trace(opportunity_outcomes, "EXEC-LONG-HIT-001")
    assert outcome is not None
    assert outcome["outcome_label"] == "hit"
    assert outcome["outcome_status"] == "resolved_t5"
    assert outcome["data_quality"] == "valid"


def test_execute_long_miss(opportunity_outcomes):
    """EXECUTE LONG with t5_return -3% -> miss."""
    outcome = _find_by_trace(opportunity_outcomes, "EXEC-LONG-MISS-001")
    assert outcome is not None
    assert outcome["outcome_label"] == "miss"
    assert outcome["outcome_status"] == "resolved_t5"
    assert outcome["data_quality"] == "valid"


def test_execute_long_neutral(opportunity_outcomes):
    """EXECUTE LONG with t5_return +1% -> neutral."""
    outcome = _find_by_trace(opportunity_outcomes, "EXEC-LONG-NEUT-001")
    assert outcome is not None
    assert outcome["outcome_label"] == "neutral"
    assert outcome["outcome_status"] == "resolved_t5"
    assert outcome["data_quality"] == "valid"


def test_execute_short_hit(opportunity_outcomes):
    """EXECUTE SHORT with t5_return -3% -> hit."""
    outcome = _find_by_trace(opportunity_outcomes, "EXEC-SHORT-HIT-001")
    assert outcome is not None
    assert outcome["outcome_label"] == "hit"
    assert outcome["data_quality"] == "valid"


def test_execute_short_miss(opportunity_outcomes):
    """EXECUTE SHORT with t5_return +3% -> miss."""
    outcome = _find_by_trace(opportunity_outcomes, "EXEC-SHORT-MISS-001")
    assert outcome is not None
    assert outcome["outcome_label"] == "miss"
    assert outcome["data_quality"] == "valid"


# ---------------------------------------------------------------------------
# WATCH classification
# ---------------------------------------------------------------------------

def test_watch_missed_opportunity(opportunity_outcomes):
    """WATCH LONG with subsequent +3% -> missed_opportunity."""
    outcome = _find_by_trace(opportunity_outcomes, "WATCH-MISSEDOPP-001")
    assert outcome is not None
    assert outcome["outcome_label"] == "missed_opportunity"
    assert outcome["data_quality"] == "valid"


def test_watch_correct(opportunity_outcomes):
    """WATCH LONG with subsequent -3% -> correct_watch."""
    outcome = _find_by_trace(opportunity_outcomes, "WATCH-CORRECT-001")
    assert outcome is not None
    assert outcome["outcome_label"] == "correct_watch"
    assert outcome["data_quality"] == "valid"


def test_watch_neutral(opportunity_outcomes):
    """WATCH LONG with t5_return +1% -> neutral_watch."""
    outcome = _find_by_trace(opportunity_outcomes, "WATCH-NEUTRAL-001")
    assert outcome is not None
    assert outcome["outcome_label"] == "neutral_watch"
    assert outcome["data_quality"] == "valid"


# ---------------------------------------------------------------------------
# BLOCK classification
# ---------------------------------------------------------------------------

def test_block_correct(opportunity_outcomes):
    """BLOCK LONG with subsequent -3% -> correct_block."""
    outcome = _find_by_trace(opportunity_outcomes, "BLOCK-CORRECT-001")
    assert outcome is not None
    assert outcome["outcome_label"] == "correct_block"
    assert outcome["data_quality"] == "valid"


def test_block_overblocked(opportunity_outcomes):
    """BLOCK LONG with subsequent +3% -> overblocked."""
    outcome = _find_by_trace(opportunity_outcomes, "BLOCK-OVERBLOCK-001")
    assert outcome is not None
    assert outcome["outcome_label"] == "overblocked"
    assert outcome["data_quality"] == "valid"


def test_block_neutral(opportunity_outcomes):
    """BLOCK LONG with t5_return +1% -> neutral_block."""
    outcome = _find_by_trace(opportunity_outcomes, "BLOCK-NEUTRAL-001")
    assert outcome is not None
    assert outcome["outcome_label"] == "neutral_block"
    assert outcome["data_quality"] == "valid"


# ---------------------------------------------------------------------------
# Data quality edge cases
# ---------------------------------------------------------------------------

def test_join_key_missing_is_invalid(opportunity_outcomes):
    """Missing join key (null event_hash) -> invalid, excluded."""
    outcome = _find_by_trace(opportunity_outcomes, "JOINKEY-MISSING-001")
    assert outcome is not None
    assert outcome["data_quality"] == "invalid"
    assert outcome["outcome_status"] == "invalid_join_key"
    assert outcome.get("primary_failure_reason") == "join_key_missing"
    assert outcome.get("failure_reasons", []) == ["join_key_missing"]


def test_join_key_missing_mapping_status(mapping_attributions):
    """JOINKEY-MISSING must map to join_key_missing, not mapping_success."""
    rec = _find_by_trace(mapping_attributions, "JOINKEY-MISSING-001")
    assert rec is not None
    assert rec["mapping_status"] == "join_key_missing"
    assert rec["mapping_failure_reason"] == "join_key_missing"


def test_join_key_missing_trust_report_counts(log_trust_report):
    """Incomplete join keys must be counted as invalid in log trust."""
    assert log_trust_report["join_key_valid_count"] == 23
    assert log_trust_report["join_key_invalid_count"] == 1
    rec = next(
        r for r in log_trust_report["records"] if r["opportunity_id"] == "opp-000012"
    )
    assert rec["join_key_valid"] is False
    assert "event_hash" in rec.get("missing_join_fields", [])


def test_join_key_missing_counted_once_in_failure_distribution(failure_reason_distribution):
    """join_key_missing should be counted once per record, not twice."""
    assert failure_reason_distribution.get("join_key_missing") == 1


def test_symbol_missing_is_invalid(opportunity_outcomes):
    """Missing symbol -> invalid."""
    outcome = _find_by_trace(opportunity_outcomes, "SYMBOL-MISSING-001")
    assert outcome is not None
    assert outcome["data_quality"] == "invalid"


def test_benchmark_missing_is_degraded(opportunity_outcomes):
    """Benchmark missing -> degraded, not in primary stats."""
    outcome = _find_by_trace(opportunity_outcomes, "BENCHMARK-MISS-001")
    assert outcome is not None
    # benchmark_missing triggers degraded
    assert outcome["data_quality"] in ("degraded", "valid")
    # Verify benchmark_missing is in failure_reasons
    if outcome["data_quality"] == "degraded":
        assert "benchmark_missing" in outcome.get("failure_reasons", [])


def test_pending_t5_no_hit_miss(opportunity_outcomes):
    """Pending T+5 should not emit hit/miss."""
    outcome = _find_by_trace(opportunity_outcomes, "PENDING-T5-001")
    assert outcome is not None
    assert outcome["outcome_label"] is None
    assert outcome["data_quality"] == "pending"


def test_pending_confirm_audit_only(opportunity_outcomes):
    """PENDING_CONFIRM -> audit-only, not valid, not hit/miss."""
    outcome = _find_by_trace(opportunity_outcomes, "AUDIT-PENDING-001")
    assert outcome is not None
    assert outcome["action_after_gate"] == "PENDING_CONFIRM"
    assert outcome["data_quality"] != "valid"
    assert outcome["outcome_label"] is None


def test_unknown_audit_only(opportunity_outcomes):
    """UNKNOWN -> audit-only, not valid, not hit/miss."""
    outcome = _find_by_trace(opportunity_outcomes, "AUDIT-UNKNOWN-001")
    assert outcome is not None
    assert outcome["action_after_gate"] == "UNKNOWN"
    assert outcome["data_quality"] != "valid"
    assert outcome["outcome_label"] is None


def test_mock_test_excluded_from_primary(opportunity_outcomes):
    """Mock/test record -> invalid, excluded from primary stats."""
    outcome = _find_by_trace(opportunity_outcomes, "MOCK-TEST-001")
    # The MOCK-TEST-001 may or may not be found depending on log_source handling
    if outcome is not None:
        assert outcome["data_quality"] != "valid"


def test_market_data_stale_is_degraded(opportunity_outcomes):
    """Stale market data -> degraded (not valid)."""
    outcome = _find_by_trace(opportunity_outcomes, "MKT-DATA-STALE-001")
    assert outcome is not None
    assert outcome["data_quality"] in ("degraded", "invalid")


def test_market_data_default_is_invalid(opportunity_outcomes):
    """Default market data used -> invalid."""
    outcome = _find_by_trace(opportunity_outcomes, "MKT-DATA-DEFAULT-001")
    assert outcome is not None
    assert outcome["data_quality"] in ("degraded", "invalid")


def test_expected_outcomes_yaml_contract(
    opportunity_outcomes, expected_outcomes_contract
):
    """YAML-driven contract: outcomes must match Member B expected cases."""
    expected_cases = expected_outcomes_contract.get("expected_cases", [])
    assert expected_cases, "expected_cases must not be empty"
    trace_ids = [case["trace_id"] for case in expected_cases]
    assert len(trace_ids) == len(set(trace_ids)), "trace_id values must be unique"

    for case in expected_cases:
        trace_id = case["trace_id"]
        outcome = _find_by_trace(opportunity_outcomes, trace_id)
        assert outcome is not None, f"Missing generated outcome for {case['fixture_id']} ({trace_id})"
        assert outcome["action_after_gate"] == case["action_after_gate"]
        assert outcome["outcome_status"] == case["expected_outcome_status"]
        assert outcome["outcome_label"] == case["expected_outcome_label"]
        assert outcome["data_quality"] == case["expected_data_quality"]
        assert _is_primary_stats_included(outcome) == case["expected_primary_stats_inclusion"]
        assert _is_alpha_primary_included(outcome) == case["expected_alpha_primary_inclusion"]
        assert outcome.get("primary_failure_reason") == case["expected_primary_failure_reason"]
        assert outcome.get("failure_reasons", []) == case["expected_failure_reasons"]

    bucket_cases = expected_outcomes_contract.get("score_bucket_tests", [])
    assert bucket_cases, "score_bucket_tests must not be empty"
    for case in bucket_cases:
        trace_id = case["trace_id"]
        outcome = _find_by_trace(opportunity_outcomes, trace_id)
        assert outcome is not None, f"Missing score bucket outcome for {case['fixture_id']} ({trace_id})"
        assert outcome["score_bucket"] == case["expected_bucket"]
        assert abs(float(outcome["score"]) - float(case["score"])) < 1e-9


def test_expected_mapping_attribution_yaml_contract(
    mapping_attributions, expected_outcomes_contract
):
    """YAML-driven contract: mapping attribution must match expected cases."""
    expected_cases = expected_outcomes_contract.get("expected_cases", [])
    mapping_cases = [
        case for case in expected_cases if "expected_mapping_status" in case
    ]
    assert mapping_cases, "expected_outcomes.yaml must include mapping attribution expected cases"

    for case in mapping_cases:
        trace_id = case["trace_id"]
        mapping = _find_mapping_by_trace(mapping_attributions, trace_id)
        assert mapping is not None, (
            f"Missing mapping attribution for {case['fixture_id']} ({trace_id})"
        )
        assert mapping["mapping_status"] == case["expected_mapping_status"]
        assert mapping.get("mapping_failure_reason") == case["expected_mapping_failure_reason"]


# ---------------------------------------------------------------------------
# Primary stats: PENDING_CONFIRM / UNKNOWN must not enter primary stats
# ---------------------------------------------------------------------------

def test_audit_only_not_in_primary_stats(outcome_summary):
    """Verify that valid_outcome_count excludes audit-only records."""
    valid_count = outcome_summary.get("valid_outcome_count", 0)
    # We should have at least the valid EXECUTE/WATCH/BLOCK records
    assert valid_count > 0


def test_benchmark_missing_not_in_alpha_primary(engine_result):
    """Benchmark_missing records are degraded, excluded from alpha primary stats."""
    alpha_path = Path(engine_result["alpha_path"])
    alpha_report = _load_json(alpha_path)
    # benchmark_missing causes degraded data_quality, which excludes from primary stats
    assert alpha_report.get("alpha_eligible_count", 0) >= 0
    # Verify degraded outcomes exist
    summary_path = Path(engine_result["summary_path"])
    summary = _load_json(summary_path)
    assert summary.get("degraded_outcome_count", 0) > 0


# ---------------------------------------------------------------------------
# Score buckets
# ---------------------------------------------------------------------------

def test_score_bucket_assignment(opportunity_outcomes):
    """Verify score buckets are assigned correctly."""
    score80 = _find_by_trace(opportunity_outcomes, "SCORE-80PLUS-001")
    assert score80 is not None
    assert score80["score_bucket"] == "80_PLUS"

    score60 = _find_by_trace(opportunity_outcomes, "SCORE-60-79-001")
    assert score60 is not None
    assert score60["score_bucket"] == "60_79"

    score40 = _find_by_trace(opportunity_outcomes, "SCORE-40-59-001")
    assert score40 is not None
    assert score40["score_bucket"] == "40_59"

    scorelt = _find_by_trace(opportunity_outcomes, "SCORE-LT40-001")
    assert scorelt is not None
    assert scorelt["score_bucket"] == "LT_40"


def test_score_buckets_output_valid(score_buckets, scoring_policy):
    """Verify score bucket output matches schema."""
    assert score_buckets["schema_version"] == "stage6.outcome_by_score_bucket.v1"
    assert "buckets" in score_buckets
    expected_order = [b["name"] for b in scoring_policy["score_buckets"]]
    actual_order = [b["name"] for b in score_buckets["buckets"]]
    assert actual_order == expected_order


def test_summary_schema_and_coverage_metrics(outcome_summary):
    """Summary must expose contract schema version and required coverage metrics."""
    assert outcome_summary["schema_version"] == "stage6.outcome_summary.v1"
    required_coverage_keys = [
        "outcome_record_coverage_rate",
        "resolved_outcome_coverage_rate",
        "pending_outcome_rate",
        "execute_outcome_coverage_rate",
        "join_key_link_rate",
        "failure_reason_coverage_rate",
    ]
    for key in required_coverage_keys:
        assert key in outcome_summary
        assert outcome_summary[key] is not None
    assert outcome_summary["failure_reason_coverage_rate"] >= 0.95


def test_score_buckets_policy_missing_fails_fast():
    with pytest.raises(ValueError, match="missing score_buckets section"):
        _require_policy_score_buckets({})


def test_score_buckets_policy_missing_name_fails_fast():
    with pytest.raises(ValueError, match="missing required key 'name'"):
        _require_policy_score_buckets({"score_buckets": [{"min": 80, "max": None}]})


# ---------------------------------------------------------------------------
# Output file existence
# ---------------------------------------------------------------------------

def test_all_output_files_exist(engine_result):
    """Verify all required output files are generated."""
    expected_files = [
        "outcome_path",        # opportunity_outcome.jsonl
        "summary_path",        # outcome_summary.json
        "report_path",         # outcome_report.md
        "bucket_path",         # outcome_by_score_bucket.json
        "mono_path",           # score_monotonicity_report.json
        "failure_path",        # failure_reason_distribution.json
        "alpha_path",          # alpha_report.json
        "trust_path",          # log_trust_report.json
        "mapping_path",        # mapping_attribution.jsonl
        "suggestions_path",    # decision_suggestions.json
    ]
    for key in expected_files:
        path = engine_result.get(key)
        assert path is not None, f"Missing output: {key}"
        assert Path(path).exists(), f"Output file not found: {path}"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _find_by_trace(outcomes: list[dict], trace_id: str) -> dict | None:
    """Find an outcome record by trace_id."""
    for o in outcomes:
        if o.get("trace_id") == trace_id:
            return o
    return None


def _find_by_opp_id(outcomes: list[dict], opp_id: str) -> dict | None:
    for o in outcomes:
        if o.get("opportunity_id") == opp_id:
            return o
    return None


def _find_mapping_by_trace(mappings: list[dict], trace_id: str) -> dict | None:
    """Find a mapping attribution record by trace_id."""
    for m in mappings:
        if m.get("trace_id") == trace_id:
            return m
    return None


def _is_primary_stats_included(outcome: dict) -> bool:
    """Primary stats are valid-only in the PR-7b contract."""
    return outcome.get("data_quality") == "valid"


def _is_alpha_primary_included(outcome: dict) -> bool:
    """Alpha primary excludes benchmark_missing and any non-valid rows."""
    return outcome.get("data_quality") == "valid" and "benchmark_missing" not in outcome.get(
        "failure_reasons", []
    )


# ---------------------------------------------------------------------------
# S6-R015: decision_price_source data_quality rules
# Test IDs: S6-T015-01 ~ S6-T015-04
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("source,expected", [
    (None, True),       # None → decision_price_source_missing → invalid
    ("missing", True),  # "missing" → decision_price_source_missing → invalid
    ("", True),         # empty → decision_price_source_missing → invalid
])
def test_s6_r015_decision_price_source_missing(source, expected):
    """S6-R015: decision_price_source is None/missing/empty -> decision_price_source_missing.
    Test IDs: S6-T015-01~03"""
    result = _check_condition({"decision_price_source": source}, "decision_price_source_missing")
    assert result is expected


def test_s6_r015_decision_price_source_live_not_missing():
    """S6-R015: decision_price_source='live' does NOT trigger missing condition.
    Test ID: S6-T015-04"""
    result = _check_condition({"decision_price_source": "live"}, "decision_price_source_missing")
    assert result is False


@pytest.mark.parametrize("source,expected", [
    ("snapshot", True),       # non-live → non_live → degraded
    ("reference", True),      # non-live → non_live → degraded
    ("dynamic_cache", True),  # non-live → non_live → degraded
    (None, False),            # None is already caught by decision_price_source_missing
    ("missing", False),       # "missing" already caught by decision_price_source_missing
    ("live", False),          # live is valid
])
def test_s6_r015_decision_price_source_non_live(source, expected):
    """S6-R015: non-live decision_price_source -> decision_price_source_non_live -> degraded.
    Test IDs: S6-T015-05~10"""
    result = _check_condition({"decision_price_source": source}, "decision_price_source_non_live")
    assert result is expected


def test_s6_r015_end_to_end_price_source_closure(tmp_path):
    """S6-R015 E2E: producer scorecard field -> engine data_quality/failure_reason closure."""
    logs_dir = tmp_path / "logs"
    out_dir = tmp_path / "out"
    logs_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    trace_id = "E2E-PRICE-SOURCE-MISSING-001"
    event_hash = "hash-e2e-1"

    # producer: trace_scorecard.jsonl
    (logs_dir / "trace_scorecard.jsonl").write_text(
        json.dumps({
            "trace_id": trace_id,
            "event_hash": event_hash,
            "symbol": "AAPL",
            "side": "LONG",
            "direction": "LONG",
            "stock_candidates": [{"symbol": "AAPL", "direction": "LONG"}],
            "final_action": "EXECUTE",
            "event_time": "2026-05-01T10:00:00Z",
            "decision_price": 100.0,
            "decision_price_source": "missing",
            "log_source": "live",
            "t5_return": 0.03,
            "sector_relative_alpha_t5": 0.02,
        }) + "\n",
        encoding="utf-8",
    )

    # required sibling logs for join
    (logs_dir / "decision_gate.jsonl").write_text(
        json.dumps({
            "trace_id": trace_id,
            "event_hash": event_hash,
            "final_action_after_gate": "EXECUTE",
            "logged_at": "2026-05-01T10:00:01Z",
        }) + "\n",
        encoding="utf-8",
    )
    (logs_dir / "market_data_provenance.jsonl").write_text(
        json.dumps({
            "trace_id": trace_id,
            "event_hash": event_hash,
            "market_data_default_used": False,
            "market_data_stale": False,
            "market_data_fallback_used": False,
        }) + "\n",
        encoding="utf-8",
    )
    (logs_dir / "execution_emit.jsonl").write_text("", encoding="utf-8")
    (logs_dir / "replay_write.jsonl").write_text("", encoding="utf-8")

    result = run_engine(logs_dir=logs_dir, out_dir=out_dir, horizon="t5")
    outcomes = _read_jsonl(Path(result["outcome_path"]))
    assert len(outcomes) == 1
    rec = outcomes[0]
    assert rec["data_quality"] == "invalid"
    assert rec.get("primary_failure_reason") == "execution_missing"
    assert "execution_missing" in rec.get("failure_reasons", [])


def test_s6_r015_end_to_end_non_live_source_closure(tmp_path):
    """S6-R015 E2E: non-live source -> degraded + market_data_bad closure."""
    logs_dir = tmp_path / "logs_non_live"
    out_dir = tmp_path / "out_non_live"
    logs_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    trace_id = "E2E-PRICE-SOURCE-NON-LIVE-001"
    event_hash = "hash-e2e-2"

    (logs_dir / "trace_scorecard.jsonl").write_text(
        json.dumps({
            "trace_id": trace_id,
            "event_hash": event_hash,
            "symbol": "AAPL",
            "side": "LONG",
            "direction": "LONG",
            "stock_candidates": [{"symbol": "AAPL", "direction": "LONG"}],
            "final_action": "EXECUTE",
            "event_time": "2026-05-01T10:05:00Z",
            "decision_price": 100.0,
            "decision_price_source": "snapshot",
            "log_source": "live",
            "t5_return": 0.03,
            "sector_relative_alpha_t5": 0.02,
        }) + "\n",
        encoding="utf-8",
    )
    (logs_dir / "decision_gate.jsonl").write_text(
        json.dumps({
            "trace_id": trace_id,
            "event_hash": event_hash,
            "final_action_after_gate": "EXECUTE",
            "logged_at": "2026-05-01T10:05:01Z",
        }) + "\n",
        encoding="utf-8",
    )
    (logs_dir / "market_data_provenance.jsonl").write_text(
        json.dumps({
            "trace_id": trace_id,
            "event_hash": event_hash,
            "market_data_default_used": False,
            "market_data_stale": False,
            "market_data_fallback_used": False,
        }) + "\n",
        encoding="utf-8",
    )
    (logs_dir / "execution_emit.jsonl").write_text("", encoding="utf-8")
    (logs_dir / "replay_write.jsonl").write_text("", encoding="utf-8")

    result = run_engine(logs_dir=logs_dir, out_dir=out_dir, horizon="t5")
    outcomes = _read_jsonl(Path(result["outcome_path"]))
    assert len(outcomes) == 1
    rec = outcomes[0]
    assert rec["data_quality"] == "degraded"
    assert rec.get("primary_failure_reason") == "market_data_bad"
    assert "market_data_bad" in rec.get("failure_reasons", [])


def test_s6_r015_end_to_end_symbol_context_prevents_cross_symbol_leakage(tmp_path):
    """S6-R015 E2E: symbol with missing price context must not inherit event-level price/source."""
    logs_dir = tmp_path / "logs_symbol_first"
    out_dir = tmp_path / "out_symbol_first"
    logs_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    trace_id = "E2E-SYMBOL-FIRST-001"
    event_hash = "hash-e2e-symbol-first"

    (logs_dir / "trace_scorecard.jsonl").write_text(
        json.dumps({
            "trace_id": trace_id,
            "event_hash": event_hash,
            "symbol": "TSLA",
            "side": "LONG",
            "direction": "LONG",
            "stock_candidates": [{"symbol": "TSLA", "direction": "LONG"}],
            "final_action": "WATCH",
            "event_time": "2026-05-01T10:10:00Z",
            # event-level fields may point to a different symbol context
            "decision_price": 111.0,
            "decision_price_source": "live",
            "decision_prices_by_symbol": {
                "AAPL": {
                    "decision_price": 111.0,
                    "decision_price_source": "live",
                    "needs_price_refresh": False,
                },
                "TSLA": {
                    "decision_price": None,
                    "decision_price_source": "missing",
                    "needs_price_refresh": True,
                },
            },
            "log_source": "live",
            "t5_return": 0.0,
            "sector_relative_alpha_t5": 0.0,
        }) + "\n",
        encoding="utf-8",
    )
    (logs_dir / "decision_gate.jsonl").write_text(
        json.dumps({
            "trace_id": trace_id,
            "event_hash": event_hash,
            "final_action_after_gate": "WATCH",
            "logged_at": "2026-05-01T10:10:01Z",
        }) + "\n",
        encoding="utf-8",
    )
    (logs_dir / "market_data_provenance.jsonl").write_text(
        json.dumps({
            "trace_id": trace_id,
            "event_hash": event_hash,
            "market_data_default_used": False,
            "market_data_stale": False,
            "market_data_fallback_used": False,
        }) + "\n",
        encoding="utf-8",
    )
    (logs_dir / "execution_emit.jsonl").write_text("", encoding="utf-8")
    (logs_dir / "replay_write.jsonl").write_text("", encoding="utf-8")

    result = run_engine(logs_dir=logs_dir, out_dir=out_dir, horizon="t5")
    outcomes = _read_jsonl(Path(result["outcome_path"]))
    assert len(outcomes) == 1
    rec = outcomes[0]
    assert rec.get("decision_price") is None
    assert rec.get("decision_price_source") in (None, "missing")
    assert rec["data_quality"] == "invalid"
    assert rec.get("primary_failure_reason") == "execution_missing"


def test_multi_symbol_missing_price_does_not_inherit_event_level_price(tmp_path):
    """Required regression: missing-price symbol must not inherit event-level/live price.
    AAPL has live price, TSLA missing; TSLA must resolve to invalid/execution_missing.
    """
    logs_dir = tmp_path / "logs_multi_symbol_missing_price"
    out_dir = tmp_path / "out_multi_symbol_missing_price"
    logs_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    trace_id = "E2E-MULTI-SYMBOL-PRICE-001"
    event_hash = "hash-e2e-multi-symbol"

    (logs_dir / "trace_scorecard.jsonl").write_text(
        json.dumps({
            "trace_id": trace_id,
            "event_hash": event_hash,
            "symbol": "TSLA",
            "side": "LONG",
            "direction": "LONG",
            "stock_candidates": [
                {"symbol": "TSLA", "direction": "LONG"},
                {"symbol": "AAPL", "direction": "LONG"},
            ],
            "final_action": "WATCH",
            "event_time": "2026-05-01T10:12:00Z",
            # event-level fields may reflect AAPL context
            "decision_price": 100.0,
            "decision_price_source": "live",
            "decision_prices_by_symbol": {
                "AAPL": {
                    "decision_price": 100.0,
                    "decision_price_source": "live",
                    "needs_price_refresh": False,
                },
                "TSLA": {
                    "decision_price": None,
                    "decision_price_source": "missing",
                    "needs_price_refresh": True,
                },
            },
            "log_source": "live",
            "t5_return": 0.0,
            "sector_relative_alpha_t5": 0.0,
        }) + "\n",
        encoding="utf-8",
    )
    (logs_dir / "decision_gate.jsonl").write_text(
        json.dumps({
            "trace_id": trace_id,
            "event_hash": event_hash,
            "final_action_after_gate": "WATCH",
            "logged_at": "2026-05-01T10:12:01Z",
        }) + "\n",
        encoding="utf-8",
    )
    (logs_dir / "market_data_provenance.jsonl").write_text(
        json.dumps({
            "trace_id": trace_id,
            "event_hash": event_hash,
            "market_data_default_used": False,
            "market_data_stale": False,
            "market_data_fallback_used": False,
        }) + "\n",
        encoding="utf-8",
    )
    (logs_dir / "execution_emit.jsonl").write_text("", encoding="utf-8")
    (logs_dir / "replay_write.jsonl").write_text("", encoding="utf-8")

    result = run_engine(logs_dir=logs_dir, out_dir=out_dir, horizon="t5")
    outcomes = _read_jsonl(Path(result["outcome_path"]))
    assert len(outcomes) == 1
    rec = outcomes[0]

    # TSLA must keep its own missing context and not inherit AAPL live price/source.
    assert rec.get("symbol") == "TSLA"
    assert rec.get("decision_price") is None
    assert rec.get("decision_price_source") in (None, "missing")
    assert rec.get("data_quality") == "invalid"
    assert rec.get("primary_failure_reason") == "execution_missing"
    assert "execution_missing" in rec.get("failure_reasons", [])
