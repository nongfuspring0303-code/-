#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = ROOT / "tests"
CASES_DIR = TESTS_DIR / "golden_cases"
ACCEPTANCE_DIR = TESTS_DIR / "acceptance"
THRESHOLDS_PATH = ACCEPTANCE_DIR / "scoring_thresholds.yaml"
LOG_DIR = ROOT / "logs" / "acceptance"
REPORT_JSON = LOG_DIR / "latest_acceptance_report.json"
REPORT_MD = LOG_DIR / "latest_acceptance_report.md"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from intel_modules import SourceRankerModule
from opportunity_score import OpportunityScorer
from transmission_engine.core.path_adjudicator import PathAdjudicator
from transmission_engine.core.path_router import PathRouter


ACTION_LEVEL = {
    "BLOCK": 0,
    "PENDING_CONFIRM": 1,
    "WATCH": 2,
    "EXECUTE": 3,
}


@dataclass
class CaseCheck:
    case_id: str
    chain_ok: bool
    fields_ok: bool
    path_ok: bool
    signal_ok: bool
    risk_ok: bool
    mixed_regime_ok: bool
    final_ok: bool
    details: Dict[str, Any]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_thresholds(path: Path) -> Dict[str, float]:
    with path.open("r", encoding="utf-8") as f:
        payload = yaml.safe_load(f) or {}
    return {
        "chain_completeness_min": float(payload.get("chain_completeness_min", 0.95)),
        "required_fields_missing_rate_max": float(payload.get("required_fields_missing_rate_max", 0.01)),
        "direction_consistency_min": float(payload.get("direction_consistency_min", 0.80)),
        "path_consistency_min": float(payload.get("path_consistency_min", 0.75)),
        "high_risk_false_release_max": float(payload.get("high_risk_false_release_max", 0.05)),
    }


def _simple_schema_check(case: Dict[str, Any]) -> Tuple[bool, str]:
    for key in ("case_id", "category", "description", "input", "expect"):
        if key not in case:
            return False, f"missing key: {key}"
    for key in ("headline", "raw_text", "source_type", "source_url", "timestamp"):
        if key not in case["input"]:
            return False, f"missing input.{key}"
    for key in (
        "required_fields",
        "allowed_signals",
        "forbidden_signals",
        "expected_path_types_any_of",
        "max_final_action",
    ):
        if key not in case["expect"]:
            return False, f"missing expect.{key}"
    return True, ""


def _iter_case_files() -> List[Path]:
    return sorted(CASES_DIR.glob("**/*.json"))


def _load_cases() -> List[Dict[str, Any]]:
    cases: List[Dict[str, Any]] = []
    for p in _iter_case_files():
        with p.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        ok, msg = _simple_schema_check(payload)
        if not ok:
            raise ValueError(f"Invalid case {p}: {msg}")
        payload["_path"] = str(p)
        cases.append(payload)
    return cases


def _run_layer0_healthcheck() -> Dict[str, Any]:
    cmd = [sys.executable, str(ROOT / "scripts" / "system_healthcheck.py"), "--mode", "dev"]
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    return {
        "passed": proc.returncode == 0,
        "returncode": proc.returncode,
        "command": " ".join(cmd),
        "output_preview": "\n".join(output.splitlines()[:20]),
        "checked_at": _utc_now(),
    }


def _default_scenario(case: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "sectors": [{"name": "科技", "direction": "WATCH", "impact_score": 0.6, "confidence": 0.6}],
        "stock_candidates": [{"symbol": "NVDA", "sector": "科技", "direction": "WATCH", "event_beta": 1.0}],
        "asset_validation": {"score": 60},
    }


def _build_compiled_output(
    case: Dict[str, Any],
    source_rank: str,
    dominant_path: Dict[str, Any],
    mixed_regime: bool,
    opportunity_out: Dict[str, Any],
) -> Dict[str, Any]:
    opps = opportunity_out.get("opportunities", [])
    signals = sorted({str(item.get("signal", "")) for item in opps if item.get("signal")})
    final_actions = [str(item.get("final_action", "WATCH")) for item in opps]

    strongest = "BLOCK"
    for action in final_actions + [str(opportunity_out.get("action", "WATCH"))]:
        if ACTION_LEVEL.get(action, -1) > ACTION_LEVEL.get(strongest, -1):
            strongest = action

    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "source_rank": source_rank,
        "dominant_path": dominant_path,
        "mixed_regime": mixed_regime,
        "opportunities": opps,
        "signals": signals,
        "state_machine_step": opportunity_out.get("state_machine_step"),
        "gate_reason_code": opportunity_out.get("gate_reason_code"),
        "action": opportunity_out.get("action"),
        "strongest_final_action": strongest,
    }


