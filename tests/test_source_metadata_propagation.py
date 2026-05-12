"""Static contract checks for the Stage8A PR-2 source metadata groundwork.

Refs #142 (Stage8A-Impl-2A)
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PHASE0_FREEZE_PATH = REPO_ROOT / "docs" / "stage8" / "news_to_accurate_stock_pool_phase0_interface_freeze.md"


def test_source_metadata_required_fields_are_frozen() -> None:
    """Phase 0 docs must keep required source metadata fields explicit."""
    text = PHASE0_FREEZE_PATH.read_text(encoding="utf-8")

    assert "Source Metadata Propagation Contract" in text
    assert "- source" in text
    assert "- role" in text
    assert "- relation" in text
    assert "- event_id" in text


def test_source_metadata_propagation_rules_are_reviewable() -> None:
    """Source metadata propagation must stay deterministic and non-inventive."""
    text = PHASE0_FREEZE_PATH.read_text(encoding="utf-8")

    assert "missing source metadata must not be converted into a valid merged candidate" in text
    assert "source metadata must remain consistent across the chain" in text
    assert "same-ticker multi-source merging must preserve provenance" in text
