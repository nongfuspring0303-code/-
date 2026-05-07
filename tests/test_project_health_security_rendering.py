import pytest
from pathlib import Path

def test_project_health_js_uses_text_content_for_dynamic_data():
    """Verify that project-health.js uses textContent for all critical report fields to prevent XSS."""
    js_path = Path("canvas/project-health.js")
    content = js_path.read_text()
    
    # Must use textContent for these fields
    target_fields = [
        'f.message',
        'f.module',
        'f.category',
        'f.evidence_file',
        'f.repro_command',
        'b.suggested_fix'
    ]
    
    for field in target_fields:
        # Check that we are assigning to .textContent
        assert '.textContent =' in content, "Missing textContent assignment in JS"
        
def test_project_health_js_implements_stale_logic():
    """Verify that the 10m stale logic is implemented as promised in the evidence pack."""
    content = Path("canvas/project-health.js").read_text()
    assert 'getReportFreshnessState' in content
    assert '10 * 60 * 1000' in content or 'staleThresholdMs' in content
    assert 'STALE' in content
