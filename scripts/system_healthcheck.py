#!/usr/bin/env python3
"""
Project-wide health check entrypoint.

Strong mode lifecycle:
1. health-system self-check
2. health-system self-heal
3. health-system re-check
4. project-wide health check
"""

from __future__ import annotations

import json
import argparse
import ast
import os
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
CONFIG_PATH = ROOT / "configs" / "edt-modules-config.yaml"
REGISTRY_PATH = ROOT / "module-registry.yaml"
DOC_PATH = ROOT / "docs" / "system_health_standard.md"
MANUAL_PATH = ROOT / "docs" / "system_health_manual.md"
LOGS_DIR = ROOT / "logs"
REPORT_PATH = LOGS_DIR / "system_health_report.json"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

try:
    import yaml
except Exception as exc:  # noqa: BLE001
    print(f"FATAL: missing yaml dependency: {exc}")
    raise SystemExit(2)

from phase3_evidence_ledger import Phase3EvidenceLedger
from data_adapter import DataAdapter
from canary_source_health import CanarySourceHealth
from theme_gate_policy import (
    REQUIRED_CONTRACT_FIELDS,
    apply_theme_gate_constraints,
    load_theme_error_codebook,
    validate_theme_contract,
    validate_theme_error_codebook,
)


STATUS_ORDER = {"GREEN": 0, "YELLOW": 1, "RED": 2}

# Dev mode policy (follow-up #81):
# - CANARY_SOURCE_HEALTH=YELLOW is treated as non-blocking (normalized to GREEN)
# - CANARY_SOURCE_HEALTH=RED always remains blocking (never downgraded)
DEV_CANARY_NON_BLOCKING_STATUS = "YELLOW"


@dataclass
class CheckResult:
    name: str
    status: str
    summary: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)


@dataclass
class StageResult:
    name: str
    status: str
    summary: str
    checks: list[CheckResult] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


def worst_status(values: list[str]) -> str:
    return max(values, key=lambda item: STATUS_ORDER[item]) if values else "GREEN"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def compile_source(path: Path) -> None:
    ast.parse(read_text(path), filename=str(path))


def run_command(args: list[str], cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace")
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, output.strip()


def build_phase3_pressure_sample() -> list[dict[str, Any]]:
    ts = "2026-04-09T01:02:03Z"
    return [
        {
            "headline": "Fed signals policy shift",
            "source_url": "https://example.com/news-1",
            "raw_text": "policy shift",
            "source_type": "rss",
            "timestamp": ts,
        },
        {
            "headline": "AI spending remains strong",
            "source_url": "https://example.com/news-2",
            "raw_text": "ai spending",
            "source_type": "official",
            "timestamp": ts,
        },
    ]


def run_phase3_pressure_gate(min_board_coverage: float = 0.5, max_p99_ms: float = 5000.0, min_throughput: float = 0.1) -> tuple[int, str]:
    gate_path = ROOT / "scripts" / "run_phase3_pressure_gate.py"
    if not gate_path.exists():
        return 1, "run_phase3_pressure_gate.py is missing"

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
        json.dump(build_phase3_pressure_sample(), handle, ensure_ascii=False)
        sample_path = Path(handle.name)

    try:
        args = [
            sys.executable,
            str(gate_path),
            "--input-json",
            str(sample_path),
            "--min-board-coverage",
            str(min_board_coverage),
            "--max-p99-ms",
            str(max_p99_ms),
            "--min-throughput",
            str(min_throughput),
        ]
        return run_command(args, ROOT)
    finally:
        try:
            sample_path.unlink(missing_ok=True)
        except Exception:
            pass


def safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        encoded = text.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8")
        print(encoded)


def render_checks(title: str, checks: list[CheckResult]) -> None:
    safe_print(title)
    for item in checks:
        safe_print(f"[{item.status}] {item.name}: {item.summary}")
        for error in item.errors:
            safe_print(f"  ERROR: {error}")
        for warning in item.warnings:
            safe_print(f"  WARN: {warning}")


def check_env() -> CheckResult:
    result = CheckResult(name="ENV", status="GREEN", summary="Runtime environment smoke checks are healthy.")
    py_version = sys.version.split()[0]
    result.evidence.append(f"python={py_version}")

    smoke_checks = [
        [sys.executable, "-c", "import pytest, yaml, requests"],
        [sys.executable, "-m", "pytest", "--version"],
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "tests/test_config_center.py"],
    ]

    for cmd in smoke_checks:
        code, output = run_command(cmd, ROOT)
        result.commands.append(" ".join(cmd))
        if code != 0:
            result.status = "RED"
            result.summary = "Runtime environment smoke checks are not healthy."
            result.errors.append(f"`{' '.join(cmd)}` failed in current environment.")
            if output:
                result.evidence.append(output.splitlines()[0])
            break

    return result


