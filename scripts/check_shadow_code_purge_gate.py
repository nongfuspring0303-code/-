#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ALLOWLIST = ROOT / "configs" / "shadow_code_purge_allowlist.json"
DEFAULT_TARGETS = [
    ROOT / "scripts" / "full_workflow_runner.py",
    ROOT / "scripts" / "workflow_runner.py",
    ROOT / "scripts" / "system_log_evaluator.py",
]


@dataclass(frozen=True)
class PrintCall:
    path: str
    line: int


class _PrintCallVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.lines: List[int] = []

    def visit_Call(self, node: ast.Call) -> Any:  # noqa: N802
        if isinstance(node.func, ast.Name) and node.func.id == "print":
            self.lines.append(int(node.lineno))
        self.generic_visit(node)


def _parse_print_calls(path: Path) -> List[PrintCall]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    visitor = _PrintCallVisitor()
    visitor.visit(tree)
    try:
        rel = path.relative_to(ROOT).as_posix()
    except ValueError:
        rel = str(path)
    return [PrintCall(path=rel, line=line) for line in visitor.lines]


def _load_allowlist(path: Path) -> set[tuple[str, int]]:
    if not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    allowed = payload.get("allowed_print_calls", [])
    out: set[tuple[str, int]] = set()
    for row in allowed:
        if not isinstance(row, dict):
            continue
        rel = str(row.get("path", "")).strip()
        line = int(row.get("line", 0) or 0)
        if rel and line > 0:
            out.add((rel, line))
    return out


def evaluate_purge_gate(targets: List[Path], allowlist_path: Path) -> Dict[str, Any]:
    allowed = _load_allowlist(allowlist_path)
    violations: List[Dict[str, Any]] = []
    checked: List[str] = []
    for path in targets:
        if not path.exists():
            continue
        try:
            checked.append(path.relative_to(ROOT).as_posix())
        except ValueError:
            checked.append(str(path))
        for call in _parse_print_calls(path):
            if (call.path, call.line) in allowed:
                continue
            violations.append({"path": call.path, "line": call.line, "rule": "print_call_not_allowlisted"})

    return {
        "gate": "shadow_code_purge_gate",
        "checked_files": checked,
        "allowlist_path": (
            allowlist_path.relative_to(ROOT).as_posix()
            if allowlist_path.is_absolute() and allowlist_path.is_relative_to(ROOT)
            else str(allowlist_path)
        ),
        "violations": violations,
        "passed": len(violations) == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage5 shadow-code purge gate (print call allowlist check)")
    parser.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    parser.add_argument("--out", type=Path, default=None, help="Optional JSON report output path")
    parser.add_argument(
        "--target",
        action="append",
        default=[],
        help="Relative path under repo root to check; can be repeated. Defaults to Stage5 critical runtime files.",
    )
    args = parser.parse_args()

    targets = [ROOT / t for t in args.target] if args.target else list(DEFAULT_TARGETS)
    report = evaluate_purge_gate(targets=targets, allowlist_path=args.allowlist)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
