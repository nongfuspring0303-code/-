from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import project_gap_monitor as pgm


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _f(
    *,
    severity: str = "P1",
    category: str = "logs",
    module: str = "module",
    code: str = "CODE",
    message: str = "message",
    evidence_file: str = "logs/file.jsonl",
    normalized_field: str = "field",
    source: str = "source",
    suggested_fix: str = "fix",
    new: bool = True,
    seen_days: int = 1,
    occurrence_count: int = 1,
    suppressed: bool = False,
    line_hint: int | str | None = None,
    repro_command: str | None = None,
) -> pgm.Finding:
    finding = pgm.Finding(
        dedupe_key="",
        severity=severity,
        category=category,
        module=module,
        code=code,
        message=message,
        evidence_file=evidence_file,
        normalized_field=normalized_field,
        source=source,
        suggested_fix=suggested_fix,
        new=new,
        seen_days=seen_days,
        occurrence_count=occurrence_count,
        suppressed=suppressed,
        line_hint=line_hint,
        repro_command=repro_command,
    )
    finding.dedupe_key = pgm._dedupe_key(finding)
    return finding


def test_first_run_creates_outputs_and_zero_delta(tmp_path: Path, monkeypatch) -> None:
    report_json = tmp_path / "logs" / "project_gap_report.json"
    report_md = tmp_path / "logs" / "project_gap_report.md"
    state_path = tmp_path / "logs" / "project_gap_state.json"

    monkeypatch.setattr(pgm, "collect_findings", lambda *_args, **_kwargs: [_f(code="FIRST_RUN_GAP")])

    report = pgm.run_project_gap_monitor(
        root=tmp_path,
        logs_dir=tmp_path / "logs",
        state_path=state_path,
        report_json_path=report_json,
        report_md_path=report_md,
        allowlist_path=tmp_path / "configs" / "project_gap_monitor_allowlist.yaml",
    )

    assert report["delta_vs_prev"] == {
        "new_count": 0,
        "resolved_count": 0,
        "unchanged_count": 0,
        "suppressed_count": 0,
    }
    assert report_json.exists()
    assert report_md.exists()
    assert state_path.exists()
    saved = json.loads(report_json.read_text(encoding="utf-8"))
    assert saved["schema_version"] == "project_gap_report.v1"
    assert saved["findings"][0]["code"] == "FIRST_RUN_GAP"
    assert not (ROOT / "logs" / "project_gap_report.json").exists()


def test_status_rules_map_counts_to_overall_status() -> None:
    assert pgm._status_from_counts(1, 0) == "RED"
    assert pgm._status_from_counts(0, 1) == "YELLOW"
    assert pgm._status_from_counts(0, 0) == "GREEN"


def test_finding_sorting_prefers_severity_new_category_then_history() -> None:
    findings = [
        _f(severity="P1", category="test", seen_days=4, occurrence_count=1, module="t1", code="C1"),
        _f(severity="P0", category="config", new=False, module="a", code="C2"),
        _f(severity="P0", category="security", new=True, module="b", code="C3"),
        _f(severity="P1", category="config", seen_days=7, occurrence_count=9, module="t2", code="C4"),
    ]
    ordered = sorted(findings, key=pgm._sort_key)
    assert [item.category for item in ordered] == ["security", "config", "config", "test"]
    assert ordered[0].new is True
    assert ordered[1].new is False
    assert ordered[2].seen_days == 7


def test_dedupe_key_joins_required_dimensions() -> None:
    finding = _f(category="logs", module="trace_scorecard", code="BAD_JSONL", evidence_file="logs/x.jsonl", normalized_field="line")
    assert pgm._dedupe_key(finding) == "logs|trace_scorecard|BAD_JSONL|logs/x.jsonl|line"


def test_finding_serializes_line_hint_and_repro_command() -> None:
    finding = _f(line_hint=12, repro_command="python3 -m pytest -q tests/test_project_gap_monitor.py")
    payload = finding.as_dict()
    assert payload["line_hint"] == 12
    assert payload["repro_command"] == "python3 -m pytest -q tests/test_project_gap_monitor.py"


