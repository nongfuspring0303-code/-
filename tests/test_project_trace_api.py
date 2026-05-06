from __future__ import annotations

import http.client
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
import sys

sys.path.insert(0, str(ROOT / "scripts"))

from config_api_server import ConfigAPIHandler, create_server
from project_trace_reader import ProjectTraceReader


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _serve(logs_dir: Path):
    ConfigAPIHandler.project_reader = ProjectTraceReader(logs_dir)
    server = create_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _request(server, method: str, path: str, body: dict | None = None):
    conn = http.client.HTTPConnection(server.server_address[0], server.server_address[1], timeout=5)
    headers = {"X-EDT-Token": ConfigAPIHandler.auth_token}
    payload = None
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    conn.request(method, path, body=payload, headers=headers)
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8")
    conn.close()
    parsed = json.loads(raw) if raw else {}
    return resp.status, parsed, raw


def _sample_scorecard(trace_id: str, logged_at: str, **overrides) -> dict:
    payload = {
        "logged_at": logged_at,
        "trace_id": trace_id,
        "request_id": "REQ-TRACE-001",
        "final_action": "WATCH",
        "final_reason": "Blocked by gates or no valid position.",
        "sector_quality_score": 100.0,
        "ticker_quality_score": 95.0,
        "output_quality_score": 92.0,
        "a_gate_blocker_codes": [],
        "a_gate_blocker_count": 0,
        "a_gate_blocker_present": False,
        "scores": {"total_score": 94.0, "grade": "A"},
    }
    payload.update(overrides)
    return payload


