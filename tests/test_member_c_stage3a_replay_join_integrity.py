import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from workflow_runner import WorkflowRunner


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return []
    return [json.loads(line) for line in content.splitlines() if line.strip()]


def _execute_payload() -> dict:
    return {
        "request_id": "REQ-C-S3A-EXEC-001",
        "batch_id": "BATCH-C-S3A-EXEC-001",
        "A0": 30,
        "A-1": 70,
        "A1": 78,
        "A1.5": 60,
        "A0.5": 0,
        "severity": "E3",
        "fatigue_index": 45,
        "event_state": "Active",
        "correlation": 0.5,
        "vix": 18,
        "ted": 40,
        "spread_pct": 0.002,
        "account_equity": 100000,
        "entry_price": 100.0,
        "risk_per_share": 2.0,
        "direction": "long",
        "symbol": "SPY",
        "has_opportunity": True,
        "market_data_present": True,
        "market_data_source": "payload_direct",
        "market_data_stale": False,
        "market_data_default_used": False,
        "market_data_fallback_used": False,
        "tradeable": True,
    }


def _block_payload() -> dict:
    payload = _execute_payload()
    payload["request_id"] = "REQ-C-S3A-BLOCK-001"
    payload["batch_id"] = "BATCH-C-S3A-BLOCK-001"
    payload["has_opportunity"] = False
    return payload


def test_stage3a_replay_primary_keys_complete_without_input_event_hash(tmp_path):
    logs_dir = tmp_path / "logs"
    runner = WorkflowRunner(
        request_store_path=str(tmp_path / "seen_ids_c_s3a_1.txt"),
        audit_dir=str(logs_dir),
    )
    payload = _block_payload()
    payload.pop("event_hash", None)

    out = runner.run(payload)

    assert out["final"]["action"] in {"WATCH", "BLOCK"}
    validation = out["replay_join_validation"]
    assert validation["replay_primary_key_complete"] is True
    assert validation["replay_primary_key_completeness_ratio"] == 1.0
    assert validation["orphan_replay_count"] == 0
    assert validation["validation_status"] == "pass"

    replay_records = _read_jsonl(logs_dir / "replay_write.jsonl")
    assert replay_records
    replay = replay_records[-1]
    assert replay["event_trace_id"]
    assert replay["request_id"] == "REQ-C-S3A-BLOCK-001"
    assert replay["batch_id"] == "BATCH-C-S3A-BLOCK-001"
    assert replay["event_hash"].startswith("EVH-")


def test_stage3a_reports_orphan_replay_when_replay_write_fails(tmp_path, monkeypatch):
    logs_dir = tmp_path / "logs"
    runner = WorkflowRunner(
        request_store_path=str(tmp_path / "seen_ids_c_s3a_2.txt"),
        audit_dir=str(logs_dir),
    )
    payload = _block_payload()

    def raise_on_replay(**kwargs):
        raise RuntimeError("simulated replay write failure")

    monkeypatch.setattr(runner, "_log_replay_task", raise_on_replay)
    out = runner.run(payload)

    validation = out["replay_join_validation"]
    assert validation["replay_write_ok"] is False
    assert validation["orphan_replay_count"] == 1
    assert validation["validation_status"] == "fail"


def test_stage3a_retry_same_request_id_no_duplicate_replay_or_execution(tmp_path):
    logs_dir = tmp_path / "logs"
    runner = WorkflowRunner(
        request_store_path=str(tmp_path / "seen_ids_c_s3a_3.txt"),
        audit_dir=str(logs_dir),
    )
    payload = _execute_payload()
    payload["request_id"] = "REQ-C-S3A-RETRY-001"
    payload["batch_id"] = "BATCH-C-S3A-RETRY-001"
    payload["event_hash"] = "EVHASH-C-S3A-RETRY-001"

    first = runner.run(payload)
    assert first["final"]["action"] == "EXECUTE"
    replay_count_before = len(_read_jsonl(logs_dir / "replay_write.jsonl"))
    emit_count_before = len(_read_jsonl(logs_dir / "execution_emit.jsonl"))

    second = runner.run(payload)
    assert second["final"]["action"] == "DUPLICATE_IGNORED"
    assert len(_read_jsonl(logs_dir / "replay_write.jsonl")) == replay_count_before
    assert len(_read_jsonl(logs_dir / "execution_emit.jsonl")) == emit_count_before


