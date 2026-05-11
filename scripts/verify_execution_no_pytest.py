#!/usr/bin/env python3
"""
Fallback verifier when pytest is unavailable.
Runs core assertions with plain Python.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from execution_modules import ExitManager, LiquidityChecker, PositionSizer, RiskGatekeeper
from workflow_runner import WorkflowRunner


ROOT = Path(__file__).resolve().parent.parent

SAFE_PATH_PATTERNS = [
    ".env.example",
    "canvas/*.html",
    "canvas/*.js",
    "canvas/runtime-config.js",
    "docs/ENVIRONMENT.md",
    "docs/STARTUP_SOP.md",
    "docs/semantic-baseline-contract-v1.md",
    "scripts/ai_semantic_analyzer.py",
    "scripts/project_gap_monitor.py",
    "scripts/verify_execution_no_pytest.py",
    "tests/fixtures/**",
    "tests/test_ai_semantic_json_parser.py",
    "tests/test_event_bus.py",
    "tests/test_project_gap_monitor.py",
    "tests/test_project_trace_api.py",
    "tests/test_verify_execution_no_pytest.py",
]

SAFE_LINE_MARKERS = (
    "***",
    "Bearer test",
    "RAW_",
    "REAL_",
    "dummy",
    "example",
    "fixture",
    "local-dev-token",
    "placeholder",
    "redacted",
    "密钥",
    "令牌",
    "test_key",
)

SENSITIVE_PATTERNS = {
    "secret_literal": re.compile(r"\b(?:sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    "raw_path": re.compile(r"/Users/|/private/tmp/"),
    "traceback": re.compile(r"Traceback \(most recent call last\):"),
    "secret_assignment": re.compile(
        r"(?i)\b(?:OPENAI_API_KEY|GLM_API_KEY|OPENCLAW_GLM_API_KEY|EDT_API_TOKEN|EDT_WS_TOKEN|JIN10_MCP_TOKEN|API_KEY|SECRET|PASSWORD|TOKEN|AUTH_TOKEN)\b\s*[:=]\s*(?:['\"]([^'\"]+)['\"]|([^#\s]+))"
    ),
}


@dataclass
class LeakFinding:
    path: str
    line: int
    kind: str
    severity: str
    excerpt: str


def _is_allowlisted_path(rel_path: str) -> bool:
    return any(Path(rel_path).match(pattern) for pattern in SAFE_PATH_PATTERNS)


def _git_tracked_files(root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
        text=False,
    )
    entries = [entry for entry in completed.stdout.decode("utf-8", errors="replace").split("\0") if entry]
    return entries


def _has_safe_marker(text: str) -> bool:
    return any(marker in text for marker in SAFE_LINE_MARKERS)


def _looks_secretish(value: str) -> bool:
    normalized = value.strip().strip("'\"")
    if not normalized:
        return False
    if _has_safe_marker(normalized):
        return False
    if normalized.startswith(("sk-", "ghp_", "github_pat_")):
        return True
    if re.fullmatch(r"[A-Za-z0-9_./+=-]{20,}", normalized):
        return True
    return False


def _scan_text_for_leaks(rel_path: str, text: str) -> list[LeakFinding]:
    findings: list[LeakFinding] = []
    allowlisted = _is_allowlisted_path(rel_path)
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        for kind, pattern in SENSITIVE_PATTERNS.items():
            if not pattern.search(line):
                continue
            severity = "WARN"
            if kind == "secret_assignment":
                match = pattern.search(line)
                value = ""
                if match:
                    value = next((group for group in match.groups() if group), "")
                if _looks_secretish(value) and not allowlisted:
                    severity = "FAIL"
            elif not allowlisted and not _has_safe_marker(line):
                severity = "FAIL"
            findings.append(
                LeakFinding(
                    path=rel_path,
                    line=line_no,
                    kind=kind,
                    severity=severity,
                    excerpt=line.strip(),
                )
            )
    return findings


def audit_repo_sensitive_leaks(root: Path = ROOT, tracked_files: list[str] | None = None) -> dict[str, object]:
    paths = tracked_files if tracked_files is not None else _git_tracked_files(root)
    warnings: list[LeakFinding] = []
    failures: list[LeakFinding] = []
    for rel_path in paths:
        path = root / rel_path
        if not path.exists() or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for finding in _scan_text_for_leaks(rel_path, text):
            if finding.severity == "FAIL":
                failures.append(finding)
            else:
                warnings.append(finding)

    status = "PASS"
    if failures:
        status = "FAIL"
    elif warnings:
        status = "WARN"

    return {
        "status": status,
        "warnings": [finding.__dict__ for finding in warnings],
        "failures": [finding.__dict__ for finding in failures],
    }


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    liq = LiquidityChecker().run({"vix": 35, "ted": 120, "correlation": 0.85, "spread_pct": 0.02})
    _assert(liq.data["liquidity_state"] == "RED", "LiquidityChecker RED case failed")

    gate = RiskGatekeeper().run(
        {
            "event_state": "Dead",
            "fatigue_index": 20,
            "liquidity_state": "GREEN",
            "correlation": 0.5,
            "score": 80,
            "severity": "E3",
            "A1": 70,
        }
    )
    _assert(gate.data["final_action"] == "FORCE_CLOSE", "RiskGatekeeper dead case failed")

    size = PositionSizer().run(
        {
            "score": 72,
            "liquidity_state": "GREEN",
            "risk_gate_multiplier": 1.0,
            "account_equity": 100000,
        }
    )
    _assert(size.data["score_tier"] == "G2", "PositionSizer tier case failed")
    _assert(size.data["final_notional"] == 50000.0, "PositionSizer notional case failed")

    ex = ExitManager().run({"entry_price": 100.0, "risk_per_share": 2.0, "direction": "long"})
    _assert(len(ex.data["take_profit_levels"]) == 3, "ExitManager TP count failed")
    _assert(ex.data["hard_stop"] == 96.0, "ExitManager hard stop failed")

    out = WorkflowRunner().run(
        {
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
        }
    )
    _assert(out["final"]["action"] in ("EXECUTE", "WATCH", "BLOCK", "FORCE_CLOSE"), "Workflow output invalid")
    print("OK: execution-layer fallback verification passed")

    audit = audit_repo_sensitive_leaks(ROOT)
    if audit["status"] == "FAIL":
        findings = audit["failures"]
        sample = findings[0] if findings else {}
        raise AssertionError(
            f"Repository sensitive-leak audit failed: {len(findings)} real leak(s) detected"
            + (f" (example: {sample.get('path')}:{sample.get('line')} {sample.get('kind')})" if sample else "")
        )
    if audit["status"] == "WARN":
        print(f"WARN: repository leak audit matched {len(audit['warnings'])} safe example(s)")
    else:
        print("PASS: repository leak audit found no sensitive leak matches")


if __name__ == "__main__":
    main()
