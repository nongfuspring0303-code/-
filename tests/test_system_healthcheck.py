import sys
from types import SimpleNamespace
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import system_healthcheck


def test_phase3_evidence_replay_only_warns_in_dev(monkeypatch):
    class _FakeLedger:
        def read_summary(self):
            return {
                "total_runs": 3,
                "live_run_count": 0,
                "replay_run_count": 3,
                "real_flow_evidence": False,
                "pass_rate": 1.0,
            }

    monkeypatch.setattr(system_healthcheck, "Phase3EvidenceLedger", lambda: _FakeLedger())
    out = system_healthcheck.check_phase3_evidence_ledger(mode="dev")
    assert out.status == "GREEN"
    assert out.warnings


def test_phase3_evidence_replay_only_fails_in_prod(monkeypatch):
    class _FakeLedger:
        def read_summary(self):
            return {
                "total_runs": 3,
                "live_run_count": 0,
                "replay_run_count": 3,
                "real_flow_evidence": False,
                "pass_rate": 1.0,
            }

    monkeypatch.setattr(system_healthcheck, "Phase3EvidenceLedger", lambda: _FakeLedger())
    out = system_healthcheck.check_phase3_evidence_ledger(mode="prod")
    assert out.status == "RED"
    assert out.errors


def test_theme_gate_healthcheck_passes(monkeypatch):
    captured = {}
    fake_codebook = {
        "codes": {
            "CONFIG_MISSING": {
                "status": "failed",
                "error_code": "CONFIG_MISSING",
                "fallback_reason": "CONFIG_MISSING",
                "degraded_mode": True,
                "safe_to_consume": False,
                "retryable": False,
                "missing_dependencies": ["config"],
            },
            "CONFIG_INVALID": {
                "status": "failed",
                "error_code": "CONFIG_INVALID",
                "fallback_reason": "CONFIG_INVALID",
                "degraded_mode": True,
                "safe_to_consume": False,
                "retryable": False,
                "missing_dependencies": ["config"],
            },
            "THEME_MAPPING_FAILED": {
                "status": "failed",
                "error_code": "THEME_MAPPING_FAILED",
                "fallback_reason": "THEME_MAPPING_FAILED",
                "degraded_mode": True,
                "safe_to_consume": False,
                "retryable": False,
                "missing_dependencies": ["theme_mapping"],
            },
            "BASKET_EMPTY": {
                "status": "degraded",
                "error_code": "BASKET_EMPTY",
                "fallback_reason": "BASKET_EMPTY",
                "degraded_mode": True,
                "safe_to_consume": False,
                "retryable": True,
                "missing_dependencies": ["basket"],
            },
            "MARKET_DATA_MISSING": {
                "status": "degraded",
                "error_code": "MARKET_DATA_MISSING",
                "fallback_reason": "MARKET_DATA_MISSING",
                "degraded_mode": True,
                "safe_to_consume": False,
                "retryable": True,
                "missing_dependencies": ["market_data"],
            },
            "VALIDATION_SKIPPED": {
                "status": "failed",
                "error_code": "VALIDATION_SKIPPED",
                "fallback_reason": "VALIDATION_SKIPPED",
                "degraded_mode": True,
                "safe_to_consume": False,
                "retryable": False,
                "missing_dependencies": ["validation"],
            },
            "STATE_ENGINE_INSUFFICIENT_DATA": {
                "status": "degraded",
                "error_code": "STATE_ENGINE_INSUFFICIENT_DATA",
                "fallback_reason": "STATE_ENGINE_INSUFFICIENT_DATA",
                "degraded_mode": True,
                "safe_to_consume": False,
                "retryable": True,
                "current_state": "FIRST_IMPULSE",
                "missing_dependencies": ["state_history"],
            },
            "DOWNSTREAM_OUTPUT_DEGRADED": {
                "status": "degraded",
                "error_code": "DOWNSTREAM_OUTPUT_DEGRADED",
                "fallback_reason": "DOWNSTREAM_OUTPUT_DEGRADED",
                "degraded_mode": True,
                "safe_to_consume": False,
                "retryable": True,
                "missing_dependencies": ["downstream_consumer"],
            },
        }
    }

    monkeypatch.setattr(system_healthcheck, "load_theme_error_codebook", lambda _path=None: fake_codebook)

    real_apply = system_healthcheck.apply_theme_gate_constraints

    def _capture_apply(payload):
        gate = real_apply(payload)
        if payload.get("conflict_flag") and str(payload.get("trade_grade")) == "A":
            captured["gate"] = gate
        return gate

    monkeypatch.setattr(system_healthcheck, "apply_theme_gate_constraints", _capture_apply)

    out = system_healthcheck.check_theme_gate()

    assert out.status == "GREEN"
    assert not out.errors
    assert captured["gate"]["trade_grade"] == "C"
    assert captured["gate"]["final_action"] == "BLOCK"
    assert captured["gate"]["prohibit_execute"] is True
    assert captured["gate"]["gate_reason"] == "CONFLICT_FLAG_BLOCKED_A_GRADE"