def test_stage3a_execution_join_validation_passes(tmp_path):
    logs_dir = tmp_path / "logs"
    runner = WorkflowRunner(
        request_store_path=str(tmp_path / "seen_ids_c_s3a_4.txt"),
        audit_dir=str(logs_dir),
    )
    payload = _execute_payload()
    payload["request_id"] = "REQ-C-S3A-JOIN-001"
    payload["batch_id"] = "BATCH-C-S3A-JOIN-001"
    payload.pop("event_hash", None)

    out = runner.run(payload)

    assert out["final"]["action"] == "EXECUTE"
    validation = out["replay_join_validation"]
    assert validation["execution_emit_expected"] is True
    assert validation["execution_joinable_to_replay"] is True
    assert validation["orphan_execution_count"] == 0
    assert validation["validation_status"] == "pass"

    replay = _read_jsonl(logs_dir / "replay_write.jsonl")[-1]
    execution = _read_jsonl(logs_dir / "execution_emit.jsonl")[-1]
    assert replay["event_trace_id"] == execution["event_trace_id"]
    assert replay["request_id"] == execution["request_id"]
    assert replay["batch_id"] == execution["batch_id"]
    assert replay["event_hash"] == execution["event_hash"]


def test_stage3a_acceptance_orphan_replay_zero_on_nominal_paths(tmp_path):
    logs_dir = tmp_path / "logs"
    runner = WorkflowRunner(
        request_store_path=str(tmp_path / "seen_ids_c_s3a_5.txt"),
        audit_dir=str(logs_dir),
    )

    scenarios = [
        (
            "BLOCK",
            {
                "request_id": "REQ-C-S3A-ACC-BLOCK-001",
                "batch_id": "BATCH-C-S3A-ACC-BLOCK-001",
                "event_hash": "EVHASH-C-S3A-ACC-BLOCK-001",
                "drop_has_opportunity": True,
            },
        ),
        (
            "WATCH",
            {
                "request_id": "REQ-C-S3A-ACC-WATCH-001",
                "batch_id": "BATCH-C-S3A-ACC-WATCH-001",
                "event_hash": "EVHASH-C-S3A-ACC-WATCH-001",
                "market_data_stale": True,
            },
        ),
        (
            "PENDING_CONFIRM",
            {
                "request_id": "REQ-C-S3A-ACC-PENDING-001",
                "batch_id": "BATCH-C-S3A-ACC-PENDING-001",
                "event_hash": "EVHASH-C-S3A-ACC-PENDING-001",
                "require_human_confirm": True,
                "human_confirmed": False,
            },
        ),
        (
            "EXECUTE",
            {
                "request_id": "REQ-C-S3A-ACC-EXEC-001",
                "batch_id": "BATCH-C-S3A-ACC-EXEC-001",
                "event_hash": "EVHASH-C-S3A-ACC-EXEC-001",
            },
        ),
    ]

    observed_actions = []
    for expected_action, options in scenarios:
        payload = _execute_payload()
        payload.update(options)
        if options.get("drop_has_opportunity"):
            payload.pop("has_opportunity", None)
            payload.pop("drop_has_opportunity", None)
        out = runner.run(payload)
        observed_actions.append(out["final"]["action"])

        assert out["final"]["action"] == expected_action
        validation = out["replay_join_validation"]
        assert validation["orphan_replay_count"] == 0
        assert validation["replay_primary_key_completeness_ratio"] == 1.0
        assert validation["validation_status"] == "pass"
        if expected_action == "EXECUTE":
            assert validation["orphan_execution_count"] == 0

    assert set(observed_actions) == {"BLOCK", "WATCH", "PENDING_CONFIRM", "EXECUTE"}

    validation_records = _read_jsonl(logs_dir / "replay_join_validation.jsonl")
    assert len(validation_records) == 4
    assert all(record["orphan_replay_count"] == 0 for record in validation_records)