def check_config() -> CheckResult:
    result = CheckResult(name="CONFIG", status="GREEN", summary="Configuration loads and is consumed by modules.")

    try:
        cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        result.status = "RED"
        result.summary = "Config file is not readable as UTF-8 YAML."
        result.errors.append(str(exc))
        return result

    modules = cfg.get("modules", {})
    if not modules:
        result.status = "RED"
        result.summary = "Top-level modules config is empty."
        result.errors.append("`configs/edt-modules-config.yaml` produced empty modules config.")
        return result

    result.evidence.append(f"module_count={len(modules)}")

    try:
        from intel_modules import SourceRankerModule
    except Exception as exc:  # noqa: BLE001
        result.status = "RED"
        result.summary = "Unable to import config-driven modules for health validation."
        result.errors.append(str(exc))
        return result

    ranker = SourceRankerModule()
    if not ranker.config:
        result.status = "RED"
        result.summary = "Config-driven modules are silently running with empty config."
        result.errors.append("`SourceRankerModule().config` is empty.")
        return result

    sample = ranker.run({"source_url": "https://www.reuters.com/markets/us/example"})
    rank = sample.data.get("rank")
    result.evidence.append(f"reuters_rank={rank}")
    if rank != "B":
        result.status = "RED"
        result.summary = "SourceRanker is not consuming ranking config correctly."
        result.errors.append("Expected Reuters to resolve to rank `B`.")

    return result


def check_theme_gate() -> CheckResult:
    result = CheckResult(name="THEME_GATE", status="GREEN", summary="Theme gate codebook and intercept rules are healthy.")
    codebook_path = ROOT / "configs" / "theme_error_codebook.yaml"
    if not codebook_path.exists():
        result.status = "RED"
        result.summary = "Theme error codebook is missing."
        result.errors.append(str(codebook_path))
        return result

    try:
        codebook = load_theme_error_codebook(codebook_path)
    except Exception as exc:  # noqa: BLE001
        result.status = "RED"
        result.summary = "Theme error codebook is unreadable."
        result.errors.append(str(exc))
        return result

    codebook_errors = validate_theme_error_codebook(codebook)
    if codebook_errors:
        result.status = "RED"
        result.summary = "Theme error codebook is incomplete."
        result.errors.extend(codebook_errors)
        return result

    result.evidence.append(f"required_codes={len(codebook.get('codes', {}))}")
    result.evidence.append(f"required_contract_fields={','.join(REQUIRED_CONTRACT_FIELDS)}")

    unsafe_sample = {
        "contract_name": "theme_catalyst_engine",
        "contract_version": "v1.0",
        "producer_module": "theme_engine",
        "safe_to_consume": False,
        "error_code": "CONFIG_MISSING",
        "fallback_reason": "CONFIG_MISSING",
        "degraded_mode": True,
        "trade_grade": "B",
        "conflict_flag": False,
    }
    unsafe_gate = apply_theme_gate_constraints(unsafe_sample)
    unsafe_errors = validate_theme_contract(unsafe_gate)
    if unsafe_errors:
        result.status = "RED"
        result.summary = "Unsafe theme output is not downgraded correctly."
        result.errors.extend(unsafe_errors)
        return result

    conflict_sample = {
        "contract_name": "theme_catalyst_engine",
        "contract_version": "v1.0",
        "producer_module": "theme_engine",
        "safe_to_consume": True,
        "error_code": "THEME_MAPPING_FAILED",
        "fallback_reason": "THEME_MAPPING_FAILED",
        "degraded_mode": True,
        "trade_grade": "A",
        "conflict_flag": True,
    }
    conflict_gate = apply_theme_gate_constraints(conflict_sample)
    conflict_errors = validate_theme_contract(conflict_gate)
    if conflict_errors or str(conflict_gate.get("trade_grade", "")).upper() == "A":
        result.status = "RED"
        result.summary = "Conflict flag is not blocking A-grade output correctly."
        result.errors.extend(conflict_errors or ["conflict_flag still allows A-grade through"])
        return result

    result.evidence.append(f"unsafe_final_action={unsafe_gate.get('final_action')}")
    result.evidence.append(f"conflict_trade_grade={conflict_gate.get('trade_grade')}")
    result.evidence.append(f"conflict_final_action={conflict_gate.get('final_action')}")
    return result


