from __future__ import annotations

import tempfile
from pathlib import Path

import sys
import subprocess

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import verify_execution_no_pytest
from verify_execution_no_pytest import audit_repo_sensitive_leaks


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_audit_marks_safe_examples_as_warn() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        _write(
            root / ".env.example",
            "EDT_API_TOKEN=edt-local-dev-token\n# example: Bearer sk-xxxx\n",
        )
        _write(
            root / "tests" / "test_ai_semantic_json_parser.py",
            'payload = "Traceback (most recent call last):\\n  File \\"/Users/runtime/private/script.py\\", line 3, in <module>\\n"\n',
        )

        report = audit_repo_sensitive_leaks(
            root,
            tracked_files=[".env.example", "tests/test_ai_semantic_json_parser.py"],
        )

        assert report["status"] == "WARN"
        assert report["failures"] == []
        assert report["warnings"]


def test_audit_fails_on_real_leak() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        secret_value = "sk-" + "abc123abc123abc123abc123abc123"
        _write(
            root / "scripts" / "bad.py",
            f"OPENAI_API_KEY = '{secret_value}'\n"
            "trace = 'Traceback (most recent call last):\\n  File \"/Users/me/leak.py\", line 1, in <module>\\n'\n",
        )

        report = audit_repo_sensitive_leaks(root, tracked_files=["scripts/bad.py"])

        assert report["status"] == "FAIL"
        assert report["failures"]
        kinds = {item["kind"] for item in report["failures"]}
        assert "secret_literal" in kinds or "secret_assignment" in kinds
        assert "raw_path" in kinds or "traceback" in kinds


def test_audit_fails_real_secret_even_in_allowlisted_path() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        secret_value = "sk-" + "abc123abc123abc123abc123abc123"
        _write(
            root / ".env.example",
            f"OPENAI_API_KEY='{secret_value}'\n",
        )

        report = audit_repo_sensitive_leaks(root, tracked_files=[".env.example"])

        assert report["status"] == "FAIL"
        assert report["failures"]


def test_audit_fails_when_git_ls_files_times_out(monkeypatch) -> None:
    def _raise_timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=["git", "ls-files", "-z"], timeout=15)

    monkeypatch.setattr(verify_execution_no_pytest.subprocess, "run", _raise_timeout)

    report = audit_repo_sensitive_leaks(Path("."), tracked_files=None)

    assert report["status"] == "FAIL"
    assert report["failures"] == []
    assert report["scan_errors"]


def test_main_uses_safe_final_action_access(monkeypatch) -> None:
    class _Module:
        def run(self, *_args, **_kwargs):
            return type("Out", (), {"data": {"liquidity_state": "RED", "final_action": "FORCE_CLOSE", "score_tier": "G2", "final_notional": 50000.0, "take_profit_levels": [1, 2, 3], "hard_stop": 96.0}, "status": "success"})()

    class _Workflow:
        def run(self, *_args, **_kwargs):
            return {"runtime_safety_gate": {"status": "blocked"}}

    monkeypatch.setattr(verify_execution_no_pytest, "LiquidityChecker", lambda: _Module())
    monkeypatch.setattr(verify_execution_no_pytest, "RiskGatekeeper", lambda: _Module())
    monkeypatch.setattr(verify_execution_no_pytest, "PositionSizer", lambda: _Module())
    monkeypatch.setattr(verify_execution_no_pytest, "ExitManager", lambda: _Module())
    monkeypatch.setattr(verify_execution_no_pytest, "WorkflowRunner", lambda: _Workflow())
    monkeypatch.setattr(verify_execution_no_pytest, "audit_repo_sensitive_leaks", lambda _root: {"status": "PASS", "warnings": [], "failures": [], "scan_errors": []})

    try:
        verify_execution_no_pytest.main()
        assert False, "expected AssertionError"
    except AssertionError as exc:
        assert "Workflow output invalid" in str(exc)
