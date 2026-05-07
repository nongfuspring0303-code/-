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
MAX_JSONL_TAIL_LINES = 2000


def _error_item(
    *,
    code: str,
    message: str,
    source: str,
    retryable: bool = False,
    severity: str = "error",
    field: str | None = None,
    line: int | None = None,
    module: str | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "code": code,
        "message": message,
        "source": source,
        "retryable": retryable,
        "severity": severity,
    }
    if field is not None:
        item["field"] = field
    if line is not None:
        item["line"] = line
    if module is not None:
        item["module"] = module
    return item


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

    def _read_jsonl_tail_lines(self, path: Path, max_lines: int = MAX_JSONL_TAIL_LINES) -> list[str]:
        """Read only tail lines to avoid loading large JSONL files fully into memory."""
        if max_lines <= 0:
            return []
        with path.open("rb") as fp:
            fp.seek(0, 2)
            pos = fp.tell()
            chunks: list[bytes] = []
            newline_count = 0
            chunk_size = 65536
            while pos > 0 and newline_count <= max_lines:
                read_size = chunk_size if pos >= chunk_size else pos
                pos -= read_size
                fp.seek(pos)
                chunk = fp.read(read_size)
                chunks.append(chunk)
                newline_count += chunk.count(b"\n")
            content = b"".join(reversed(chunks)).decode("utf-8", errors="replace")
            lines = content.splitlines()
            if len(lines) > max_lines:
                lines = lines[-max_lines:]
            return lines

    def _read_jsonl(self, filename: str) -> LoadResult:
        path = self.logs_dir / filename
        if not path.exists():
            return LoadResult(rows=[], bad_lines=[])

        rows: list[dict[str, Any]] = []
        bad_lines: list[dict[str, Any]] = []
        for line_no, raw_line in enumerate(self._read_jsonl_tail_lines(path), start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except Exception:
                bad_lines.append(
                    _error_item(
                        code="BAD_JSONL_LINE",
                        message=f"Skipped unreadable JSONL line in {filename}.",
                        source=filename,
                        severity="warning",
                        line=line_no,
                    )
                )
                continue
            if not isinstance(payload, dict):
                bad_lines.append(
                    _error_item(
                        code="NON_OBJECT_JSONL_ROW",
                        message=f"Skipped non-object JSONL row in {filename}.",
                        source=filename,
                        severity="warning",
                        line=line_no,
                    )
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

    def _find_trace_payload(self, trace_id: str) -> dict[str, Any] | None:
        candidates = [
            "event_bus_live.jsonl",
            "event_bus_live.json",
            "action_card_replay.jsonl",
            "action_card_replay.json",
        ]
        for filename in candidates:
            result = self._read_jsonl(filename)
            for row in reversed(result.rows):
                if _safe_str(row.get("trace_id")) == trace_id:
                    return row
        return None

    def _extract_trace_modules(
        self,
        *,
        trace_id: str,
        scorecard_row: dict[str, Any] | None,
        trace_payload: dict[str, Any] | None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        modules: dict[str, Any] = {
            "event": trace_payload or {},
            "lifecycle_fatigue_contract": None,
            "execution_suggestion": None,
            "path_quality_eval": None,
            "trace_scorecard": self._scorecard_record(scorecard_row) if scorecard_row else None,
            "risk_blocker_reason": None,
        }
        errors: list[dict[str, Any]] = []

        analysis = trace_payload.get("analysis") if isinstance(trace_payload, dict) and isinstance(trace_payload.get("analysis"), dict) else {}
        execution = trace_payload.get("execution") if isinstance(trace_payload, dict) and isinstance(trace_payload.get("execution"), dict) else {}

        lifecycle = analysis.get("lifecycle_fatigue_contract")
        if lifecycle is not None:
            modules["lifecycle_fatigue_contract"] = lifecycle
        else:
            errors.append(
                _error_item(
                    code="MODULE_MISSING",
                    message="lifecycle_fatigue_contract is not available for this trace.",
                    source="lifecycle_fatigue_contract",
                    module="lifecycle_fatigue_contract",
                    severity="warning",
                )
            )

        execution_suggestion = analysis.get("execution_suggestion")
        if execution_suggestion is not None:
            modules["execution_suggestion"] = execution_suggestion
        else:
            errors.append(
                _error_item(
                    code="MODULE_MISSING",
                    message="execution_suggestion is not available for this trace.",
                    source="execution_suggestion",
                    module="execution_suggestion",
                    severity="warning",
                )
            )

        path_quality = analysis.get("path_quality_eval")
        if path_quality is not None:
            modules["path_quality_eval"] = path_quality
        else:
            errors.append(
                _error_item(
                    code="MODULE_MISSING",
                    message="path_quality_eval is not available for this trace.",
                    source="path_quality_eval",
                    module="path_quality_eval",
                    severity="warning",
                )
            )

        if modules["trace_scorecard"] is None:
            errors.append(
                _error_item(
                    code="MODULE_MISSING",
                    message="trace_scorecard is not available for this trace.",
                    source="trace_scorecard",
                    module="trace_scorecard",
                    severity="warning",
                )
            )

        final_data = execution.get("final") if isinstance(execution.get("final"), dict) else {}
        if final_data:
            modules["risk_blocker_reason"] = _safe_str(final_data.get("reason")) or _safe_str(final_data.get("block_reason"))

        return modules, errors

    def _scorecard_rows(self) -> LoadResult:
        return self._read_jsonl("trace_scorecard.jsonl")

    def _pipeline_rows(self) -> LoadResult:
        return self._read_jsonl("pipeline_stage.jsonl")

    def _timestamp_from_row(self, row: dict[str, Any]) -> str:
        return _safe_timestamp(row.get("timestamp") or row.get("logged_at")) or ""

    def latest_traces(self, limit: int = 20) -> dict[str, Any]:
        scorecards = self._scorecard_rows()
        pipeline = self._pipeline_rows()
        errors = scorecards.bad_lines + pipeline.bad_lines
        trace_ids = sorted({
            _safe_str(row.get("trace_id"))
            for row in (scorecards.rows + pipeline.rows)
            if _safe_str(row.get("trace_id"))
        })
        if not trace_ids:
            empty_status = "empty" if not errors else "partial"
            return {
                "status": empty_status,
                "code": "PARTIAL_TRACE_LIST" if empty_status == "partial" else "EMPTY",
                "message": "No trace scorecards are available.",
                "errors": errors,
                "trace_id": None,
                "data": {
                    "items": [],
                    "scorecard": None,
                    "pipeline_stages": [],
                    "limit": limit,
                    "count": 0,
                    "next_cursor": None,
                },
            }

        def _trace_sort_key(trace_id: str) -> tuple[str, str]:
            scorecard_rows = [row for row in scorecards.rows if _safe_str(row.get("trace_id")) == trace_id]
            pipeline_rows = [row for row in pipeline.rows if _safe_str(row.get("trace_id")) == trace_id]
            latest_scorecard_ts = max((self._timestamp_from_row(row) for row in scorecard_rows), default="")
            latest_pipeline_ts = max((self._timestamp_from_row(row) for row in pipeline_rows), default="")
            latest_ts = max(latest_scorecard_ts, latest_pipeline_ts)
            return (latest_ts, trace_id)

        trace_ids.sort(key=_trace_sort_key, reverse=True)
        items: list[dict[str, Any]] = []
        required_missing_entries: list[dict[str, Any]] = []

        for trace_id in trace_ids[:max(1, limit)]:
            matching_scorecards = [row for row in scorecards.rows if _safe_str(row.get("trace_id")) == trace_id]
            latest_scorecard = max(matching_scorecards, key=lambda row: self._timestamp_from_row(row)) if matching_scorecards else None
            matching_pipeline = [
                self._pipeline_record(row)
                for row in pipeline.rows
                if _safe_str(row.get("trace_id")) == trace_id
            ]
            matching_pipeline.sort(
                key=lambda item: (item.get("stage_seq") is None, item.get("stage_seq") or 0, item.get("timestamp") or "")
            )
            item_scorecard = self._scorecard_record(latest_scorecard) if latest_scorecard else None
            items.append({
                "trace_id": trace_id,
                "scorecard": item_scorecard,
                "pipeline_stages": matching_pipeline,
            })
            if latest_scorecard is not None:
                missing = self._scorecard_required_gaps(latest_scorecard)
                if missing:
                    for field in missing:
                        required_missing_entries.append(
                            _error_item(
                                code="REQUIRED_FIELD_MISSING",
                                message=f"Required field {field} is missing.",
                                source="trace_scorecard.jsonl",
                                field=field,
                                module="trace_scorecard",
                                severity="error",
                                retryable=False,
                            )
                        )

        status = "ok"
        if errors or required_missing_entries:
            status = "partial"

        top_item = items[0] if items else None
        return {
            "status": status,
            "code": "PARTIAL_TRACE_LIST" if status == "partial" else ("EMPTY" if status == "empty" else "OK"),
            "message": "Latest trace list loaded.",
            "errors": errors + required_missing_entries,
            "trace_id": top_item["trace_id"] if top_item else None,
            "data": {
                "items": items,
                "scorecard": top_item["scorecard"] if top_item else None,
                "pipeline_stages": top_item["pipeline_stages"] if top_item else [],
                "limit": limit,
                "count": len(items),
                "next_cursor": None,
            },
        }

    def latest_trace(self) -> dict[str, Any]:
        return self.latest_traces(limit=1)

    def trace_detail(self, trace_id: str) -> dict[str, Any]:
        lookup = _safe_str(trace_id)
        if not lookup:
            return {
                "status": "error",
                "code": "MISSING_TRACE_ID",
                "message": "Trace id is missing.",
                "errors": [
                    _error_item(
                        code="MISSING_TRACE_ID",
                        message="Trace id is required.",
                        source="trace_detail",
                        field="trace_id",
                    )
                ],
                "trace_id": None,
                "http_status": 404,
                "data": None,
            }

        scorecards = self._scorecard_rows()
        pipeline = self._pipeline_rows()
        errors = scorecards.bad_lines + pipeline.bad_lines

        matching_scorecards = [row for row in scorecards.rows if _safe_str(row.get("trace_id")) == lookup]
        matching_pipeline = [row for row in pipeline.rows if _safe_str(row.get("trace_id")) == lookup]

        trace_payload = self._find_trace_payload(lookup)
        if not matching_scorecards and not matching_pipeline and trace_payload is None:
            return {
                "status": "error",
                "code": "TRACE_NOT_FOUND",
                "message": "Trace not found.",
                "errors": errors
                + [
                    _error_item(
                        code="TRACE_NOT_FOUND",
                        message="Trace id does not exist in available logs.",
                        source="trace_detail",
                        field="trace_id",
                    )
                ],
                "trace_id": lookup,
                "http_status": 404,
                "data": None,
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

        modules, module_errors = self._extract_trace_modules(
            trace_id=lookup,
            scorecard_row=latest_scorecard,
            trace_payload=trace_payload,
        )

        status = "ok"
        if errors or required_missing or module_errors:
            status = "partial"
        if latest_scorecard is None and not matching_pipeline:
            status = "partial" if errors or module_errors else "empty"

        missing_field_errors = [
            _error_item(
                code="REQUIRED_FIELD_MISSING",
                message=f"Required field {field} is missing.",
                source="trace_detail",
                field=field,
                severity="error",
            )
            for field in required_missing
        ]
        analysis_payload = {
            "event": modules["event"],
            "lifecycle_fatigue_contract": modules["lifecycle_fatigue_contract"],
            "execution_suggestion": modules["execution_suggestion"],
            "path_quality_eval": modules["path_quality_eval"],
            "trace_scorecard": modules["trace_scorecard"],
            "risk_blocker_reason": modules["risk_blocker_reason"],
        }
        is_advisory_only = bool(modules["execution_suggestion"] is not None)
        return {
            "status": status,
            "code": "PARTIAL_TRACE_DETAIL" if status == "partial" else ("EMPTY" if status == "empty" else "OK"),
            "message": "Trace detail loaded.",
            "errors": errors + module_errors + missing_field_errors,
            "trace_id": lookup,
            "data": {
                "request_id": _safe_str(trace_payload.get("request_id")) if isinstance(trace_payload, dict) else None,
                "is_advisory_only": is_advisory_only,
                "analysis": analysis_payload,
                "event": modules["event"],
                "lifecycle_fatigue_contract": modules["lifecycle_fatigue_contract"],
                "execution_suggestion": modules["execution_suggestion"],
                "path_quality_eval": modules["path_quality_eval"],
                "trace_scorecard": modules["trace_scorecard"],
                "risk_blocker_reason": modules["risk_blocker_reason"],
                "scorecard": modules["trace_scorecard"],
                "pipeline_stages": pipeline_records,
            },
        }

    def latest_scorecard(self) -> dict[str, Any]:
        scorecards = self._scorecard_rows()
        errors = scorecards.bad_lines
        if not scorecards.rows:
            empty_status = "empty" if not errors else "partial"
            return {
                "status": empty_status,
                "code": "PARTIAL_SCORECARD" if empty_status == "partial" else "EMPTY",
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
        required_errors = [
            _error_item(
                code="REQUIRED_FIELD_MISSING",
                message=f"Required field {field} is missing.",
                source="trace_scorecard.jsonl",
                field=field,
                module="trace_scorecard",
                severity="error",
                retryable=False,
            )
            for field in required_missing
        ]
        return {
            "status": status,
            "code": "PARTIAL_SCORECARD" if status == "partial" else ("EMPTY" if status == "empty" else "OK"),
            "message": "Latest scorecard loaded.",
            "errors": errors + required_errors,
            "trace_id": _safe_str(latest_row.get("trace_id")),
            "data": {"scorecard": self._scorecard_record(latest_row)},
        }

    def gap_report(self) -> dict[str, Any]:
        return {
            "status": "empty",
            "code": "GAP_REPORT_NOT_READY",
            "message": "Project gap report is not generated yet.",
            "errors": [],
            "trace_id": None,
            "data": None,
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
            "code": "PARTIAL_SYSTEM_HEALTH" if status == "partial" else ("EMPTY" if status == "empty" else "OK"),
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
    data: Any,
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
        "trace_id": trace_id,
        "request_id": request_id or _short_request_id("req"),
        "generated_at": _now_utc_iso(),
        "retryable": retryable,
        "errors": errors or [],
        "data": data,
    }
