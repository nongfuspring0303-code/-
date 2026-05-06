#!/usr/bin/env python3
from __future__ import annotations

import json
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from system_log_evaluator import build_daily_report_md, build_provider_health_hourly, build_system_health_daily


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOGS_DIR = ROOT / "logs"
API_SCHEMA_VERSION = "project.api.v1"


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _short_request_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _safe_str(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _safe_list_of_str(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = _safe_str(item)
        if text:
            out.append(text)
    return out


def _safe_timestamp(value: Any) -> str | None:
    text = _safe_str(value)
    if not text:
        return None
    try:
        ts = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _hour_bucket(value: Any) -> str | None:
    ts = _safe_timestamp(value)
    if not ts:
        return None
    return ts[:13] + ":00:00Z"


@dataclass
class LoadResult:
    rows: list[dict[str, Any]]
    bad_lines: list[dict[str, Any]]


class ProjectTraceReader:
    def __init__(self, logs_dir: Path | None = None):
        self.logs_dir = Path(logs_dir) if logs_dir else DEFAULT_LOGS_DIR

    def _read_jsonl(self, filename: str) -> LoadResult:
        path = self.logs_dir / filename
        if not path.exists():
            return LoadResult(rows=[], bad_lines=[])

        rows: list[dict[str, Any]] = []
        bad_lines: list[dict[str, Any]] = []
        for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except Exception:
                bad_lines.append(
                    {
                        "code": "BAD_JSONL_LINE",
                        "message": f"Skipped unreadable JSONL line in {filename}.",
                        "file": filename,
                        "line": line_no,
                    }
                )
                continue
            if not isinstance(payload, dict):
                bad_lines.append(
                    {
                        "code": "NON_OBJECT_JSONL_ROW",
                        "message": f"Skipped non-object JSONL row in {filename}.",
                        "file": filename,
                        "line": line_no,
                    }
                )
                continue
            rows.append(payload)
        return LoadResult(rows=rows, bad_lines=bad_lines)

    def _scorecard_record(self, row: dict[str, Any]) -> dict[str, Any]:
        scores = row.get("scores") if isinstance(row.get("scores"), dict) else {}
        return {
            "trace_id": _safe_str(row.get("trace_id")),
            "request_id": _safe_str(row.get("request_id")),
            "logged_at": _safe_timestamp(row.get("logged_at")),
            "final_action": _safe_str(row.get("final_action")),
            "final_reason": _safe_str(row.get("final_reason")),
            "total_score": _safe_float(scores.get("total_score")),
            "grade": _safe_str(scores.get("grade")),
            "sector_quality_score": _safe_float(row.get("sector_quality_score")),
            "ticker_quality_score": _safe_float(row.get("ticker_quality_score")),
            "output_quality_score": _safe_float(row.get("output_quality_score")),
            "a_gate_blocker_codes": _safe_list_of_str(row.get("a_gate_blocker_codes")),
            "a_gate_blocker_count": _safe_int(row.get("a_gate_blocker_count")),
            "a_gate_blocker_present": bool(row.get("a_gate_blocker_present", False)),
        }

    def _pipeline_record(self, row: dict[str, Any]) -> dict[str, Any]:
        details = row.get("details") if isinstance(row.get("details"), dict) else {}
        errors = row.get("errors")
        if not isinstance(errors, list):
            errors = details.get("errors") if isinstance(details.get("errors"), list) else []
        return {
            "trace_id": _safe_str(row.get("trace_id")),
            "stage": _safe_str(row.get("stage")),
            "status": _safe_str(row.get("status")),
            "timestamp": _safe_timestamp(row.get("logged_at")),
            "errors": _safe_list_of_str(errors),
            "stage_seq": _safe_int(row.get("stage_seq")),
        }

    def _valid_required_fields(self, row: dict[str, Any], required: list[str]) -> list[str]:
        missing: list[str] = []
        for field in required:
            value = row.get(field)
            if value in ("", None):
                missing.append(field)
        return missing

    def _scorecard_required_gaps(self, row: dict[str, Any]) -> list[str]:
        # Field matrix v1.2 keeps the scorecard required set minimal for PR-1.
        return self._valid_required_fields(row, ["trace_id", "final_action"])

    def _scorecard_rows(self) -> LoadResult:
        return self._read_jsonl("trace_scorecard.jsonl")

    def _pipeline_rows(self) -> LoadResult:
        return self._read_jsonl("pipeline_stage.jsonl")

    def latest_trace(self) -> dict[str, Any]:
        scorecards = self._scorecard_rows()
        pipeline = self._pipeline_rows()
        errors = scorecards.bad_lines + pipeline.bad_lines
        if not scorecards.rows:
            if pipeline.rows:
                latest_pipeline = max(pipeline.rows, key=lambda row: _safe_timestamp(row.get("logged_at")) or "")
                trace_id = _safe_str(latest_pipeline.get("trace_id"))
                matching_pipeline = [
                    self._pipeline_record(row)
                    for row in pipeline.rows
                    if _safe_str(row.get("trace_id")) == trace_id
                ]
                matching_pipeline.sort(
                    key=lambda item: (item.get("stage_seq") is None, item.get("stage_seq") or 0, item.get("timestamp") or "")
                )
                return {
                    "status": "partial" if errors or matching_pipeline else "empty",
                    "message": "Pipeline trace loaded without scorecard.",
                    "errors": errors,
                    "data": {
                        "scorecard": None,
                        "pipeline_stages": matching_pipeline,
                    },
                    "trace_id": trace_id,
                }
            return {
                "status": "empty" if not errors else "partial",
                "message": "No trace scorecards are available.",
                "errors": errors,
                "data": {
                    "scorecard": None,
                    "pipeline_stages": [],
                },
                "trace_id": None,
            }

        latest_row = max(scorecards.rows, key=lambda row: _safe_timestamp(row.get("logged_at")) or "")
        trace_id = _safe_str(latest_row.get("trace_id"))
        matching_pipeline = [
            self._pipeline_record(row)
            for row in pipeline.rows
            if _safe_str(row.get("trace_id")) == trace_id
        ]
        matching_pipeline.sort(key=lambda item: (item.get("stage_seq") is None, item.get("stage_seq") or 0, item.get("timestamp") or ""))

        required_missing = self._scorecard_required_gaps(latest_row)
        status = "ok"
        if errors or required_missing:
            status = "partial"

        return {
            "status": status,
            "message": "Latest trace snapshot loaded.",
            "errors": errors + [{"code": "MISSING_REQUIRED_FIELD", "fields": required_missing}] if required_missing else errors,
            "trace_id": trace_id,
            "data": {
                "scorecard": self._scorecard_record(latest_row),
                "pipeline_stages": matching_pipeline,
            },
        }

    def trace_detail(self, trace_id: str) -> dict[str, Any]:
        lookup = _safe_str(trace_id)
        if not lookup:
            return {
                "status": "empty",
                "message": "Trace id is missing.",
                "errors": [{"code": "MISSING_TRACE_ID", "message": "Trace id is required."}],
                "trace_id": None,
                "data": {"scorecard": None, "pipeline_stages": []},
            }

        scorecards = self._scorecard_rows()
        pipeline = self._pipeline_rows()
        errors = scorecards.bad_lines + pipeline.bad_lines

        matching_scorecards = [row for row in scorecards.rows if _safe_str(row.get("trace_id")) == lookup]
        matching_pipeline = [row for row in pipeline.rows if _safe_str(row.get("trace_id")) == lookup]

        if not matching_scorecards and not matching_pipeline:
            return {
                "status": "empty",
                "message": "Trace not found.",
                "errors": errors,
                "trace_id": lookup,
                "data": {"scorecard": None, "pipeline_stages": []},
            }

        latest_scorecard = None
        if matching_scorecards:
            latest_scorecard = max(matching_scorecards, key=lambda row: _safe_timestamp(row.get("logged_at")) or "")

        pipeline_records = [self._pipeline_record(row) for row in matching_pipeline]
        pipeline_records.sort(key=lambda item: (item.get("stage_seq") is None, item.get("stage_seq") or 0, item.get("timestamp") or ""))

        required_missing: list[str] = []
        if latest_scorecard is not None:
            required_missing.extend(self._scorecard_required_gaps(latest_scorecard))
        if pipeline_records:
            for index, item in enumerate(pipeline_records):
                for field in ("trace_id", "stage", "status", "timestamp"):
                    if item.get(field) in ("", None):
                        required_missing.append(f"pipeline[{index}].{field}")

        status = "ok"
        if errors or required_missing:
            status = "partial"
        if latest_scorecard is None:
            status = "partial" if errors or matching_pipeline else "empty"

        return {
            "status": status,
            "message": "Trace detail loaded.",
            "errors": errors + [{"code": "MISSING_REQUIRED_FIELD", "fields": required_missing}] if required_missing else errors,
            "trace_id": lookup,
            "data": {
                "scorecard": self._scorecard_record(latest_scorecard) if latest_scorecard else None,
                "pipeline_stages": pipeline_records,
            },
        }

    def latest_scorecard(self) -> dict[str, Any]:
        scorecards = self._scorecard_rows()
        errors = scorecards.bad_lines
        if not scorecards.rows:
            return {
                "status": "empty" if not errors else "partial",
                "message": "No scorecards are available.",
                "errors": errors,
                "trace_id": None,
                "data": {"scorecard": None},
            }

        latest_row = max(scorecards.rows, key=lambda row: _safe_timestamp(row.get("logged_at")) or "")
        required_missing = self._scorecard_required_gaps(latest_row)
        status = "ok"
        if errors or required_missing:
            status = "partial"
        return {
            "status": status,
            "message": "Latest scorecard loaded.",
            "errors": errors + [{"code": "MISSING_REQUIRED_FIELD", "fields": required_missing}] if required_missing else errors,
            "trace_id": _safe_str(latest_row.get("trace_id")),
            "data": {"scorecard": self._scorecard_record(latest_row)},
        }

    def gap_report(self) -> dict[str, Any]:
        scorecards = self._scorecard_rows()
        pipeline = self._pipeline_rows()
        bad_lines = scorecards.bad_lines + pipeline.bad_lines

        scorecard_ids = {sid for sid in (_safe_str(row.get("trace_id")) for row in scorecards.rows) if sid}
        pipeline_ids = {sid for sid in (_safe_str(row.get("trace_id")) for row in pipeline.rows) if sid}
        trace_ids = sorted(scorecard_ids | pipeline_ids)

        missing_scorecard = sorted(pipeline_ids - scorecard_ids)
        missing_pipeline = sorted(scorecard_ids - pipeline_ids)

        required_gaps: list[dict[str, Any]] = []
        for row in scorecards.rows:
            missing = self._scorecard_required_gaps(row)
            if missing:
                required_gaps.append({"trace_id": _safe_str(row.get("trace_id")), "source": "trace_scorecard.jsonl", "missing": missing})
        for row in pipeline.rows:
            missing = self._valid_required_fields(row, ["trace_id", "stage", "status", "logged_at"])
            if missing:
                required_gaps.append({"trace_id": _safe_str(row.get("trace_id")), "source": "pipeline_stage.jsonl", "missing": missing})

        status = "ok"
        if bad_lines or required_gaps or missing_scorecard or missing_pipeline:
            status = "partial"

        return {
            "status": status,
            "message": "Gap report loaded.",
            "errors": bad_lines + [{"code": "MISSING_REQUIRED_FIELD", "items": required_gaps}] if required_gaps else bad_lines,
            "trace_id": None,
            "data": {
                "scorecard_count": len(scorecards.rows),
                "pipeline_stage_count": len(pipeline.rows),
                "trace_count": len(trace_ids),
                "traces_missing_scorecard": missing_scorecard,
                "traces_missing_pipeline": missing_pipeline,
                "required_field_gaps": required_gaps,
            },
        }

    def system_health(self) -> dict[str, Any]:
        raw_ingest = self._read_jsonl("raw_news_ingest.jsonl")
        market = self._read_jsonl("market_data_provenance.jsonl")
        pipeline = self._read_jsonl("pipeline_stage.jsonl")
        decision = self._read_jsonl("decision_gate.jsonl")
        rejected = self._read_jsonl("rejected_events.jsonl")
        quarantine = self._read_jsonl("quarantine_replay.jsonl")
        replay_write = self._read_jsonl("replay_write.jsonl")
        execution_emit = self._read_jsonl("execution_emit.jsonl")
        scorecards = self._read_jsonl("trace_scorecard.jsonl")

        all_errors = (
            raw_ingest.bad_lines
            + market.bad_lines
            + pipeline.bad_lines
            + decision.bad_lines
            + rejected.bad_lines
            + quarantine.bad_lines
            + replay_write.bad_lines
            + execution_emit.bad_lines
            + scorecards.bad_lines
        )

        provider_health = build_provider_health_hourly(market.rows)
        system_health = build_system_health_daily(
            raw_ingest_rows=raw_ingest.rows,
            pipeline_rows=pipeline.rows,
            decision_rows=decision.rows,
            rejected_rows=rejected.rows,
            quarantine_rows=quarantine.rows,
            replay_write_rows=replay_write.rows,
            execution_emit_rows=execution_emit.rows,
            trace_scorecard_rows=scorecards.rows,
            gate_enabled=True,
        )
        report_md = build_daily_report_md(provider_health=provider_health, system_health=system_health)

        status = "ok"
        if all_errors:
            status = "partial"
        elif not any((provider_health, system_health)):
            status = "empty"

        return {
            "status": status,
            "message": "System health snapshot loaded.",
            "errors": all_errors,
            "trace_id": None,
            "data": {
                "provider_health_hourly": provider_health,
                "system_health_daily": system_health,
                "daily_report_markdown": report_md,
            },
        }


def build_api_envelope(
    *,
    status: str,
    message: str,
    data: dict[str, Any],
    trace_id: str | None,
    request_id: str | None = None,
    errors: list[dict[str, Any]] | None = None,
    retryable: bool = False,
    code: str = "OK",
) -> dict[str, Any]:
    return {
        "schema_version": API_SCHEMA_VERSION,
        "status": status,
        "code": code,
        "message": message,
        "trace_id": trace_id or _short_request_id("evt"),
        "request_id": request_id or _short_request_id("req"),
        "generated_at": _now_utc_iso(),
        "retryable": retryable,
        "errors": errors or [],
        "data": data,
    }