def test_markdown_report_includes_line_hint_and_repro_command() -> None:
    finding = _f(
        line_hint=12,
        repro_command="python3 -m pytest -q tests/test_project_gap_monitor.py",
        message="gap | markdown",
        suggested_fix="run | monitor",
    )
    report = {
        "generated_at": "2026-05-08T00:00:00Z",
        "overall_status": "YELLOW",
        "summary": {"p0_count": 0, "p1_count": 1, "p2_count": 0, "total_count": 1},
        "delta_vs_prev": {"new_count": 1, "resolved_count": 0, "unchanged_count": 0, "suppressed_count": 0},
        "top_blockers": [finding.as_dict()],
        "findings": [finding.as_dict()],
    }
    markdown = pgm._render_markdown(report)
    assert "line_hint" in markdown
    assert "repro_command" in markdown
    assert "12" in markdown
    assert "python3 -m pytest -q tests/test_project_gap_monitor.py" in markdown
    assert "gap \\| markdown" in markdown
    assert "run \\| monitor" in markdown


def test_state_persists_line_hint_and_repro_command() -> None:
    finding = _f(
        line_hint=12,
        repro_command="python3 -m pytest -q tests/test_project_gap_monitor.py",
    )
    state = pgm._build_state([finding])
    key = finding.dedupe_key
    assert state["findings_by_key"][key]["line_hint"] == 12
    assert state["findings_by_key"][key]["repro_command"] == "python3 -m pytest -q tests/test_project_gap_monitor.py"


def test_delta_vs_prev_tracks_new_resolved_unchanged_and_suppressed() -> None:
    previous_state = {
        "active_dedupe_keys": ["logs|a|A|f1|x", "logs|c|C|f3|z"],
        "findings_by_key": {},
    }
    current = [
        _f(module="a", code="A", evidence_file="f1", normalized_field="x", new=False),
        _f(module="b", code="B", evidence_file="f2", normalized_field="y", new=True),
        _f(module="d", code="D", evidence_file="f4", normalized_field="w", suppressed=True),
    ]
    current[0].dedupe_key = "logs|a|A|f1|x"
    current[1].dedupe_key = "logs|b|B|f2|y"
    current[2].dedupe_key = "logs|d|D|f4|w"
    delta = pgm._delta_vs_prev(current, previous_state)
    assert delta == {
        "new_count": 1,
        "resolved_count": 1,
        "unchanged_count": 1,
        "suppressed_count": 1,
    }


def test_allowlist_suppresses_matching_finding_and_counts_it(tmp_path: Path) -> None:
    finding = _f(category="logs", module="project_gap_monitor", code="LOG_FILE_MISSING", evidence_file="logs/project_gap_report.json", normalized_field="*")
    finding.dedupe_key = "logs|project_gap_monitor|LOG_FILE_MISSING|logs/project_gap_report.json|*"
    rules = [
        pgm.AllowlistRule(
            category="logs",
            module="project_gap_monitor",
            code="LOG_FILE_MISSING",
            evidence_file="logs/project_gap_report.json",
            normalized_field="*",
            reason="expected before first monitor run",
            allow_p0=False,
        )
    ]
    bucket = {finding.dedupe_key: finding}
    pgm._apply_allowlist(bucket, rules)
    assert finding.suppressed is True
    delta = pgm._delta_vs_prev([finding], {"active_dedupe_keys": [], "findings_by_key": {}})
    assert delta["suppressed_count"] == 1


def test_scan_logs_reports_bad_jsonl_and_secret_or_path_leaks(tmp_path: Path, monkeypatch) -> None:
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    _write(
        logs_dir / "trace_scorecard.jsonl",
        "\n".join(
            [
                '{"trace_id":"T1","logged_at":"2026-05-06T10:00:00Z"}',
                "not-json",
                '{"trace_id":"T2","message":"Traceback boom /Users/jia/secret"}',
            ]
        )
        + "\n",
    )
    for name in ("scan_module_registry", "scan_schemas", "scan_configs", "scan_tests", "scan_scripts", "scan_canvas", "scan_system_health_source"):
        monkeypatch.setattr(pgm, name, lambda *args, **kwargs: [])

    report = pgm.run_project_gap_monitor(root=tmp_path, logs_dir=logs_dir)
    codes = {finding["code"] for finding in report["findings"]}
    assert "BAD_JSONL" in codes
    assert "RAW_TRACEBACK_LEAK" in codes
    assert "LOCAL_PATH_LEAK" in codes


def test_scan_canvas_finds_missing_dom_contract_markers(tmp_path: Path, monkeypatch) -> None:
    canvas_dir = tmp_path / "canvas"
    _write(canvas_dir / "index.html", "<html><body><div>missing markers</div></body></html>")
    _write(canvas_dir / "app.js", "const x = 1;\n")
    _write(canvas_dir / "styles.css", "body{}\n")
    for name in ("scan_module_registry", "scan_schemas", "scan_configs", "scan_tests", "scan_scripts", "scan_logs", "scan_system_health_source"):
        monkeypatch.setattr(pgm, name, lambda *args, **kwargs: [])

    report = pgm.run_project_gap_monitor(root=tmp_path, logs_dir=tmp_path / "logs")
    codes = {finding["code"] for finding in report["findings"]}
    assert "DOM_CONTRACT_MARKER_MISSING" in codes
    assert "FOUR_STATE_MARKER_MISSING" in codes


