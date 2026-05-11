from __future__ import annotations

import tempfile
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

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
        _write(
            root / "scripts" / "bad.py",
            "OPENAI_API_KEY = 'sk-abc123abc123abc123abc123abc123'\n"
            "trace = 'Traceback (most recent call last):\\n  File \"/Users/me/leak.py\", line 1, in <module>\\n'\n",
        )

        report = audit_repo_sensitive_leaks(root, tracked_files=["scripts/bad.py"])

        assert report["status"] == "FAIL"
        assert report["failures"]
        kinds = {item["kind"] for item in report["failures"]}
        assert "secret_literal" in kinds or "secret_assignment" in kinds
        assert "raw_path" in kinds or "traceback" in kinds