def check_chain() -> CheckResult:
    result = CheckResult(name="CHAIN", status="GREEN", summary="Main chain points at current implementations.")

    full_workflow_text = read_text(ROOT / "scripts" / "full_workflow_runner.py")
    workflow_text = read_text(ROOT / "scripts" / "workflow_runner.py")

    if "from analysis_modules import AnalysisPipeline" in full_workflow_text:
        result.status = "RED"
        result.summary = "Full chain still points at legacy analysis aggregation."
        result.errors.append("`full_workflow_runner.py` imports `analysis_modules.AnalysisPipeline`.")

    if "from edt_module_base import ModuleStatus, SignalScorer" in workflow_text:
        result.status = "RED"
        result.summary = "Execution chain still uses demo SignalScorer implementation."
        result.errors.append("`workflow_runner.py` imports `SignalScorer` from `edt_module_base`.")

    if '"source_rank"' not in full_workflow_text and '"needs_escalation"' not in full_workflow_text:
        if result.status != "RED":
            result.status = "YELLOW"
            result.summary = "Source trust constraints are not visible in full-chain inputs."
        result.warnings.append("Full-chain assembly does not appear to propagate `source_rank` or `needs_escalation`.")

    return result


def check_contract() -> CheckResult:
    result = CheckResult(name="CONTRACT", status="GREEN", summary="Registry, schema, and test references are structurally consistent.")

    registry = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    entries = registry.get("registry", [])
    missing_files: list[str] = []
    placeholder_refs: list[str] = []
    empty_tests: list[str] = []

    for entry in entries:
        for field_name in ("input_schema", "output_schema"):
            ref = entry.get(field_name)
            if not ref:
                continue
            schema_path = ROOT / "schemas" / ref
            if not schema_path.exists():
                missing_files.append(str(schema_path))
                continue
            content = read_text(schema_path)
            if "placeholder schema" in content or "TODO: define contract" in content:
                placeholder_refs.append(f"{entry['name']} -> {schema_path.name}")

        test_ref = entry.get("test_case")
        if not test_ref:
            continue
        test_path = ROOT / test_ref
        if not test_path.exists():
            missing_files.append(str(test_path))
            continue
        if test_path.suffix == ".yaml":
            payload = yaml.safe_load(test_path.read_text(encoding="utf-8")) or {}
            if payload.get("cases") == []:
                empty_tests.append(test_path.name)

    if missing_files:
        result.status = "RED"
        result.summary = "Registry references missing files."
        result.errors.extend(sorted(set(missing_files)))

    if placeholder_refs:
        result.status = "RED"
        result.summary = "Registry still points at placeholder schemas."
        result.errors.extend(sorted(set(placeholder_refs)))

    if empty_tests and result.status != "RED":
        result.status = "YELLOW"
        result.summary = "Some registry-linked YAML tests are still empty shells."

    if empty_tests:
        result.warnings.extend(sorted(set(empty_tests)))

    result.evidence.append(f"registry_entries={len(entries)}")
    return result


def check_test_runtime() -> CheckResult:
    result = CheckResult(name="TEST", status="GREEN", summary="Core runtime checks pass.")

    commands = [
        [sys.executable, "tests/run_analysis_interface_checks.py"],
        [sys.executable, "scripts/verify_execution_no_pytest.py"],
        [sys.executable, "scripts/full_workflow_runner.py"],
    ]

    for cmd in commands:
        code, output = run_command(cmd, ROOT)
        result.commands.append(" ".join(cmd))
        if code != 0:
            result.status = "RED"
            result.summary = "One or more core runtime checks failed."
            result.errors.append(" ".join(cmd))
            if output:
                result.evidence.append(output.splitlines()[-1])

    return result


