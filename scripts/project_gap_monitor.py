#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception as exc:  # noqa: BLE001
    raise SystemExit(f"Missing yaml dependency: {exc}") from exc


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOGS_DIR = ROOT / "logs"
DEFAULT_STATE_PATH = DEFAULT_LOGS_DIR / "project_gap_state.json"
DEFAULT_REPORT_JSON = DEFAULT_LOGS_DIR / "project_gap_report.json"
DEFAULT_REPORT_MD = DEFAULT_LOGS_DIR / "project_gap_report.md"
DEFAULT_ALLOWLIST = ROOT / "configs" / "project_gap_monitor_allowlist.yaml"
SCHEMA_VERSION = "project_gap_report.v1"
STATE_SCHEMA_VERSION = "project_gap_state.v1"
ALLOWLIST_SCHEMA_VERSION = "project_gap_monitor.allowlist.v1"
STALE_AFTER_DAYS = 2

SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}
CATEGORY_WEIGHTS = {
    "security": 0,
    "hardcode": 1,
    "logs": 2,
    "config": 3,
    "schema": 4,
    "module": 5,
    "test": 6,
    "frontend": 7,
    "health": 8,
    "other": 9,
}


@dataclass
class Finding:
    dedupe_key: str
    severity: str
    category: str
    module: str
    code: str
    message: str
    evidence_file: str
    normalized_field: str
    source: str
    suggested_fix: str
    new: bool = True
    seen_days: int = 1
    occurrence_count: int = 1
    suppressed: bool = False
    first_seen_at: str | None = None
    last_seen_at: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "dedupe_key": self.dedupe_key,
            "severity": self.severity,
            "category": self.category,
            "module": self.module,
            "code": self.code,
            "message": self.message,
            "evidence_file": self.evidence_file,
            "normalized_field": self.normalized_field,
            "new": self.new,
            "seen_days": self.seen_days,
            "occurrence_count": self.occurrence_count,
            "suppressed": self.suppressed,
            "source": self.source,
            "suggested_fix": self.suggested_fix,
        }


@dataclass
class AllowlistRule:
    category: str = "*"
    module: str = "*"
    code: str = "*"
    evidence_file: str = "*"
    normalized_field: str = "*"
    reason: str = ""
    expires_at: str | None = None
    allow_p0: bool = False

    def matches(self, finding: Finding) -> bool:
        checks = (
            (self.category, finding.category),
            (self.module, finding.module),
            (self.code, finding.code),
            (self.evidence_file, finding.evidence_file),
            (self.normalized_field, finding.normalized_field),
        )
        for rule_value, actual_value in checks:
            if rule_value in ("", "*", None):
                continue
            if not fnmatch(actual_value, str(rule_value)):
                return False
        if finding.severity == "P0" and not self.allow_p0:
            return False
        if self.expires_at:
            try:
                expiry = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            except ValueError:
                return False
            if expiry.astimezone(timezone.utc) < datetime.now(timezone.utc):
                return False
        return True


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _now_utc_iso() -> str:
    return _now_utc().isoformat().replace("+00:00", "Z")


def _safe_read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _relative_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _load_yaml(path: Path) -> Any:
    return yaml.safe_load(_safe_read_text(path))


def _load_json(path: Path) -> Any:
    return json.loads(_safe_read_text(path))


def _parse_structured_file(path: Path) -> tuple[Any | None, str | None]:
    try:
        if path.suffix.lower() in {".json"}:
            return _load_json(path), None
        return _load_yaml(path), None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def _dedupe_key(finding: Finding) -> str:
    return "|".join(
        [
            finding.category,
            finding.module,
            finding.code,
            finding.evidence_file,
            finding.normalized_field,
        ]
    )


def _make_finding(
    *,
    severity: str,
    category: str,
    module: str,
    code: str,
    message: str,
    evidence_file: str,
    normalized_field: str,
    source: str,
    suggested_fix: str,
) -> Finding:
    finding = Finding(
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
    )
    finding.dedupe_key = _dedupe_key(finding)
    return finding


def _merge_finding(bucket: dict[str, Finding], finding: Finding) -> None:
    existing = bucket.get(finding.dedupe_key)
    if existing is None:
        bucket[finding.dedupe_key] = finding
        return
    existing.occurrence_count += finding.occurrence_count
    existing.severity = min(existing.severity, finding.severity, key=lambda s: SEVERITY_ORDER[s])
    if finding.message and finding.message not in existing.message:
        existing.message = f"{existing.message}; {finding.message}"


