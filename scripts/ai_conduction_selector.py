#!/usr/bin/env python3
"""Semantic-first conduction chain selector with rules fallback metadata."""

from __future__ import annotations

from typing import Dict, Optional


class AIConductionSelector:
    def __init__(self, min_confidence: int = 70):
        self.min_confidence = max(0, min(100, int(min_confidence)))

    def choose_chain(
        self,
        semantic_output: Dict[str, object],
        rule_selected_chain: Optional[str],
    ) -> Dict[str, object]:
        semantic_chain = str(semantic_output.get("recommended_chain", "") or "")
        try:
            semantic_conf = int(float(semantic_output.get("confidence", 0) or 0))
        except (TypeError, ValueError):
            semantic_conf = 0
        semantic_conf = max(0, min(100, semantic_conf))

        if semantic_chain and semantic_conf >= self.min_confidence:
            return {
                "chain_id": semantic_chain,
                "selection_source": "semantic",
                "selection_confidence": semantic_conf,
            }

        return {
            "chain_id": rule_selected_chain or "",
            "selection_source": "rules",
            "selection_confidence": semantic_conf,
            "fallback_reason": semantic_output.get("fallback_reason", "semantic_low_confidence"),
        }
