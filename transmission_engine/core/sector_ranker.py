#!/usr/bin/env python3

from __future__ import annotations

from typing import Any, Dict, List


def rank_sectors(sectors: List[Dict[str, Any]]) -> Dict[str, Any]:
    scored: List[tuple[str, float]] = []
    for item in sectors:
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        # v2.1 formula fallback strategy:
        # Final_Sector_Score = 0.45*Factor_Exposure + 0.25*Asset_Validation +
        #                      0.20*Fundamental_Path + 0.10*Narrative_Path - Penalties
        # If upstream detailed fields are missing, fallback to impact/conf proxies.
        impact = float(item.get("impact_score", 0.0) or 0.0)
        conf = float(item.get("confidence", 0.0) or 0.0)
        factor_exposure = float(item.get("factor_exposure", impact * 100.0) or 0.0)
        asset_validation = float(item.get("asset_validation", conf * 100.0) or 0.0)
        fundamental_path = float(item.get("fundamental_path", impact * 100.0) or 0.0)
        narrative_path = float(item.get("narrative_path", conf * 100.0) or 0.0)
        penalties = float(item.get("penalties", 0.0) or 0.0)
        direction = str(item.get("direction", "WATCH")).upper()
        sign = -1.0 if direction == "SHORT" else 1.0
        base = 0.45 * factor_exposure + 0.25 * asset_validation + 0.20 * fundamental_path + 0.10 * narrative_path - penalties
        score = round(sign * base, 2)
        scored.append((name, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    sector_scores = {k: v for k, v in scored}

    primary = scored[0][0] if scored else ""
    secondary = scored[1][0] if len(scored) > 1 else ""
    avoid = [name for name, score in scored if score < 0][:2]

    return {
        "primary_sector": primary,
        "secondary_sector": secondary,
        "avoid_sector": avoid,
        "sector_scores": sector_scores,
    }