def _mark_history(findings: dict[str, Finding], previous_state: dict[str, Any] | None) -> None:
    prev_map = (previous_state or {}).get("findings_by_key", {})
    prev_keys = set((previous_state or {}).get("active_dedupe_keys", []))
    now = _now_utc()
    for key, finding in findings.items():
        prev = prev_map.get(key, {}) if isinstance(prev_map, dict) else {}
        first_seen = prev.get("first_seen_at") or finding.first_seen_at or now.isoformat().replace("+00:00", "Z")
        try:
            first_seen_dt = datetime.fromisoformat(str(first_seen).replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            first_seen_dt = now
        finding.first_seen_at = first_seen_dt.isoformat().replace("+00:00", "Z")
        finding.last_seen_at = now.isoformat().replace("+00:00", "Z")
        finding.new = key not in prev_keys
        if key in prev_map and isinstance(prev_map[key], dict):
            prev_occ = int(prev_map[key].get("occurrence_count", 0) or 0)
            finding.occurrence_count += prev_occ
        finding.seen_days = max(1, (now.date() - first_seen_dt.date()).days + 1)


def _load_previous_state(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(_safe_read_text(path))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _load_allowlist(path: Path) -> list[AllowlistRule]:
    if not path.exists():
        return []
    payload = yaml.safe_load(_safe_read_text(path)) or {}
    rules = payload.get("rules", [])
    out: list[AllowlistRule] = []
    if not isinstance(rules, list):
        return out
    for row in rules:
        if not isinstance(row, dict):
            continue
        out.append(
            AllowlistRule(
                category=str(row.get("category", "*") or "*"),
                module=str(row.get("module", "*") or "*"),
                code=str(row.get("code", "*") or "*"),
                evidence_file=str(row.get("evidence_file", "*") or "*"),
                normalized_field=str(row.get("normalized_field", "*") or "*"),
                reason=str(row.get("reason", "") or ""),
                expires_at=row.get("expires_at"),
                allow_p0=bool(row.get("allow_p0", False)),
            )
        )
    return out


def _apply_allowlist(findings: dict[str, Finding], rules: list[AllowlistRule]) -> None:
    for finding in findings.values():
        for rule in rules:
            if rule.matches(finding):
                finding.suppressed = True
                break


def _latest_timestamp_from_text(text: str) -> datetime | None:
    latest: datetime | None = None
    for line in text.splitlines():
        if "/Users/" in line or "Traceback" in line or "traceback" in line.lower():
            continue
        match = re.search(r"20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", line)
        if not match:
            continue
        try:
            ts = datetime.fromisoformat(match.group(0).replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            continue
        if latest is None or ts > latest:
            latest = ts
    return latest


def _jsonl_bad_lines(path: Path, text: str) -> int:
    bad_lines = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            json.loads(line)
        except Exception:  # noqa: BLE001
            bad_lines += 1
    return bad_lines


def scan_module_registry(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    path = root / "module-registry.yaml"
    if not path.exists():
        findings.append(
            _make_finding(
                severity="P0",
                category="module",
                module="module-registry",
                code="MODULE_REGISTRY_MISSING",
                message="module-registry.yaml is missing.",
                evidence_file=_relative_path(path, root),
                normalized_field="file",
                source="module-registry.yaml",
                suggested_fix="Restore module-registry.yaml from the canonical source of truth.",
            )
        )
        return findings
    data, error = _parse_structured_file(path)
    if error is not None:
        findings.append(
            _make_finding(
                severity="P0",
                category="module",
                module="module-registry",
                code="MODULE_REGISTRY_PARSE_ERROR",
                message=f"module-registry.yaml could not be parsed: {error}",
                evidence_file=_relative_path(path, root),
                normalized_field="file",
                source="module-registry.yaml",
                suggested_fix="Fix YAML syntax or encoding issues in module-registry.yaml.",
            )
        )
        return findings
    registry = data.get("registry", []) if isinstance(data, dict) else []
    if not isinstance(registry, list) or not registry:
        findings.append(
            _make_finding(
                severity="P1",
                category="module",
                module="module-registry",
                code="MODULE_REGISTRY_EMPTY",
                message="module-registry.yaml has no registry entries.",
                evidence_file=_relative_path(path, root),
                normalized_field="registry",
                source="module-registry.yaml",
                suggested_fix="Populate module-registry.yaml with the authoritative registry entries.",
            )
        )
        return findings

    for entry in registry:
        if not isinstance(entry, dict):
            continue
        module_name = str(entry.get("name", "") or "").strip() or "unknown"
        missing_fields = [field for field in ("owner", "status", "test_case") if not str(entry.get(field, "") or "").strip()]
        if missing_fields:
            findings.append(
                _make_finding(
                    severity="P1",
                    category="module",
                    module=module_name,
                    code="MODULE_REGISTRY_METADATA_MISSING",
                    message=f"Module {module_name} is missing registry metadata: {', '.join(missing_fields)}.",
                    evidence_file=_relative_path(path, root),
                    normalized_field=",".join(missing_fields),
                    source="module-registry.yaml",
                    suggested_fix="Add owner/status/test_case metadata for this module entry.",
                )
            )
    return findings


def scan_schemas(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    schemas_dir = root / "schemas"
    if not schemas_dir.exists():
        findings.append(
            _make_finding(
                severity="P0",
                category="schema",
                module="schemas",
                code="SCHEMAS_DIR_MISSING",
                message="schemas/ directory is missing.",
                evidence_file=_relative_path(schemas_dir, root),
                normalized_field="dir",
                source="schemas",
                suggested_fix="Restore the schemas/ directory.",
            )
        )
        return findings
    for path in sorted(p for p in schemas_dir.rglob("*") if p.is_file()):
        data, error = _parse_structured_file(path)
        rel = _relative_path(path, root)
        if error is not None:
            findings.append(
                _make_finding(
                    severity="P0",
                    category="schema",
                    module=path.stem,
                    code="SCHEMA_PARSE_ERROR",
                    message=f"Schema file {rel} could not be parsed: {error}",
                    evidence_file=rel,
                    normalized_field="file",
                    source=rel,
                    suggested_fix="Fix schema syntax so the file can be parsed reliably.",
                )
            )
            continue
        if not isinstance(data, dict):
            findings.append(
                _make_finding(
                    severity="P1",
                    category="schema",
                    module=path.stem,
                    code="SCHEMA_NOT_OBJECT",
                    message=f"Schema file {rel} does not contain a mapping object.",
                    evidence_file=rel,
                    normalized_field="schema",
                    source=rel,
                    suggested_fix="Convert the schema to a mapping object with version/required/properties metadata.",
                )
            )
            continue
        missing: list[str] = []
        if not any(key in data for key in ("version", "schema_version")):
            missing.append("version")
        if "required" not in data:
            missing.append("required")
        if "properties" not in data:
            missing.append("properties")
        if missing:
            findings.append(
                _make_finding(
                    severity="P1",
                    category="schema",
                    module=path.stem,
                    code="SCHEMA_METADATA_MISSING",
                    message=f"Schema file {rel} is missing: {', '.join(missing)}.",
                    evidence_file=rel,
                    normalized_field=",".join(missing),
                    source=rel,
                    suggested_fix="Add version, required, and properties metadata to the schema file.",
                )
            )
    return findings


def scan_configs(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    configs_dir = root / "configs"
    if not configs_dir.exists():
        findings.append(
            _make_finding(
                severity="P0",
                category="config",
                module="configs",
                code="CONFIGS_DIR_MISSING",
                message="configs/ directory is missing.",
                evidence_file=_relative_path(configs_dir, root),
                normalized_field="dir",
                source="configs",
                suggested_fix="Restore the configs/ directory.",
            )
        )
        return findings

    config_files = [p for p in configs_dir.rglob("*") if p.is_file()]
    for path in sorted(config_files):
        rel = _relative_path(path, root)
        text = _safe_read_text(path)
        secret_match = re.search(r"(?i)\b(?:token|secret|password|api[_-]?key|authorization)\b\s*[:=]\s*['\"]?[^'\"\s#]+", text)
        if secret_match:
            findings.append(
                _make_finding(
                    severity="P0",
                    category="security",
                    module=path.stem,
                    code="HARD_CODED_SECRET",
                    message=f"Potential hardcoded secret-like value found in {rel}.",
                    evidence_file=rel,
                    normalized_field="literal",
                    source=rel,
                    suggested_fix="Move secrets to environment variables or secret storage and keep only placeholders in config.",
                )
            )
        if "/Users/" in text:
            findings.append(
                _make_finding(
                    severity="P1",
                    category="hardcode",
                    module=path.stem,
                    code="HARD_CODED_LOCAL_PATH",
                    message=f"Local absolute path found in {rel}.",
                    evidence_file=rel,
                    normalized_field="/Users/",
                    source=rel,
                    suggested_fix="Replace the absolute path with a repository-relative or environment-derived path.",
                )
            )

    modules_cfg = configs_dir / "edt-modules-config.yaml"
    registry = root / "module-registry.yaml"
    if modules_cfg.exists() and registry.exists():
        findings.append(
            _make_finding(
                severity="P1",
                category="config",
                module="config_source",
                code="DUPLICATE_CONFIG_SOURCE",
                message="module-registry.yaml and configs/edt-modules-config.yaml coexist as overlapping module sources of truth.",
                evidence_file="module-registry.yaml",
                normalized_field="module-source",
                source="configs/edt-modules-config.yaml",
                suggested_fix="Keep one canonical module registry or clearly define the ownership split between the two sources.",
            )
        )
    return findings


def _module_test_candidates(module_name: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z][a-z]*|[A-Z][a-z]*|[0-9]+", module_name)
    raw = module_name.lower()
    candidates = {
        f"tests/test_{raw}.py",
        f"tests/test_{raw.replace('-', '_')}.py",
        f"tests/test_{raw.replace(' ', '_')}.py",
    }
    if tokens:
        snake = "_".join(token.lower() for token in tokens)
        candidates.add(f"tests/test_{snake}.py")
    return sorted(candidates)


def scan_tests(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    tests_dir = root / "tests"
    if not tests_dir.exists():
        findings.append(
            _make_finding(
                severity="P0",
                category="test",
                module="tests",
                code="TESTS_DIR_MISSING",
                message="tests/ directory is missing.",
                evidence_file=_relative_path(tests_dir, root),
                normalized_field="dir",
                source="tests",
                suggested_fix="Restore the tests/ directory.",
            )
        )
        return findings

    registry_path = root / "module-registry.yaml"
    registry_entries: list[dict[str, Any]] = []
    if registry_path.exists():
        data, error = _parse_structured_file(registry_path)
        if error is None and isinstance(data, dict) and isinstance(data.get("registry"), list):
            registry_entries = [row for row in data["registry"] if isinstance(row, dict)]

    test_files = {p.relative_to(root).as_posix(): p for p in tests_dir.rglob("test_*.py") if p.is_file()}

    for entry in registry_entries:
        module_name = str(entry.get("name", "") or "").strip()
        if not module_name:
            continue
        candidates = _module_test_candidates(module_name)
        chosen = next((candidate for candidate in candidates if candidate in test_files), None)
        test_case = str(entry.get("test_case", "") or "").strip()
        if not test_case and chosen is None:
            findings.append(
                _make_finding(
                    severity="P1",
                    category="test",
                    module=module_name,
                    code="MISSING_MODULE_TEST",
                    message=f"No corresponding test file was found for module {module_name}.",
                    evidence_file="module-registry.yaml",
                    normalized_field="test_case",
                    source="module-registry.yaml",
                    suggested_fix="Add a dedicated module test file and register it in module-registry.yaml.",
                )
            )
            continue
        if test_case:
            test_path = root / test_case
            if not test_path.exists():
                findings.append(
                    _make_finding(
                        severity="P1",
                        category="test",
                        module=module_name,
                        code="TEST_CASE_MISSING",
                        message=f"Registered test_case is missing for module {module_name}: {test_case}.",
                        evidence_file="module-registry.yaml",
                        normalized_field="test_case",
                        source="module-registry.yaml",
                        suggested_fix="Restore the test_case path or update the registry to the real test file.",
                    )
                )
                continue
            text = _safe_read_text(test_path)
            failure_markers = ("pytest.raises", "status == \"error\"", "status in {\"error\"", "partial", "missing", "blocked", "fallback", "not found", "not_swallowed", "error")
            if not any(marker in text for marker in failure_markers):
                findings.append(
                    _make_finding(
                        severity="P1",
                        category="test",
                        module=module_name,
                        code="FAILURE_PATH_TEST_MISSING",
                        message=f"Test file {test_case} does not appear to cover failure-path behavior for {module_name}.",
                        evidence_file=test_case,
                        normalized_field="failure_path",
                        source=test_case,
                        suggested_fix="Add at least one failure-path assertion such as partial/error/missing handling.",
                    )
                )
    return findings


def scan_scripts(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    scripts_dir = root / "scripts"
    if not scripts_dir.exists():
        findings.append(
            _make_finding(
                severity="P0",
                category="module",
                module="scripts",
                code="SCRIPTS_DIR_MISSING",
                message="scripts/ directory is missing.",
                evidence_file=_relative_path(scripts_dir, root),
                normalized_field="dir",
                source="scripts",
                suggested_fix="Restore the scripts/ directory.",
            )
        )
        return findings

    for path in sorted(p for p in scripts_dir.rglob("*.py") if p.is_file()):
        rel = _relative_path(path, root)
        try:
            text = _safe_read_text(path)
        except Exception as exc:  # noqa: BLE001
            findings.append(
                _make_finding(
                    severity="P0",
                    category="module",
                    module=path.stem,
                    code="SCRIPT_READ_FAILED",
                    message=f"Could not read {rel}: {exc}",
                    evidence_file=rel,
                    normalized_field="file",
                    source=rel,
                    suggested_fix="Fix file permissions or encoding so the script can be scanned.",
                )
            )
            continue
        try:
            ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            findings.append(
                _make_finding(
                    severity="P0",
                    category="module",
                    module=path.stem,
                    code="PYTHON_SYNTAX_ERROR",
                    message=f"Syntax error in {rel}: {exc.msg}",
                    evidence_file=rel,
                    normalized_field="syntax",
                    source=rel,
                    suggested_fix="Fix the Python syntax error.",
                )
            )
            continue

        tree = ast.parse(text, filename=str(path))
        bare_except = any(isinstance(node, ast.ExceptHandler) and node.type is None for node in ast.walk(tree))
        if bare_except:
            findings.append(
                _make_finding(
                    severity="P1",
                    category="module",
                    module=path.stem,
                    code="BARE_EXCEPT",
                    message=f"Bare except handler found in {rel}.",
                    evidence_file=rel,
                    normalized_field="except",
                    source=rel,
                    suggested_fix="Replace bare except with specific exceptions and avoid swallowing errors.",
                )
            )
        if "/Users/" in text:
            findings.append(
                _make_finding(
                    severity="P1",
                    category="hardcode",
                    module=path.stem,
                    code="HARDCODED_ABSOLUTE_PATH",
                    message=f"Hardcoded /Users/ path found in {rel}.",
                    evidence_file=rel,
                    normalized_field="/Users/",
                    source=rel,
                    suggested_fix="Replace the absolute path with a repo-relative or environment-derived path.",
                )
            )
        if "read_text(" in text and "splitlines()" in text and "logs" in text:
            findings.append(
                _make_finding(
                    severity="P1",
                    category="logs",
                    module=path.stem,
                    code="LARGE_LOG_READTEXT_SPLITLINES",
                    message=f"{rel} uses read_text().splitlines() on log-like content, which can scale poorly for large files.",
                    evidence_file=rel,
                    normalized_field="read_text.splitlines",
                    source=rel,
                    suggested_fix="Stream the file or use a tail reader instead of loading all lines at once.",
                )
            )
    return findings


def scan_canvas(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    html = root / "canvas" / "index.html"
    js = root / "canvas" / "app.js"
    css = root / "canvas" / "styles.css"
    if not html.exists() or not js.exists() or not css.exists():
        missing = [str(path.relative_to(root)) for path in (html, js, css) if not path.exists()]
        findings.append(
            _make_finding(
                severity="P0",
                category="frontend",
                module="canvas",
                code="CANVAS_ASSET_MISSING",
                message=f"Canvas assets are missing: {', '.join(missing)}.",
                evidence_file="canvas",
                normalized_field="asset",
                source="canvas",
                suggested_fix="Restore the missing canvas assets.",
            )
        )
        return findings

    html_text = _safe_read_text(html)
    js_text = _safe_read_text(js)
    css_text = _safe_read_text(css)
    canvas_text = "\n".join([html_text, js_text, css_text])

    required_markers = [
        ('data-module="TraceDetailPanel"', "TraceDetailPanel", "data-module"),
        ('data-key="execution_suggestion.trade_type"', "ExecutionSuggestionCard", "data-key"),
        ('data-key="path_quality_eval.composite_score"', "PathQualityEvalCard", "data-key"),
        ('data-key="trace_scorecard.final_action"', "TraceScorecardCard", "data-key"),
        ('data-key="pipeline_stage.stage"', "PipelineStageCard", "data-key"),
        ('data-module="EmptyStateCard"', "EmptyStateCard", "data-module"),
        ('data-key="empty_state"', "EmptyStateCard", "data-key"),
    ]
    for marker, module_name, normalized_field in required_markers:
        if marker not in canvas_text:
            findings.append(
                _make_finding(
                    severity="P1",
                    category="frontend",
                    module=module_name,
                    code="DOM_CONTRACT_MARKER_MISSING",
                    message=f"Canvas contract marker missing: {marker}.",
                    evidence_file="canvas/index.html",
                    normalized_field=normalized_field,
                    source="canvas",
                    suggested_fix="Add the missing data-module/data-key marker to the trace detail DOM contract.",
                )
            )

    for state in ("MISSING", "FAILED", "PENDING", "STALE"):
        if state not in canvas_text:
            findings.append(
                _make_finding(
                    severity="P1",
                    category="frontend",
                    module="TraceDetailPanel",
                    code="FOUR_STATE_MARKER_MISSING",
                    message=f"Canvas does not contain required state marker {state}.",
                    evidence_file="canvas/app.js",
                    normalized_field="data-state",
                    source="canvas",
                    suggested_fix="Render the full four-state contract in the trace detail panel.",
                )
            )

    if "暂无数据" in canvas_text and "ApiErrorCard" in canvas_text:
        findings.append(
            _make_finding(
                severity="P0",
                category="frontend",
                module="ApiErrorCard",
                code="ERROR_RENDERED_AS_EMPTY",
                message="Canvas appears to route an error state through empty/no-data text.",
                evidence_file="canvas/app.js",
                normalized_field="failed_state",
                source="canvas",
                suggested_fix="Render API/network failures as FAILED with code/message/request_id instead of empty-state text.",
            )
        )
    return findings


def scan_logs(root: Path, logs_dir: Path) -> list[Finding]:
    findings: list[Finding] = []
    if not logs_dir.exists():
        findings.append(
            _make_finding(
                severity="P1",
                category="logs",
                module="logs",
                code="LOGS_DIR_MISSING",
                message="logs/ directory is missing.",
                evidence_file=_relative_path(logs_dir, root),
                normalized_field="dir",
                source="logs",
                suggested_fix="Create the logs/ directory before running the monitor.",
            )
        )
        return findings

    key_files = [
        "trace_scorecard.jsonl",
        "pipeline_stage.jsonl",
        "raw_news_ingest.jsonl",
        "market_data_provenance.jsonl",
        "decision_gate.jsonl",
        "rejected_events.jsonl",
        "quarantine_replay.jsonl",
        "replay_write.jsonl",
        "execution_emit.jsonl",
        "health_signals.jsonl",
    ]

    for name in key_files:
        path = logs_dir / name
        rel = _relative_path(path, root)
        if not path.exists():
            findings.append(
                _make_finding(
                    severity="P1",
                    category="logs",
                    module=name,
                    code="LOG_FILE_MISSING",
                    message=f"Expected log file is missing: {rel}.",
                    evidence_file=rel,
                    normalized_field="file",
                    source=rel,
                    suggested_fix="Ensure the pipeline writes this artifact or suppress it explicitly until the producer exists.",
                )
            )
            continue

        try:
            text = _safe_read_text(path)
        except Exception as exc:  # noqa: BLE001
            findings.append(
                _make_finding(
                    severity="P1",
                    category="logs",
                    module=name,
                    code="LOG_FILE_UNREADABLE",
                    message=f"Log file {rel} could not be read: {exc}",
                    evidence_file=rel,
                    normalized_field="file",
                    source=rel,
                    suggested_fix="Fix permissions or encoding so the log file can be inspected.",
                )
            )
            continue
        if not text.strip():
            findings.append(
                _make_finding(
                    severity="P1",
                    category="logs",
                    module=name,
                    code="LOG_FILE_EMPTY",
                    message=f"Log file {rel} is empty.",
                    evidence_file=rel,
                    normalized_field="file",
                    source=rel,
                    suggested_fix="Ensure the producer writes at least one record or suppress the expected empty state.",
                )
            )
            continue
        if name.endswith(".jsonl"):
            bad_lines = _jsonl_bad_lines(path, text)
            if bad_lines:
                findings.append(
                    _make_finding(
                        severity="P1",
                        category="logs",
                        module=name,
                        code="BAD_JSONL",
                        message=f"Log file {rel} contains {bad_lines} unreadable JSONL line(s).",
                        evidence_file=rel,
                        normalized_field="jsonl",
                        source=rel,
                        suggested_fix="Repair or drop malformed JSONL lines so the monitor can parse the log safely.",
                    )
                )
            if "Traceback" in text or "traceback" in text.lower():
                findings.append(
                    _make_finding(
                        severity="P0",
                        category="security",
                        module=name,
                        code="RAW_TRACEBACK_LEAK",
                        message=f"Raw traceback text appears in {rel}.",
                        evidence_file=rel,
                        normalized_field="traceback",
                        source=rel,
                        suggested_fix="Sanitize exception output before it reaches logs.",
                    )
                )
            if "/Users/" in text:
                findings.append(
                    _make_finding(
                        severity="P0",
                        category="security",
                        module=name,
                        code="LOCAL_PATH_LEAK",
                        message=f"Local absolute path appears in {rel}.",
                        evidence_file=rel,
                        normalized_field="/Users/",
                        source=rel,
                        suggested_fix="Strip local filesystem paths before persisting or publishing logs.",
                    )
                )
            if re.search(r"(?i)\b(?:token|secret|password|authorization)\b", text):
                findings.append(
                    _make_finding(
                        severity="P0",
                        category="security",
                        module=name,
                        code="SECRET_LITERAL_LEAK",
                        message=f"Potential secret-bearing token appears in {rel}.",
                        evidence_file=rel,
                        normalized_field="secret",
                        source=rel,
                        suggested_fix="Redact token/secret/password values before logging them.",
                    )
                )
        if name == "system_health_daily_report.md":
            latest = _latest_timestamp_from_text(text)
            if latest is not None and (_now_utc() - latest) > timedelta(days=STALE_AFTER_DAYS):
                findings.append(
                    _make_finding(
                        severity="P1",
                        category="health",
                        module="system_health_daily_report",
                        code="HEALTH_REPORT_STALE",
                        message=f"System health report {rel} is stale.",
                        evidence_file=rel,
                        normalized_field="generated_at",
                        source=rel,
                        suggested_fix="Regenerate the health report from the latest logs.",
                    )
                )
            for line in text.splitlines():
                if "status=critical" in line or "status=degraded" in line:
                    severity = "P0" if "status=critical" in line else "P1"
                    findings.append(
                        _make_finding(
                            severity=severity,
                            category="health",
                            module="system_health_daily_report",
                            code="NON_GREEN_HEALTH_STATUS",
                            message=f"Non-green health signal found in {rel}: {line.strip()}",
                            evidence_file=rel,
                            normalized_field="status",
                            source=rel,
                            suggested_fix="Address the underlying system-health issue or annotate the expected non-green state.",
                        )
                    )
                    break
    return findings


def scan_system_health_source(root: Path, logs_dir: Path) -> list[Finding]:
    path = logs_dir / "system_health_daily_report.md"
    if not path.exists():
        return [
            _make_finding(
                severity="P2",
                category="health",
                module="system_health_daily_report",
                code="HEALTH_SOURCE_MISSING",
                message="No system health source was found; cannot assess non-green status.",
                evidence_file=_relative_path(path, root),
                normalized_field="source",
                source="system_health_daily_report.md",
                suggested_fix="Create a system health report source or suppress this expected absence.",
            )
        ]
    return []


def collect_findings(root: Path, logs_dir: Path | None = None) -> list[Finding]:
    logs_root = logs_dir or (root / "logs")
    findings: dict[str, Finding] = {}
    for item in (
        scan_module_registry(root),
        scan_schemas(root),
        scan_configs(root),
        scan_tests(root),
        scan_scripts(root),
        scan_canvas(root),
        scan_logs(root, logs_root),
        scan_system_health_source(root, logs_root),
    ):
        for finding in item:
            _merge_finding(findings, finding)
    return list(findings.values())


def _sort_key(finding: Finding) -> tuple[int, int, int, int, int, str]:
    return (
        SEVERITY_ORDER.get(finding.severity, 99),
        0 if finding.new else 1,
        CATEGORY_WEIGHTS.get(finding.category, CATEGORY_WEIGHTS["other"]),
        -finding.seen_days,
        -finding.occurrence_count,
        finding.dedupe_key,
    )


def _status_from_counts(p0_count: int, p1_count: int) -> str:
    if p0_count > 0:
        return "RED"
    if p1_count > 0:
        return "YELLOW"
    return "GREEN"


def _summarize_findings(findings: list[Finding]) -> dict[str, int]:
    summary = {"p0_count": 0, "p1_count": 0, "p2_count": 0, "total_count": 0}
    for finding in findings:
        if finding.suppressed:
            continue
        summary["total_count"] += 1
        if finding.severity == "P0":
            summary["p0_count"] += 1
        elif finding.severity == "P1":
            summary["p1_count"] += 1
        else:
            summary["p2_count"] += 1
    return summary


def _build_state(findings: list[Finding]) -> dict[str, Any]:
    active_keys = [finding.dedupe_key for finding in findings if not finding.suppressed]
    findings_by_key = {
        finding.dedupe_key: {
            "severity": finding.severity,
            "category": finding.category,
            "module": finding.module,
            "code": finding.code,
            "message": finding.message,
            "evidence_file": finding.evidence_file,
            "normalized_field": finding.normalized_field,
            "suppressed": finding.suppressed,
            "seen_days": finding.seen_days,
            "occurrence_count": finding.occurrence_count,
            "first_seen_at": finding.first_seen_at,
            "last_seen_at": finding.last_seen_at,
        }
        for finding in findings
    }
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "active_dedupe_keys": active_keys,
        "findings_by_key": findings_by_key,
    }


def _delta_vs_prev(current_findings: list[Finding], previous_state: dict[str, Any] | None) -> dict[str, int]:
    if previous_state is None:
        return {"new_count": 0, "resolved_count": 0, "unchanged_count": 0, "suppressed_count": 0}
    prev_active = set((previous_state or {}).get("active_dedupe_keys", []))
    current_active = {finding.dedupe_key for finding in current_findings if not finding.suppressed}
    current_all = {finding.dedupe_key for finding in current_findings}
    return {
        "new_count": len([key for key in current_active if key not in prev_active]),
        "resolved_count": len([key for key in prev_active if key not in current_all]),
        "unchanged_count": len([key for key in current_active if key in prev_active]),
        "suppressed_count": len([finding for finding in current_findings if finding.suppressed]),
    }


def _top_blockers(findings: list[Finding], limit: int = 5) -> list[dict[str, Any]]:
    active = [finding for finding in findings if not finding.suppressed and finding.severity in {"P0", "P1"}]
    active.sort(key=_sort_key)
    return [finding.as_dict() for finding in active[:limit]]


def _render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    delta = report["delta_vs_prev"]
    findings = report["findings"]
    suppressed = [finding for finding in findings if finding["suppressed"]]
    active = [finding for finding in findings if not finding["suppressed"]]

    lines = [
        "# Project Gap Report",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- overall_status: `{report['overall_status']}`",
        "",
        "## Summary",
        "",
        f"- P0: `{summary['p0_count']}`",
        f"- P1: `{summary['p1_count']}`",
        f"- P2: `{summary['p2_count']}`",
        f"- Total: `{summary['total_count']}`",
        "",
        "## Delta vs Prev",
        "",
        f"- new: `{delta['new_count']}`",
        f"- resolved: `{delta['resolved_count']}`",
        f"- unchanged: `{delta['unchanged_count']}`",
        f"- suppressed: `{delta['suppressed_count']}`",
        "",
        "## Top Blockers",
    ]
    if report["top_blockers"]:
        for blocker in report["top_blockers"]:
            lines.append(
                f"- `{blocker['severity']}` `{blocker['category']}` `{blocker['module']}` `{blocker['code']}`: {blocker['message']}"
            )
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Findings",
            "",
            "| severity | category | module | code | message | evidence_file | normalized_field | suppressed | suggested_fix |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for finding in findings:
        lines.append(
            "| {severity} | {category} | {module} | {code} | {message} | {evidence_file} | {normalized_field} | {suppressed} | {suggested_fix} |".format(
                severity=finding["severity"],
                category=finding["category"],
                module=finding["module"],
                code=finding["code"],
                message=finding["message"].replace("|", "\\|"),
                evidence_file=finding["evidence_file"],
                normalized_field=finding["normalized_field"],
                suppressed=str(finding["suppressed"]).lower(),
                suggested_fix=finding["suggested_fix"].replace("|", "\\|"),
            )
        )
    lines.extend(
        [
            "",
            "## Suppressed Findings Summary",
            "",
            f"- Suppressed count: `{len(suppressed)}`",
        ]
    )
    if suppressed:
        for finding in suppressed[:10]:
            lines.append(f"- `{finding['dedupe_key']}`")
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Suggested Fixes",
            "",
        ]
    )
    if active:
        for finding in active[:10]:
            lines.append(f"- `{finding['dedupe_key']}` -> {finding['suggested_fix']}")
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def run_project_gap_monitor(
    *,
    root: Path = ROOT,
    logs_dir: Path | None = None,
    allowlist_path: Path | None = None,
    state_path: Path | None = None,
    report_json_path: Path | None = None,
    report_md_path: Path | None = None,
) -> dict[str, Any]:
    root = Path(root)
    logs_dir = Path(logs_dir) if logs_dir else root / "logs"
    state_path = Path(state_path) if state_path else logs_dir / "project_gap_state.json"
    report_json_path = Path(report_json_path) if report_json_path else logs_dir / "project_gap_report.json"
    report_md_path = Path(report_md_path) if report_md_path else logs_dir / "project_gap_report.md"
    allowlist_path = Path(allowlist_path) if allowlist_path else root / "configs" / "project_gap_monitor_allowlist.yaml"

    previous_state = _load_previous_state(state_path)
    findings = collect_findings(root, logs_dir)
    rules = _load_allowlist(allowlist_path)
    _apply_allowlist({finding.dedupe_key: finding for finding in findings}, rules)
    findings_by_key = {finding.dedupe_key: finding for finding in findings}
    _mark_history(findings_by_key, previous_state)
    ordered = sorted(findings_by_key.values(), key=_sort_key)
    summary = _summarize_findings(ordered)
    status = _status_from_counts(summary["p0_count"], summary["p1_count"])
    delta = _delta_vs_prev(ordered, previous_state)
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "overall_status": status,
        "summary": summary,
        "delta_vs_prev": delta,
        "top_blockers": _top_blockers(ordered),
        "findings": [finding.as_dict() for finding in ordered],
    }
    state = _build_state(ordered)

    report_json_path.parent.mkdir(parents=True, exist_ok=True)
    report_md_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    report_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_md_path.write_text(_render_markdown(report), encoding="utf-8")
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Project Gap Monitor (read-only gap discovery)")
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root to scan.")
    parser.add_argument("--logs-dir", type=Path, default=None, help="Logs directory to scan and write outputs into.")
    parser.add_argument("--state-path", type=Path, default=None, help="Previous state JSON path.")
    parser.add_argument("--report-json", type=Path, default=None, help="Report JSON output path.")
    parser.add_argument("--report-md", type=Path, default=None, help="Report Markdown output path.")
    parser.add_argument("--allowlist", type=Path, default=None, help="YAML allowlist path.")
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    report = run_project_gap_monitor(
        root=args.root,
        logs_dir=args.logs_dir,
        allowlist_path=args.allowlist,
        state_path=args.state_path,
        report_json_path=args.report_json,
        report_md_path=args.report_md,
    )
    print(json.dumps(
        {
            "schema_version": report["schema_version"],
            "generated_at": report["generated_at"],
            "overall_status": report["overall_status"],
            "summary": report["summary"],
            "delta_vs_prev": report["delta_vs_prev"],
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
