import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from check_shadow_code_purge_gate import evaluate_purge_gate


def test_shadow_code_purge_gate_detects_non_allowlisted_print(tmp_path):
    target = tmp_path / "bad_module.py"
    target.write_text("def run():\n    print('debug')\n", encoding="utf-8")
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(json.dumps({"allowed_print_calls": []}, ensure_ascii=False), encoding="utf-8")

    report = evaluate_purge_gate(targets=[target], allowlist_path=allowlist)
    assert report["passed"] is False
    assert report["violations"]


def test_shadow_code_purge_gate_respects_allowlist(tmp_path):
    target = tmp_path / "ok_module.py"
    target.write_text("def run():\n    print('allowed')\n", encoding="utf-8")
    rel = target.relative_to(ROOT).as_posix() if target.is_relative_to(ROOT) else str(target)
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(
        json.dumps({"allowed_print_calls": [{"path": rel, "line": 2}]}, ensure_ascii=False),
        encoding="utf-8",
    )

    report = evaluate_purge_gate(targets=[target], allowlist_path=allowlist)
    assert report["passed"] is True
    assert report["violations"] == []