def check_pressure_gate() -> CheckResult:
    result = CheckResult(name="PHASE3_PRESSURE_GATE", status="GREEN", summary="Phase-3 pressure gate passes on local replay data.")
    code, output = run_phase3_pressure_gate()
    result.commands.append(
        f"{sys.executable} scripts/run_phase3_pressure_gate.py --input-json <local sample> --min-board-coverage 0.5 --max-p99-ms 5000 --min-throughput 0.1"
    )
    if code != 0:
        result.status = "RED"
        result.summary = "Phase-3 pressure gate failed."
        result.errors.append("run_phase3_pressure_gate.py returned non-zero exit code.")
        if output:
            result.evidence.append(output)
        return result

    result.evidence.append(output)
    return result


def check_phase3_evidence_ledger(mode: str = "dev") -> CheckResult:
    ledger = Phase3EvidenceLedger()
    summary = ledger.read_summary()
    result = CheckResult(
        name="PHASE3_EVIDENCE_LEDGER",
        status="GREEN",
        summary="Phase-3 evidence ledger is present and rolling statistics are available.",
    )
    total_runs = int(summary.get("total_runs", 0) or 0)
    live_run_count = int(summary.get("live_run_count", 0) or 0)
    replay_run_count = int(summary.get("replay_run_count", 0) or 0)

    if total_runs <= 0:
        result.status = "RED"
        result.summary = "Phase-3 evidence ledger has no records yet."
        result.errors.append("No pressure-gate records found in logs/phase3_evidence.jsonl.")
        return result

    result.evidence.extend(
        [
            f"total_runs={total_runs}",
            f"live_run_count={live_run_count}",
            f"replay_run_count={replay_run_count}",
            f"real_flow_evidence={bool(summary.get('real_flow_evidence'))}",
            f"pass_rate={summary.get('pass_rate', 0)}",
        ]
    )
    if not summary.get("real_flow_evidence"):
        if mode == "prod":
            result.status = "RED"
            result.summary = "Production readiness requires live pressure-gate evidence."
            result.errors.append("No live pressure-gate records found; replay-only evidence is insufficient in prod mode.")
        else:
            result.warnings.append("No live pressure-gate records found; current evidence is replay-only.")

    return result


def check_external_data_health(mode: str = "dev") -> CheckResult:
    adapter = DataAdapter()
    payload = adapter.fetch()
    health = adapter.health_report()

    news = payload.get("news", {})
    market = payload.get("market_data", {})
    result = CheckResult(
        name="DATA_HEALTH",
        status="GREEN",
        summary="External data health snapshot recorded.",
    )
    result.evidence.extend(
        [
            f"total_fetches={health.get('total_fetches', 0)}",
            f"live_news_count={health.get('live_news_count', 0)}",
            f"fallback_news_count={health.get('fallback_news_count', 0)}",
            f"market_test_count={health.get('market_test_count', 0)}",
            f"live_news_ratio={health.get('live_news_ratio', 0)}",
            f"news_source_type={news.get('source_type', 'unknown')}",
            f"market_source={market.get('market_data_source', 'unknown')}",
        ]
    )
    if health.get("live_news_count", 0) <= 0:
        if mode == "prod":
            result.status = "RED"
            result.summary = "Production mode requires live external data evidence."
            result.errors.append("No live external news samples recorded.")
        else:
            result.warnings.append("External data health is replay/fallback only in the current environment.")
    return result


def check_canary_source_health(mode: str = "dev") -> CheckResult:
    health = CanarySourceHealth()
    ci_env = str(os.getenv("CI", "")).strip().lower() == "true"
    force_refresh = str(os.getenv("HEALTHCHECK_CANARY_FORCE_REFRESH", "")).strip().lower() in {"1", "true", "yes", "on"}
    skip_refresh = ci_env and mode == "dev" and not force_refresh
    if skip_refresh:
        refresh_error = "canary refresh skipped in CI dev mode; using existing summary snapshot."
    else:
        try:
            health.collect_once()
        except Exception as exc:  # noqa: BLE001
            refresh_error = f"canary refresh failed: {exc}"
        else:
            refresh_error = ""
    summary = health.read_summary()
    assessment = health.assess(summary=summary, mode=mode)
    result = CheckResult(
        name="CANARY_SOURCE_HEALTH",
        status=assessment.status,
        summary=assessment.summary,
        warnings=list(assessment.warnings),
        errors=list(assessment.errors),
        evidence=list(assessment.evidence),
    )
    window_1h = assessment.windows.get("60", {}) or assessment.windows.get("1h", {})
    recent_30m = assessment.windows.get("30", {}) or assessment.windows.get("30m", {})
    result.evidence.extend(
        [
            f"1h_success_rate={window_1h.get('success_rate', 0)}",
            f"1h_p95_latency_ms={window_1h.get('p95_latency_ms', 0)}",
            f"1h_freshness_lag_sec={window_1h.get('freshness_lag_sec', 0)}",
            f"1h_new_item_count={window_1h.get('new_item_count', 0)}",
            f"30m_new_item_count={recent_30m.get('new_item_count', 0)}",
        ]
    )
    if refresh_error:
        result.warnings.append(refresh_error)
    return result


