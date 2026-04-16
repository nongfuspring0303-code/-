#!/usr/bin/env python3
"""Theme replay and idempotency verifier for member B."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from theme_gate_policy import apply_theme_gate_constraints, validate_theme_contract


def build_idempotency_key(event_id: str, config_version: str, evaluation_window: str) -> str:
    return f"{event_id}|{config_version}|{evaluation_window}"


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(payload: Any) -> str:
    return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _load_records(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        records: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
        return records

    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [dict(item) for item in payload]
    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        return [dict(item) for item in payload["records"]]
    raise TypeError("Unsupported replay input format")


def _resolve_record(record: Mapping[str, Any]) -> dict[str, Any]:
    event_id = str(record["event_id"])
    config_version = str(record.get("config_version") or "unknown_config_version")
    evaluation_window = str(record.get("evaluation_window") or "T0")
    input_snapshot = record.get("input_snapshot", {})
    output_snapshot = record.get("output_snapshot", {})
    return {
        "event_id": event_id,
        "config_version": config_version,
        "evaluation_window": evaluation_window,
        "idempotency_key": build_idempotency_key(event_id, config_version, evaluation_window),
        "input_snapshot": input_snapshot,
        "output_snapshot": apply_theme_gate_constraints(output_snapshot),
    }


@dataclass
class ReplayRecord:
    idempotency_key: str
    input_digest: str
    output_digest: str


def verify_replay_consistency(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, ReplayRecord] = {}
    inconsistent_keys: list[str] = []
    contract_errors: list[str] = []

    for record in records:
        resolved = _resolve_record(record)
        errors = validate_theme_contract(resolved["output_snapshot"])
        contract_errors.extend(errors)

        item = ReplayRecord(
            idempotency_key=resolved["idempotency_key"],
            input_digest=_digest(resolved["input_snapshot"]),
            output_digest=_digest(resolved["output_snapshot"]),
        )
        prior = grouped.get(item.idempotency_key)
        if prior and (prior.input_digest != item.input_digest or prior.output_digest != item.output_digest):
            inconsistent_keys.append(item.idempotency_key)
        else:
            grouped[item.idempotency_key] = item

    replay_consistency = not inconsistent_keys and not contract_errors
    return {
        "replay_consistency": replay_consistency,
        "idempotency_strategy": "event_id|config_version|evaluation_window",
        "total_records": len(records),
        "unique_keys": len(grouped),
        "inconsistent_keys": sorted(set(inconsistent_keys)),
        "contract_errors": contract_errors,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify theme replay/idempotency consistency.")
    parser.add_argument("--input-json", type=Path, help="Path to JSON array/object input.", default=None)
    parser.add_argument("--input-jsonl", type=Path, help="Path to JSONL replay input.", default=None)
    parser.add_argument("--output-json", type=Path, help="Optional output report path.", default=None)
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    if not args.input_json and not args.input_jsonl:
        parser.error("one of --input-json or --input-jsonl is required")

    input_path = args.input_json or args.input_jsonl
    assert input_path is not None
    records = _load_records(input_path)
    report = verify_replay_consistency(records)
    if args.output_json:
        args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["replay_consistency"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
