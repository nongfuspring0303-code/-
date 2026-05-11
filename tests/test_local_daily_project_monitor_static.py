import pytest
from pathlib import Path

def test_local_monitor_script_security_policy():
    """Verify that local_daily_project_monitor.sh does not contain forbidden mutation commands."""
    script_path = Path("scripts/local_daily_project_monitor.sh")
    assert script_path.exists()
    content = script_path.read_text()

    forbidden_commands = [
        'git commit',
        'git push',
        'git add',
        'gh pr create',
        'gh pr merge',
        'broker execute',
        'trade execute'
    ]

    for cmd in forbidden_commands:
        assert cmd not in content, f"Forbidden mutation command found in local monitor: {cmd}"

def test_local_monitor_script_read_only_checks():
    """Verify that the script correctly calls the monitor and redirects to logs."""
    content = Path("scripts/local_daily_project_monitor.sh").read_text()
    assert 'python3' in content
    assert 'project_gap_monitor.py' in content
    assert 'logs/local_project_monitor.log' in content


def test_runtime_artifact_ignore_rules_cover_project_gap_monitor_outputs():
    """Verify that the repo ignores the monitor-generated runtime artifacts."""
    gitignore = Path(".gitignore").read_text()
    expected_coverage = [
        "logs/project_gap_report.md",
        "logs/*.json",
        "logs/*.jsonl",
        "logs/*.log",
    ]

    for entry in expected_coverage:
        assert entry in gitignore, f"Missing ignore rule: {entry}"


def test_local_monitor_script_cleans_project_gap_report_artifacts():
    """Verify that the local monitor removes project gap report artifacts on exit."""
    content = Path("scripts/local_daily_project_monitor.sh").read_text()
    expected_paths = [
        'logs/project_gap_report.json',
        'logs/project_gap_report.md',
        'logs/project_gap_state.json',
    ]

    assert 'trap cleanup_runtime_artifacts EXIT' in content
    for path in expected_paths:
        assert path in content, f"Missing cleanup path: {path}"