def check_recovery() -> CheckResult:
    result = CheckResult(name="RECOVERY", status="GREEN", summary="Health system self-check and recovery entrypoints are present.")
    required = [
        DOC_PATH,
        MANUAL_PATH,
        ROOT / "scripts" / "system_healthcheck.py",
        ROOT / "scripts" / "system_autofix.py",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        result.status = "RED"
        result.summary = "Recovery tooling is incomplete."
        result.errors.extend(missing)
        return result

    for script_path in (ROOT / "scripts" / "system_healthcheck.py", ROOT / "scripts" / "system_autofix.py"):
        try:
            compile_source(script_path)
            result.evidence.append(f"compiled={script_path.name}")
        except Exception as exc:  # noqa: BLE001
            result.status = "RED"
            result.summary = "Recovery tooling exists but is not syntactically healthy."
            result.errors.append(f"{script_path.name}: {exc}")
    return result


def run_health_system_self_checks() -> list[CheckResult]:
    checks: list[CheckResult] = []

    presence = CheckResult(name="SELF_FILES", status="GREEN", summary="Health-system core files are present.")
    required = [
        ROOT / "scripts" / "system_healthcheck.py",
        ROOT / "scripts" / "system_autofix.py",
        DOC_PATH,
        MANUAL_PATH,
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        presence.status = "RED"
        presence.summary = "Health-system core files are missing."
        presence.errors.extend(missing)
    checks.append(presence)

    compile_check = CheckResult(name="SELF_COMPILE", status="GREEN", summary="Health-system scripts compile.")
    for script_path in (ROOT / "scripts" / "system_healthcheck.py", ROOT / "scripts" / "system_autofix.py"):
        try:
            compile_source(script_path)
            compile_check.evidence.append(f"compiled={script_path.name}")
        except Exception as exc:  # noqa: BLE001
            compile_check.status = "RED"
            compile_check.summary = "One or more health-system scripts fail to compile."
            compile_check.errors.append(f"{script_path.name}: {exc}")
    checks.append(compile_check)

    autofix_dry_run = CheckResult(name="SELF_AUTOFIX_DRYRUN", status="GREEN", summary="Autofix dry-run executes.")
    autofix_path = ROOT / "scripts" / "system_autofix.py"
    if autofix_path.exists():
        code, output = run_command([sys.executable, str(autofix_path)], ROOT)
        autofix_dry_run.commands.append(f"{sys.executable} {autofix_path}")
        if code != 0:
            autofix_dry_run.status = "RED"
            autofix_dry_run.summary = "Autofix dry-run failed."
            autofix_dry_run.errors.append("system_autofix dry-run returned non-zero exit code.")
            if output:
                autofix_dry_run.evidence.append(output.splitlines()[-1])
    else:
        autofix_dry_run.status = "RED"
        autofix_dry_run.summary = "Autofix script is missing."
        autofix_dry_run.errors.append(str(autofix_path))
    checks.append(autofix_dry_run)

    return checks


def maybe_self_heal(enabled: bool) -> StageResult:
    if not enabled:
        return StageResult(name="SELF_HEAL", status="GREEN", summary="Self-heal stage was skipped by configuration.")
    autofix_path = ROOT / "scripts" / "system_autofix.py"
    if not autofix_path.exists():
        return StageResult(
            name="SELF_HEAL",
            status="RED",
            summary="Self-heal could not start because autofix is missing.",
            evidence=[str(autofix_path)],
        )
    code, output = run_command([sys.executable, str(autofix_path), "--apply"], ROOT)
    stage = StageResult(
        name="SELF_HEAL",
        status="GREEN" if code == 0 else "RED",
        summary="Health-system self-heal completed." if code == 0 else "Health-system self-heal failed.",
        evidence=[f"command={sys.executable} {autofix_path} --apply"],
    )
    if output:
        stage.evidence.append(output)
    if code != 0:
        stage.evidence.append(f"exit_code={code}")
    return stage


def build_stage(name: str, summary: str, checks: list[CheckResult]) -> StageResult:
    return StageResult(
        name=name,
        status=worst_status([item.status for item in checks]),
        summary=summary,
        checks=checks,
    )


def run_project_checks(mode: str = "dev", skip_env_check: bool = False) -> list[CheckResult]:
    checks = []
    if not skip_env_check:
        checks.append(check_env())
    checks.extend([
        check_config(),
        check_theme_gate(),
        check_chain(),
        check_contract(),
        check_test_runtime(),
        check_pressure_gate(),
        check_phase3_evidence_ledger(mode=mode),
        check_canary_source_health(mode=mode),
        check_external_data_health(mode=mode),
        check_recovery(),
    ])
    return checks


def _stage_status_for_overall(checks: list[CheckResult], mode: str) -> str:
    statuses: list[str] = []
    for check in checks:
        status = check.status
        if (
            mode == "dev"
            and check.name == "CANARY_SOURCE_HEALTH"
            and status == DEV_CANARY_NON_BLOCKING_STATUS
        ):
            status = "GREEN"
        statuses.append(status)
    return worst_status(statuses)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run health-system self-check and project-wide health checks.")
    parser.add_argument("--self-heal", action="store_true", help="Attempt self-heal between self-check and project checks.")
    parser.add_argument("--self-only", action="store_true", help="Only run health-system self-check stages.")
    parser.add_argument("--mode", choices=["dev", "prod"], default="dev", help="Healthcheck strictness mode.")
    parser.add_argument("--skip-env-check", action="store_true", help="Skip ENV smoke checks.")
    args = parser.parse_args()

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    self_checks_pre = run_health_system_self_checks()
    stage_self_check = build_stage("SELF_CHECK", "Health-system self-check before any repair.", self_checks_pre)

    stage_self_heal = StageResult(name="SELF_HEAL", status="SKIP", summary="Self-heal not requested.")
    if args.self_heal and stage_self_check.status != "GREEN":
        stage_self_heal = maybe_self_heal(True)

    self_checks_post = run_health_system_self_checks()
    stage_self_recheck = build_stage("SELF_RECHECK", "Health-system self-check after self-heal.", self_checks_post)

    stage_project = StageResult(name="PROJECT_CHECK", status="SKIP", summary="Project-wide health check skipped.")
    project_checks: list[CheckResult] = []
    if not args.self_only:
        project_checks = run_project_checks(mode=args.mode, skip_env_check=args.skip_env_check)
        stage_project = build_stage("PROJECT_CHECK", "Project-wide health check after health-system validation.", project_checks)

    stage_statuses = [stage_self_check.status, stage_self_recheck.status]
    if stage_self_heal.status != "SKIP":
        stage_statuses.append(stage_self_heal.status)
    if stage_project.status != "SKIP":
        stage_statuses.append(_stage_status_for_overall(stage_project.checks, args.mode))
    normalized_statuses = [s for s in stage_statuses if s in STATUS_ORDER]
    overall = worst_status(normalized_statuses)

    report = {
        "overall_status": overall,
        "root": str(ROOT),
        "python": sys.version,
        "self_heal": args.self_heal,
        "self_only": args.self_only,
        "mode": args.mode,
        "stages": [
            asdict(stage_self_check),
            asdict(stage_self_heal),
            asdict(stage_self_recheck),
            asdict(stage_project),
        ],
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    safe_print(f"OVERALL: {overall}")
    safe_print(f"[{stage_self_check.status}] {stage_self_check.name}: {stage_self_check.summary}")
    render_checks("SELF-CHECK DETAILS:", stage_self_check.checks)
    safe_print(f"[{stage_self_heal.status}] {stage_self_heal.name}: {stage_self_heal.summary}")
    for evidence in stage_self_heal.evidence:
        safe_print(f"  INFO: {evidence}")
    safe_print(f"[{stage_self_recheck.status}] {stage_self_recheck.name}: {stage_self_recheck.summary}")
    render_checks("SELF-RECHECK DETAILS:", stage_self_recheck.checks)
    if not args.self_only:
        safe_print(f"[{stage_project.status}] {stage_project.name}: {stage_project.summary}")
        render_checks("PROJECT-CHECK DETAILS:", stage_project.checks)
    safe_print(f"REPORT: {REPORT_PATH}")

    return 0 if overall == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
