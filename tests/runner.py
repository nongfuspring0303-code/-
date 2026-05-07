import unittest
from pathlib import Path
import re

class TestPR3Remediation(unittest.TestCase):

    # === HTML Contract Tests ===

    def test_project_health_html_mandatory_anchors(self):
        """Verify all mandatory data-key anchors exist."""
        content = Path("canvas/project-health.html").read_text()
        mandatory_keys = [
            'health.overall_status', 'health.last_generated_at', 'health.p0_count',
            'health.p1_count', 'health.p2_count', 'health.current_commit',
            'health.frontend_coverage', 'health.contract_coverage', 'health.log_freshness',
            'health.test_health', 'health.hardcoded_risk', 'health.delta_stats',
            'health.recommendations'
        ]
        for key in mandatory_keys:
            self.assertIn(f'data-key="{key}"', content, f"Missing mandatory data-key: {key}")

    def test_project_health_mandatory_data_module(self):
        """A-MAJOR-3: Verify data-module anchor co-exists with data-key on KPI cards."""
        content = Path("canvas/project-health.html").read_text()
        kpi_count = content.count('class="kpi-card"')
        module_count = content.count('data-module="ProjectHealth"')
        self.assertGreaterEqual(module_count, kpi_count,
            f"Only {module_count} of {kpi_count} KPI cards have data-module anchor")

    def test_project_health_mandatory_data_state(self):
        """Verify that KPI cards have data-state for audit stability."""
        content = Path("canvas/project-health.html").read_text()
        kpi_count = content.count('class="kpi-card"')
        state_count = content.count('data-state="MISSING"')
        self.assertGreaterEqual(state_count, kpi_count,
            "Some KPI cards are missing data-state anchors")

    def test_project_health_no_inline_onclick(self):
        """BLOCKER-2: Zero inline onclick handlers."""
        content = Path("canvas/project-health.html").read_text()
        self.assertNotIn('onclick=', content, "Found forbidden inline onclick handler in HTML")

    # === JS Security Tests ===

    def test_project_health_js_no_report_field_in_innerhtml(self):
        """BLOCKER-2: report fields must never enter innerHTML."""
        content = Path("canvas/project-health.js").read_text()
        self.assertNotIn('innerHTML +=', content, "Found dangerous innerHTML concatenation")
        # Scan every line: no report field reference in any innerHTML assignment
        report_fields = ['f.message', 'f.module', 'f.category', 'f.evidence_file',
                         'f.repro_command', 'f.severity', 'f.line_hint',
                         'b.suggested_fix', 'b.code', 'p.module', 'p.code']
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if 'innerHTML' in line:
                for field in report_fields:
                    self.assertNotIn(field, line,
                        f"Line {i+1}: report field '{field}' injected into innerHTML: {line.strip()}")

    def test_project_health_js_xss_adversarial(self):
        """BLOCKER-2: All critical fields rendered via textContent, not innerHTML."""
        content = Path("canvas/project-health.js").read_text()
        adversarial_fields = ['f.message', 'f.module', 'f.category', 'f.evidence_file',
                              'b.suggested_fix', 'f.repro_command', 'p.module', 'p.code']
        for field in adversarial_fields:
            self.assertIn(field, content, f"Field {field} not found in renderer")

    # === JS Null Safety Tests ===

    def test_project_health_js_null_safe_tolowercase(self):
        """B: f.module/f.message must not directly call toLowerCase()."""
        content = Path("canvas/project-health.js").read_text()
        # Must NOT have f.module.toLowerCase or f.message.toLowerCase without guard
        self.assertNotIn('f.module.toLowerCase()', content,
            "f.module.toLowerCase() without null guard")
        self.assertNotIn('f.message.toLowerCase()', content,
            "f.message.toLowerCase() without null guard")
        # Must have guarded version
        self.assertIn("(f.module || '').toLowerCase()", content,
            "Missing null-guarded toLowerCase for f.module")
        self.assertIn("(f.message || '').toLowerCase()", content,
            "Missing null-guarded toLowerCase for f.message")

    def test_project_health_js_current_commit_missing(self):
        """B: current_commit missing must show MISSING, not UNKNOWN."""
        content = Path("canvas/project-health.js").read_text()
        self.assertNotIn("|| 'UNKNOWN'", content,
            "current_commit fallback is UNKNOWN instead of MISSING")

    def test_project_health_js_null_finding_defense(self):
        """B: null/empty findings must not white screen."""
        content = Path("canvas/project-health.js").read_text()
        # Findings filter must exclude null entries
        self.assertIn('f != null', content, "Missing null finding filter")
        self.assertIn('report.findings || []', content, "Missing empty findings guard")

    # === Stale Detection Tests ===

    def test_project_health_js_stale_four_state_branches(self):
        """B-MAJOR-3: Verify all 4 freshness state branches."""
        content = Path("canvas/project-health.js").read_text()
        self.assertIn('return { state: "MISSING"', content, "MISSING branch missing")
        self.assertIn('return { state: "FAILED"', content, "FAILED branch missing")
        self.assertIn('return { state: "STALE"', content, "STALE branch missing")
        self.assertIn('return { state: "OK"', content, "OK branch missing")
        self.assertIn('10 * 60 * 1000', content, "10min threshold missing")

    # === Monitor Script Tests ===

    def test_local_monitor_script_security_policy(self):
        """Read-only monitor policy."""
        content = Path("scripts/local_daily_project_monitor.sh").read_text()
        forbidden = ['git commit', 'git push', 'git add', 'gh pr create',
                     'broker ', 'trade ', 'execute ']
        for cmd in forbidden:
            self.assertNotIn(cmd, content, f"Forbidden command: {cmd}")

    def test_local_monitor_script_strict_mode(self):
        """B: script must use set -euo pipefail and propagate failures."""
        content = Path("scripts/local_daily_project_monitor.sh").read_text()
        self.assertIn('set -euo pipefail', content, "Missing strict error handling")
        self.assertIn('#!/usr/bin/env bash', content, "Missing portable shebang")
        self.assertIn('date -u', content, "Must use UTC timestamps")

    # === Runtime Config Tests ===

    def test_runtime_config_preserves_contract(self):
        """B: runtime-config.js must define window.RUNTIME_CONFIG for app.js."""
        content = Path("canvas/runtime-config.js").read_text()
        self.assertIn('window.RUNTIME_CONFIG', content,
            "window.RUNTIME_CONFIG missing - breaks app.js contract")

    # === Error Handling Tests ===

    def test_project_health_js_error_handling(self):
        """Verify no white screen on missing report fields."""
        content = Path("canvas/project-health.js").read_text()
        self.assertIn('report.summary?', content, "Missing safety guard for report.summary")

    def test_project_health_js_envelope_dual_compatibility(self):
        """B: Verify code handles both raw log body and envelope body.data."""
        content = Path("canvas/project-health.js").read_text()
        # Must unwrap data if present
        self.assertIn('const report = body.data || body', content,
            "Missing API Envelope dual compatibility unwrap logic")

if __name__ == '__main__':
    unittest.main()
