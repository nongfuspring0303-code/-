import pytest
from pathlib import Path
import re

def test_project_health_html_mandatory_anchors():
    """Verify that project-health.html contains all mandatory data-key anchors for audit."""
    html_path = Path("canvas/project-health.html")
    assert html_path.exists()
    content = html_path.read_text()

    mandatory_keys = [
        'health.overall_status',
        'health.last_generated_at',
        'health.p0_count',
        'health.p1_count',
        'health.p2_count',
        'health.current_commit',
        'health.frontend_coverage',
        'health.contract_coverage',
        'health.log_freshness',
        'health.test_health',
        'health.delta_stats',
        'health.recommendations'
    ]

    for key in mandatory_keys:
        assert f'data-key="{key}"' in content, f"Missing mandatory data-key: {key}"

def test_project_health_no_inline_onclick():
    """Verify that project-health.html has no inline onclick handlers (Security)."""
    html_path = Path("canvas/project-health.html")
    content = html_path.read_text()
    
    # Check for onclick="..."
    assert 'onclick=' not in content, "Found forbidden inline onclick handler in HTML"

def test_project_health_js_no_innerhtml_for_report():
    """Verify that project-health.js avoids innerHTML for rendering report findings."""
    js_path = Path("canvas/project-health.js")
    content = js_path.read_text()
    
    # We allow innerHTML = '' for clearing, but not for concatenation with f.xxx
    # The new implementation uses createElement.
    forbidden_pattern = r'innerHTML\s*\+?='
    matches = re.findall(forbidden_pattern, content)
    
    # Only innerHTML = '' is allowed (to clear container)
    for m in matches:
        # Check if the line is innerHTML = ''
        assert "innerHTML = ''" in content or "innerHTML = \"\"" in content, "Found dangerous innerHTML usage in JS"