def _check_fields(output: Dict[str, Any], expected: Dict[str, Any]) -> Tuple[bool, List[str]]:
    missing: List[str] = []
    for field in expected.get("required_fields", []):
        if field not in output or output.get(field) is None:
            missing.append(field)
    if bool(expected.get("must_have_gate_reason_code", False)) and not output.get("gate_reason_code"):
        missing.append("gate_reason_code")
    return len(missing) == 0, missing


def _check_mixed_regime(output: Dict[str, Any], expected: Dict[str, Any]) -> Tuple[bool, str]:
    """Check mixed_regime assertion if must_have_mixed_regime is set."""
    if not bool(expected.get("must_have_mixed_regime", False)):
        return True, "not_required"
    actual = bool(output.get("mixed_regime", False))
    if actual:
        return True, "mixed_regime_detected"
    return False, "expected_mixed_regime_but_not_detected"


def _check_signal(output: Dict[str, Any], expected: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    signals = set(output.get("signals", []))
    allow_empty = bool(expected.get("allow_empty_opportunities", False))
    forbidden = set(expected.get("forbidden_signals", []))
    allowed = set(expected.get("allowed_signals", []))

    if not signals and not allow_empty:
        return False, {"reason": "empty_signals", "signals": []}
    if signals & forbidden:
        return False, {"reason": "forbidden_signal", "signals": sorted(signals)}
    if signals and not signals.issubset(allowed):
        return False, {"reason": "outside_allowed_signals", "signals": sorted(signals)}
    return True, {"signals": sorted(signals)}


def _check_path(output: Dict[str, Any], expected: Dict[str, Any]) -> Tuple[bool, str]:
    path_type = str((output.get("dominant_path") or {}).get("path_type", ""))
    expected_types = set(expected.get("expected_path_types_any_of", []))
    return path_type in expected_types, path_type


def _check_risk(output: Dict[str, Any], expected: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    actual = str(output.get("strongest_final_action", "BLOCK"))
    max_expected = str(expected.get("max_final_action", "WATCH"))
    ok = ACTION_LEVEL.get(actual, -1) <= ACTION_LEVEL.get(max_expected, -1)
    return ok, {"actual": actual, "max_expected": max_expected}


def _execute_case(
    case: Dict[str, Any],
    ranker: SourceRankerModule,
    router: PathRouter,
    adjudicator: PathAdjudicator,
    scorer: OpportunityScorer,
) -> CaseCheck:
    scenario = {**_default_scenario(case), **(case.get("scenario") or {})}
    expect = case["expect"]

    chain_ok = True
    chain_errors: List[str] = []

    try:
        rank_out = ranker.run({"source_url": case["input"]["source_url"], "headline": case["input"]["headline"]})
        source_rank = str((rank_out.data or {}).get("rank", "C"))
        if rank_out.status.value != "success":
            chain_ok = False
            chain_errors.append("source_ranker_failed")

        if scenario.get("transmission_paths"):
            transmission_paths = scenario["transmission_paths"]
            router_ok = True
        else:
            router_out = router.run(
                {
                    "event_id": case["case_id"],
                    "schema_version": "v1.1",
                    "headline": case["input"].get("headline", ""),
                    "summary": case["input"].get("raw_text", ""),
                    "path_blueprints": scenario.get("path_blueprints", []),
                }
            )
            router_ok = router_out.status.value == "success"
            transmission_paths = (router_out.data or {}).get("transmission_paths", [])

        adj_out = adjudicator.run({"transmission_paths": transmission_paths})
        if not router_ok or adj_out.status.value != "success":
            chain_ok = False
            chain_errors.append("path_layer_failed")

        gate_payload = {
            "trace_id": case["case_id"],
            "schema_version": "v1.0",
            "timestamp": case["input"].get("timestamp", _utc_now()),
            "sectors": scenario.get("sectors", []),
            "stock_candidates": scenario.get("stock_candidates", []),
            "mixed_regime": bool((adj_out.data or {}).get("mixed_regime", False)),
            "asset_validation": scenario.get("asset_validation", {"score": 60}),
            "risk_blocked": bool(scenario.get("risk_blocked", False)),
        }

        opportunity_out = scorer.build_opportunity_update(gate_payload)
        compiled = _build_compiled_output(
            case=case,
            source_rank=source_rank,
            dominant_path=(adj_out.data or {}).get("dominant_path", {}),
            mixed_regime=bool((adj_out.data or {}).get("mixed_regime", False)),
            opportunity_out=opportunity_out,
        )

        fields_ok, missing_fields = _check_fields(compiled, expect)
        signal_ok, signal_meta = _check_signal(compiled, expect)
        path_ok, actual_path = _check_path(compiled, expect)
        risk_ok, risk_meta = _check_risk(compiled, expect)
        mixed_regime_ok, mixed_regime_reason = _check_mixed_regime(compiled, expect)

        final_ok = all([chain_ok, fields_ok, path_ok, signal_ok, risk_ok, mixed_regime_ok])
        details = {
            "compiled_output": compiled,
            "chain_errors": chain_errors,
            "missing_fields": missing_fields,
            "signal_meta": signal_meta,
            "actual_path_type": actual_path,
            "risk_meta": risk_meta,
            "mixed_regime_check": {"ok": mixed_regime_ok, "reason": mixed_regime_reason},
            "source_file": case.get("_path"),
        }

        return CaseCheck(
            case_id=case["case_id"],
            chain_ok=chain_ok,
            fields_ok=fields_ok,
            path_ok=path_ok,
            signal_ok=signal_ok,
            risk_ok=risk_ok,
            mixed_regime_ok=mixed_regime_ok,
            final_ok=final_ok,
            details=details,
        )
    except Exception as exc:  # noqa: BLE001
        return CaseCheck(
            case_id=case["case_id"],
            chain_ok=False,
            fields_ok=False,
            path_ok=False,
            signal_ok=False,
            risk_ok=False,
            mixed_regime_ok=False,
            final_ok=False,
            details={"exception": f"{type(exc).__name__}: {exc}", "source_file": case.get("_path")},
        )


def _ratio(num: int, den: int) -> float:
    if den <= 0:
        return 0.0
    return num / den


def _pass_text(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def _build_markdown(results: List[CaseCheck], summary: Dict[str, Any]) -> str:
    lines = [
        "# Golden E2E Acceptance Report",
        "",
        f"Generated at: {summary['generated_at']}",
        "",
        "## Layer 0",
        f"- healthcheck: {_pass_text(summary['layer0']['passed'])}",
        f"- returncode: {summary['layer0']['returncode']}",
        "",
        "## Case Matrix",
        "",
        "| CASE_ID | CHAIN_OK | FIELDS_OK | PATH_OK | SIGNAL_OK | RISK_OK | MIXED_OK | FINAL |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for item in results:
        lines.append(
            f"| {item.case_id} | {_pass_text(item.chain_ok)} | {_pass_text(item.fields_ok)} | {_pass_text(item.path_ok)} | {_pass_text(item.signal_ok)} | {_pass_text(item.risk_ok)} | {_pass_text(item.mixed_regime_ok)} | {_pass_text(item.final_ok)} |"
        )

    m = summary["metrics"]
    lines += [
        "",
        "## Metrics",
        f"- chain_completeness_rate: {m['chain_completeness_rate']:.4f}",
        f"- required_fields_missing_rate: {m['required_fields_missing_rate']:.4f}",
        f"- direction_consistency_rate: {m['direction_consistency_rate']:.4f}",
        f"- path_consistency_rate: {m['path_consistency_rate']:.4f}",
        f"- high_risk_false_release_rate: {m['high_risk_false_release_rate']:.4f}",
        f"- threshold_pass: {_pass_text(summary['threshold_pass'])}",
    ]
    return "\n".join(lines) + "\n"


def run() -> int:
    parser = argparse.ArgumentParser(description="Run golden E2E acceptance suite")
    parser.add_argument("--skip-healthcheck", action="store_true", help="skip Layer0 health check")
    args = parser.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    cases = _load_cases()
    thresholds = _load_thresholds(THRESHOLDS_PATH)

    layer0 = {
        "passed": True,
        "returncode": 0,
        "command": "skipped",
        "output_preview": "",
        "checked_at": _utc_now(),
    }
    if not args.skip_healthcheck:
        layer0 = _run_layer0_healthcheck()

    ranker = SourceRankerModule()
    router = PathRouter()
    adjudicator = PathAdjudicator()
    scorer = OpportunityScorer()

    results = [_execute_case(case, ranker, router, adjudicator, scorer) for case in cases]

    total = len(results)
    chain_ok_count = sum(1 for x in results if x.chain_ok)
    fields_ok_count = sum(1 for x in results if x.fields_ok)
    signal_ok_count = sum(1 for x in results if x.signal_ok)
    path_ok_count = sum(1 for x in results if x.path_ok)

    conservative_cases = 0
    false_releases = 0
    by_case = {c["case_id"]: c for c in cases}
    for item in results:
        case = by_case.get(item.case_id, {})
        expected = (case.get("expect") or {}).get("max_final_action", "EXECUTE")
        actual = (item.details.get("risk_meta") or {}).get("actual", "BLOCK")
        if expected != "EXECUTE":
            conservative_cases += 1
            if ACTION_LEVEL.get(actual, -1) > ACTION_LEVEL.get(expected, -1):
                false_releases += 1

    metrics = {
        "chain_completeness_rate": _ratio(chain_ok_count, total),
        "required_fields_missing_rate": _ratio(total - fields_ok_count, total),
        "direction_consistency_rate": _ratio(signal_ok_count, total),
        "path_consistency_rate": _ratio(path_ok_count, total),
        "high_risk_false_release_rate": _ratio(false_releases, conservative_cases),
    }

    threshold_pass = (
        layer0["passed"]
        and metrics["chain_completeness_rate"] >= thresholds["chain_completeness_min"]
        and metrics["required_fields_missing_rate"] <= thresholds["required_fields_missing_rate_max"]
        and metrics["direction_consistency_rate"] >= thresholds["direction_consistency_min"]
        and metrics["path_consistency_rate"] >= thresholds["path_consistency_min"]
        and metrics["high_risk_false_release_rate"] <= thresholds["high_risk_false_release_max"]
    )

    summary = {
        "generated_at": _utc_now(),
        "total_cases": total,
        "passed_cases": sum(1 for x in results if x.final_ok),
        "failed_cases": sum(1 for x in results if not x.final_ok),
        "layer0": layer0,
        "thresholds": thresholds,
        "metrics": metrics,
        "threshold_pass": threshold_pass,
    }

    report = {
        "summary": summary,
        "case_results": [
            {
                "case_id": x.case_id,
                "chain_ok": x.chain_ok,
                "fields_ok": x.fields_ok,
                "path_ok": x.path_ok,
                "signal_ok": x.signal_ok,
                "risk_ok": x.risk_ok,
                "mixed_regime_ok": x.mixed_regime_ok,
                "final": x.final_ok,
                "details": x.details,
            }
            for x in results
        ],
    }

    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_MD.write_text(_build_markdown(results, summary), encoding="utf-8")

    header = f"{'CASE_ID':30} {'CHAIN_OK':9} {'FIELDS_OK':9} {'PATH_OK':7} {'SIGNAL_OK':9} {'RISK_OK':7} {'MIXED_OK':8} {'FINAL':6}"
    print(header)
    for item in results:
        print(
            f"{item.case_id:30} {_pass_text(item.chain_ok):9} {_pass_text(item.fields_ok):9} {_pass_text(item.path_ok):7} {_pass_text(item.signal_ok):9} {_pass_text(item.risk_ok):7} {_pass_text(item.mixed_regime_ok):8} {_pass_text(item.final_ok):6}"
        )

    print("\nSaved:")
    print(f"- {REPORT_JSON}")
    print(f"- {REPORT_MD}")
    print(f"Threshold pass: {_pass_text(threshold_pass)}")

    return 0 if threshold_pass else 1


if __name__ == "__main__":
    raise SystemExit(run())
