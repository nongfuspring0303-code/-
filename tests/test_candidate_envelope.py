"""Static contract checks for the Stage8A PR-2 CandidateEnvelope groundwork.

Refs #142 (Stage8A-Impl-2A)
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PHASE0_FREEZE_PATH = REPO_ROOT / "docs" / "stage8" / "news_to_accurate_stock_pool_phase0_interface_freeze.md"


def test_candidate_envelope_phase0_contract_is_frozen() -> None:
    """Phase 0 docs must keep CandidateEnvelope explicitly frozen before runtime lands."""
    text = PHASE0_FREEZE_PATH.read_text(encoding="utf-8")

    assert "`CandidateEnvelope`" in text
    assert "stable candidate identity" in text
    assert "stable ticker identity" in text
    assert "source and role provenance" in text
    assert "relation evidence required for peer-derived candidates" in text
    assert "event linkage metadata" in text
    assert "deterministic ordering semantics for review and replay" in text


def test_candidate_envelope_failure_behavior_is_explicit() -> None:
    """CandidateEnvelope must fail closed when critical provenance is missing."""
    text = PHASE0_FREEZE_PATH.read_text(encoding="utf-8")

    assert "missing critical fields must not silently produce a valid candidate" in text
    assert "unknown or partial candidates must remain explicitly non-final until resolved" in text
    assert "a candidate without required provenance must be rejected or downgraded with a reason" in text