def test_scan_canvas_requires_data_state_attribute_markers(tmp_path: Path, monkeypatch) -> None:
    canvas_text = "FAILED MISSING PENDING STALE but no data-state markers"
    canvas_dir = tmp_path / "canvas"
    _write(canvas_dir / "index.html", "<html></html>")
    _write(canvas_dir / "app.js", "const x = 1;\n")
    _write(canvas_dir / "styles.css", "body{}\n")

    def _fake_read(path: Path) -> str:
        return canvas_text

    monkeypatch.setattr(pgm, "_safe_read_text", _fake_read)

    findings = pgm.scan_canvas(tmp_path)
    codes = [finding.code for finding in findings]
    assert "FOUR_STATE_MARKER_MISSING" in codes
    assert all('data-state="' not in finding.message for finding in findings if finding.code == "FOUR_STATE_MARKER_MISSING")


def test_scan_configs_finds_hardcoded_secret_like_values(tmp_path: Path, monkeypatch) -> None:
    configs_dir = tmp_path / "configs"
    _write(configs_dir / "bad.yaml", "password: supersecret\napi_key: abc123\n")
    for name in ("scan_module_registry", "scan_schemas", "scan_tests", "scan_scripts", "scan_canvas", "scan_logs", "scan_system_health_source"):
        monkeypatch.setattr(pgm, name, lambda *args, **kwargs: [])

    report = pgm.run_project_gap_monitor(root=tmp_path, logs_dir=tmp_path / "logs")
    codes = {finding["code"] for finding in report["findings"]}
    assert "HARD_CODED_SECRET" in codes


def test_scan_scripts_finds_splitlines_log_risk(tmp_path: Path, monkeypatch) -> None:
    scripts_dir = tmp_path / "scripts"
    _write(
        scripts_dir / "bad.py",
        "from pathlib import Path\n\nLOG = Path('logs/x.jsonl')\nrows = LOG.read_text(encoding='utf-8').splitlines()\n",
    )
    for name in ("scan_module_registry", "scan_schemas", "scan_configs", "scan_tests", "scan_canvas", "scan_logs", "scan_system_health_source"):
        monkeypatch.setattr(pgm, name, lambda *args, **kwargs: [])

    report = pgm.run_project_gap_monitor(root=tmp_path, logs_dir=tmp_path / "logs")
    codes = {finding["code"] for finding in report["findings"]}
    assert "LARGE_LOG_READTEXT_SPLITLINES" in codes


def test_scan_logs_uses_tail_window_for_large_files(tmp_path: Path, monkeypatch) -> None:
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for idx in range(3100):
        if idx < 1000:
            rows.append(f'{{"trace_id":"T{idx}","message":"Traceback /Users/jia/secret"}}')
        else:
            rows.append(f'{{"trace_id":"T{idx}","logged_at":"2026-05-06T10:00:00Z"}}')
    _write(logs_dir / "trace_scorecard.jsonl", "\n".join(rows) + "\n")

    def _boom(*_args, **_kwargs):
        raise AssertionError("scan_logs should not call _safe_read_text for log payloads")

    monkeypatch.setattr(pgm, "_safe_read_text", _boom)
    findings = pgm.scan_logs(tmp_path, logs_dir)
    codes = {finding.code for finding in findings}
    assert "BAD_JSONL" not in codes
    assert "RAW_TRACEBACK_LEAK" not in codes
    assert "LOCAL_PATH_LEAK" not in codes
    assert "SECRET_LITERAL_LEAK" not in codes
    assert "LOG_FILE_MISSING" in codes


def test_missing_health_source_reports_p2_without_upgrading_status(tmp_path: Path, monkeypatch) -> None:
    for name in ("scan_module_registry", "scan_schemas", "scan_configs", "scan_tests", "scan_scripts", "scan_canvas", "scan_logs"):
        monkeypatch.setattr(pgm, name, lambda *args, **kwargs: [])

    report = pgm.run_project_gap_monitor(root=tmp_path, logs_dir=tmp_path / "logs")
    assert report["overall_status"] == "GREEN"
    assert report["summary"]["p0_count"] == 0
    assert report["summary"]["p1_count"] == 0
    assert any(finding["code"] == "HEALTH_SOURCE_MISSING" and finding["severity"] == "P2" for finding in report["findings"])
