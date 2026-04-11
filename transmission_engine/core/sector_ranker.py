#!/usr/bin/env python3

from __future__ import annotations

from typing import Any, Dict, List


def rank_sectors(sectors: List[Dict[str, Any]]) -> Dict[str, Any]:
    scored: List[tuple[str, float]] = []
    for item in sectors:
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        impact = float(item.get("impact_score", 0.0) or 0.0)
        conf = float(item.get("confidence", 0.0) or 0.0)
        direction = str(item.get("direction", "WATCH")).upper()
        sign = -1.0 if direction == "SHORT" else 1.0
        score = round(sign * (0.6 * impact + 0.4 * conf) * 100.0, 2)
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