def _sample_pipeline_stage(trace_id: str, stage: str, logged_at: str, seq: int, **overrides) -> dict:
    payload = {
        "logged_at": logged_at,
        "trace_id": trace_id,
        "stage_seq": seq,
        "stage": stage,
        "status": "success",
        "details": {"note": stage},
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def logs_dir(tmp_path: Path) -> Path:
    path = tmp_path / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def project_server(logs_dir: Path):
    server, thread = _serve(logs_dir)
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_project_trace_api_normal_and_empty_paths(project_server, logs_dir: Path):
    trace_id = "ME-PR-1-001"
    _write_jsonl(
        logs_dir / "trace_scorecard.jsonl",
        [
            _sample_scorecard(trace_id, "2026-05-06T10:00:00Z"),
            _sample_scorecard("ME-PR-1-002", "2026-05-06T11:00:00Z", scores={"total_score": 82.0, "grade": "B"}),
        ],
    )
    _write_jsonl(
        logs_dir / "pipeline_stage.jsonl",
        [
            _sample_pipeline_stage(trace_id, "intel_ingest", "2026-05-06T10:00:01Z", 1),
            _sample_pipeline_stage(trace_id, "execution", "2026-05-06T10:00:10Z", 10),
        ],
    )

    status, body, raw = _request(project_server, "GET", "/api/project/traces/latest")
    assert status == 200
    assert body["schema_version"] == "project.api.v1"
    assert body["status"] == "ok"
    assert body["trace_id"] == "ME-PR-1-002"
    assert body["data"]["scorecard"]["trace_id"] == "ME-PR-1-002"
    assert body["data"]["scorecard"]["total_score"] == 82.0
    assert body["data"]["pipeline_stages"] == []
    assert "Traceback" not in raw
    assert "evt_" not in raw

    status, body, raw = _request(project_server, "GET", f"/api/project/trace/{trace_id}")
    assert status == 200
    assert body["status"] == "ok"
    assert body["trace_id"] == trace_id
    assert len(body["data"]["pipeline_stages"]) == 2
    assert body["data"]["scorecard"]["grade"] == "A"
    assert "Traceback" not in raw

    status, body, raw = _request(project_server, "GET", "/api/project/trace/NOT-FOUND")
    assert status == 200
    assert body["status"] == "empty"
    assert body["data"]["scorecard"] is None
    assert body["data"]["pipeline_stages"] == []
    assert "Traceback" not in raw
    assert "evt_" not in raw

    status, body, raw = _request(project_server, "GET", "/api/project/scorecards/latest")
    assert status == 200
    assert body["status"] == "ok"
    assert body["data"]["scorecard"]["trace_id"] == "ME-PR-1-002"


def test_project_trace_api_empty_and_partial_and_bad_jsonl(project_server, logs_dir: Path):
    _write_text(logs_dir / "trace_scorecard.jsonl", '{"broken": true}\n{"logged_at": "2026-05-06T10:00:00Z"}\n')
    _write_text(logs_dir / "pipeline_stage.jsonl", '{"trace_id":"ME-PR-1-003","stage":"intel_ingest","status":"success"}\n')

    status, body, raw = _request(project_server, "GET", "/api/project/scorecards/latest")
    assert status == 200
    assert body["status"] == "partial"
    assert body["errors"]
    assert "Traceback" not in raw

    status, body, raw = _request(project_server, "GET", "/api/project/traces/latest")
    assert status == 200
    assert body["status"] == "partial"
    assert body["errors"]
    assert "Traceback" not in raw

    empty_logs_dir = logs_dir.parent / "empty_logs"
    empty_logs_dir.mkdir(parents=True, exist_ok=True)
    empty_server, thread = _serve(empty_logs_dir)
    try:
        status, body, raw = _request(empty_server, "GET", "/api/project/scorecards/latest")
        assert status == 200
        assert body["status"] == "empty"
        assert body["data"]["scorecard"] is None
        assert "Traceback" not in raw
    finally:
        empty_server.shutdown()
        empty_server.server_close()
        thread.join(timeout=2)


def test_project_trace_api_system_health_and_read_only_methods(project_server, logs_dir: Path):
    trace_id = "ME-PR-1-010"
    _write_jsonl(
        logs_dir / "trace_scorecard.jsonl",
        [_sample_scorecard(trace_id, "2026-05-06T10:00:00Z")],
    )
    _write_jsonl(
        logs_dir / "pipeline_stage.jsonl",
        [
            _sample_pipeline_stage(trace_id, stage, f"2026-05-06T10:{idx:02d}:00Z", idx)
            for idx, stage in enumerate(
                [
                    "intel_ingest",
                    "lifecycle",
                    "fatigue",
                    "conduction",
                    "market_validation",
                    "semantic",
                    "path_adjudication",
                    "signal",
                    "opportunity",
                    "execution",
                ],
                start=1,
            )
        ],
    )
    _write_jsonl(logs_dir / "raw_news_ingest.jsonl", [{"logged_at": "2026-05-06T10:00:00Z", "trace_id": trace_id}])
    _write_jsonl(
        logs_dir / "market_data_provenance.jsonl",
        [
            {
                "logged_at": "2026-05-06T10:00:00Z",
                "trace_id": trace_id,
                "market_data_source": "payload_direct",
                "market_data_present": True,
                "market_data_stale": False,
                "market_data_default_used": False,
                "market_data_fallback_used": False,
                "fallback_used": False,
                "providers_failed": [],
                "provider_failure_reasons": {},
                "fallback_reason": "",
                "unresolved_symbols": [],
            }
        ],
    )

    status, body, raw = _request(project_server, "GET", "/api/project/system-health")
    assert status == 200
    assert body["schema_version"] == "project.api.v1"
    assert body["status"] in {"ok", "partial"}
    assert body["trace_id"] is None
    assert "system_health_daily" in body["data"]
    assert "daily_report_markdown" in body["data"]
    assert "Traceback" not in raw
    assert "evt_" not in raw

    status, body, raw = _request(project_server, "GET", "/api/project/gap-report")
    assert status == 200
    assert body["schema_version"] == "project.api.v1"
    assert body["status"] in {"ok", "empty", "partial", "error"}
    assert body["trace_id"] is None
    assert "scorecard_count" in body["data"]
    assert "pipeline_stage_count" in body["data"]
    assert "trace_count" in body["data"]
    assert "required_field_gaps" in body["data"]
    assert "Traceback" not in raw
    assert "/Users/" not in raw
    assert "evt_" not in raw

    status, body, _ = _request(project_server, "POST", "/api/project/traces/latest")
    assert status == 405
    assert body["status"] == "error"

    status, body, _ = _request(project_server, "PUT", "/api/project/traces/latest", body={})
    assert status == 405
    assert body["status"] == "error"

    status, body, _ = _request(project_server, "PATCH", "/api/project/traces/latest", body={})
    assert status == 405
    assert body["status"] == "error"

    status, body, _ = _request(project_server, "DELETE", "/api/project/traces/latest")
    assert status == 405
    assert body["status"] == "error"


def test_project_trace_api_latest_trace_id_matches_snapshot_or_empty(logs_dir: Path):
    empty_server, thread = _serve(logs_dir)
    try:
        status, body, raw = _request(empty_server, "GET", "/api/project/traces/latest")
        assert status == 200
        assert body["schema_version"] == "project.api.v1"
        assert body["status"] == "empty"
        assert body["trace_id"] is None
        assert body["data"]["scorecard"] is None
        assert body["data"]["pipeline_stages"] == []
        assert "evt_" not in raw
    finally:
        empty_server.shutdown()
        empty_server.server_close()
        thread.join(timeout=2)


def test_project_trace_api_error_path_is_safely_wrapped(monkeypatch, logs_dir: Path):
    monkeypatch.setattr(ProjectTraceReader, "trace_detail", lambda self, trace_id: (_ for _ in ()).throw(RuntimeError("boom")))
    server, thread = _serve(logs_dir)
    try:
        status, body, raw = _request(server, "GET", "/api/project/trace/ME-PR-1-ERR")
        assert status == 500
        assert body["status"] == "error"
        assert "Traceback" not in raw
        assert "/Users/" not in raw
        assert "boom" not in raw
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