def test_theme_gate_healthcheck_rejects_missing_fallback_reason(monkeypatch):
    fake_codebook = {
        "codes": {
            "CONFIG_MISSING": {
                "status": "failed",
                "error_code": "CONFIG_MISSING",
                "degraded_mode": True,
                "safe_to_consume": False,
                "retryable": False,
                "missing_dependencies": ["config"],
            },
        }
    }

    monkeypatch.setattr(system_healthcheck, "load_theme_error_codebook", lambda _path=None: fake_codebook)

    out = system_healthcheck.check_theme_gate()

    assert out.status == "RED"
    assert out.errors


def test_stage_status_keeps_canary_red_in_dev():
    checks = [
        system_healthcheck.CheckResult(name="CANARY_SOURCE_HEALTH", status="RED", summary="canary red"),
        system_healthcheck.CheckResult(name="CHAIN", status="GREEN", summary="chain ok"),
    ]

    overall = system_healthcheck._stage_status_for_overall(checks, mode="dev")

    assert overall == "RED"


def test_dev_mode_keeps_latency_only_canary_red_blocking():
    checks = [
        system_healthcheck.CheckResult(
            name="CANARY_SOURCE_HEALTH",
            status="RED",
            summary="canary red",
            errors=["p95_latency_ms_1h=4642.93 > 3000.0"],
        ),
        system_healthcheck.CheckResult(name="CHAIN", status="GREEN", summary="chain ok"),
    ]

    overall = system_healthcheck._stage_status_for_overall(checks, mode="dev")

    assert overall == "RED"


def test_dev_mode_keeps_non_latency_canary_red_blocking():
    checks = [
        system_healthcheck.CheckResult(
            name="CANARY_SOURCE_HEALTH",
            status="RED",
            summary="canary red",
            errors=["success_rate_1h=0.82 < 0.95"],
        ),
        system_healthcheck.CheckResult(name="CHAIN", status="GREEN", summary="chain ok"),
    ]

    overall = system_healthcheck._stage_status_for_overall(checks, mode="dev")

    assert overall == "RED"


def test_canary_refresh_skipped_in_ci_dev_mode(monkeypatch):
    called = {"collect_once": 0}

    class _FakeCanary:
        def collect_once(self):
            called["collect_once"] += 1

        def read_summary(self):
            return {
                "windows": {"60": {"total_attempts": 0, "live_sample_count": 0}},
                "recent_30m": {"new_item_count": 0},
            }

        def assess(self, summary=None, mode="dev"):
            return SimpleNamespace(
                status="YELLOW",
                summary="no live samples",
                warnings=[],
                errors=[],
                evidence=[],
                windows={},
            )

    monkeypatch.setenv("CI", "true")
    monkeypatch.delenv("HEALTHCHECK_CANARY_FORCE_REFRESH", raising=False)
    monkeypatch.setattr(system_healthcheck, "CanarySourceHealth", _FakeCanary)

    out = system_healthcheck.check_canary_source_health(mode="dev")

    assert called["collect_once"] == 0
    assert out.status == "YELLOW"
    assert any("skipped in CI dev mode" in w for w in out.warnings)


def test_canary_refresh_can_be_forced_in_ci_dev_mode(monkeypatch):
    called = {"collect_once": 0}

    class _FakeCanary:
        def collect_once(self):
            called["collect_once"] += 1

        def read_summary(self):
            return {
                "windows": {"60": {"total_attempts": 0, "live_sample_count": 0}},
                "recent_30m": {"new_item_count": 0},
            }

        def assess(self, summary=None, mode="dev"):
            return SimpleNamespace(
                status="YELLOW",
                summary="no live samples",
                warnings=[],
                errors=[],
                evidence=[],
                windows={},
            )

    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("HEALTHCHECK_CANARY_FORCE_REFRESH", "1")
    monkeypatch.setattr(system_healthcheck, "CanarySourceHealth", _FakeCanary)

    out = system_healthcheck.check_canary_source_health(mode="dev")

    assert called["collect_once"] == 1
    assert out.status == "YELLOW"


def test_phase3_pressure_gate_sample_passes():
    code, output = system_healthcheck.run_phase3_pressure_gate()

    assert code == 0
    assert '"passed": true' in output


def test_run_command_passes_timeout_to_subprocess(monkeypatch):
    captured = {}

    class _Proc:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def _fake_run(*args, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        return _Proc()

    monkeypatch.setattr(system_healthcheck.subprocess, "run", _fake_run)
    code, output = system_healthcheck.run_command(["echo", "ok"], system_healthcheck.ROOT)

    assert code == 0
    assert output == "ok"
    assert captured["timeout"] == system_healthcheck.DEFAULT_COMMAND_TIMEOUT_SEC


def test_run_command_handles_timeout(monkeypatch):
    def _raise_timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=["git", "status"], timeout=60)

    monkeypatch.setattr(system_healthcheck.subprocess, "run", _raise_timeout)
    code, output = system_healthcheck.run_command(["git", "status"], system_healthcheck.ROOT)

    assert code == 124
    assert "timed out" in output
