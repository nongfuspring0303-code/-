#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import yaml
from pathlib import Path
from typing import Any, Dict, List, Tuple

from conduction_mapper import ConductionMapper


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _key(row: Dict[str, Any]) -> Tuple[str, str]:
    return (str(row.get("trace_id", "")), str(row.get("event_hash", "")))


def _infer_category(trace_id: str) -> str:
    parts = trace_id.split("-")
    if len(parts) >= 2 and parts[1]:
        return str(parts[1]).upper()
    return "E"


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild round6 rerun scorecard by replaying ConductionMapper on raw ingest headlines.")
    parser.add_argument("--base-scorecard", type=Path, default=Path("reports/ai_mapping_regression_eval/trace_scorecard_vnew_round5_rerun_with_buckets.jsonl"))
    parser.add_argument("--raw-news", type=Path, default=Path("logs/raw_news_ingest.jsonl"))
    parser.add_argument("--out-scorecard", type=Path, default=Path("reports/ai_mapping_regression_eval/trace_scorecard_vnew_round6_rerun_with_buckets.jsonl"))
    args = parser.parse_args()

    base_rows = _read_jsonl(args.base_scorecard)
    raw_rows = _read_jsonl(args.raw_news)
    raw_by_key = {_key(r): r for r in raw_rows}
    mapper = ConductionMapper()

    out_rows: List[Dict[str, Any]] = []
    for row in base_rows:
        merged = dict(row)
        raw = raw_by_key.get(_key(row))
        if not raw:
            out_rows.append(merged)
            continue
        headline = str(raw.get("headline", "") or "").strip()
        if not headline:
            out_rows.append(merged)
            continue
        semantic_event_type = str(row.get("semantic_event_type", "")).strip().lower()
        semantic_output = {
            "event_type": semantic_event_type,
            "confidence": float(row.get("ai_confidence", 70.0) or 70.0),
            "recommended_stocks": row.get("ai_recommended_stocks", []),
            "entities": [],
            "transmission_candidates": [],
        }
        sector_weight_view = mapper._build_sector_weight_view(  # noqa: SLF001
            semantic_event_type=semantic_event_type,
            subtype=mapper._extract_subtype(semantic_event_type, headline, "", semantic_output),  # noqa: SLF001
            headline=headline,
            summary="",
            semantic_output=semantic_output,
            sector_impacts=[],
        )
        sector_weights = sector_weight_view.get("sector_weights", {}) if isinstance(sector_weight_view, dict) else {}
        sector_impacts = [
            {"sector": k, "direction": "watch", "impact_score": v}
            for k, v in sorted((sector_weights or {}).items(), key=lambda kv: (-float(kv[1]), kv[0]))[:3]
            if str(k).strip()
        ]
        pool_candidates = mapper._build_ticker_pool_candidates(  # noqa: SLF001
            semantic_output=semantic_output,
            subtype=mapper._extract_subtype(semantic_event_type, headline, "", semantic_output),  # noqa: SLF001
            sector_weight_view=sector_weight_view,
            sector_impacts=sector_impacts,
        )
        rec_buckets = mapper._split_recommendation_buckets(  # noqa: SLF001
            semantic_event_type=semantic_event_type,
            headline=headline,
            candidates=pool_candidates,
        )
        stock_candidates = rec_buckets.get("recommended", []) + rec_buckets.get("watchlist", [])

        merged["semantic_event_type"] = semantic_event_type
        merged["sector_candidates"] = [str((x or {}).get("sector", "")).strip() for x in sector_impacts if isinstance(x, dict) and str((x or {}).get("sector", "")).strip()]
        merged["ticker_candidates"] = [str((x or {}).get("symbol", "")).strip().upper() for x in stock_candidates if isinstance(x, dict) and str((x or {}).get("symbol", "")).strip()]
        merged["stock_candidates"] = stock_candidates
        merged["stock_recommendation_buckets"] = rec_buckets
        merged["primary_sector"] = str(sector_weight_view.get("primary_sector", ""))
        merged["sector_weight_quality_score"] = float(sector_weight_view.get("weight_quality_score", row.get("sector_weight_quality_score", 0.0)) or 0.0)

        # Compute ticker_quality_score from truth pool
        _script_root = Path(__file__).resolve().parent.parent
        ticker_truth_pool = set()
        pool_path = _script_root / "configs" / "premium_stock_pool.yaml"
        pool_cfg = yaml.safe_load(pool_path.read_text()) if pool_path.exists() else {}
        for s in pool_cfg.get("stocks", []):
            sym = str(s.get("symbol", "")).strip().upper()
            if sym:
                ticker_truth_pool.add(sym)
        ticker_candidates_list = [str(t).strip().upper() for t in merged.get("ticker_candidates", []) if str(t).strip()]
        ticker_truth_source_hit = sum(1 for t in ticker_candidates_list if t in ticker_truth_pool)
        ticker_truth_source_miss = sum(1 for t in ticker_candidates_list if t not in ticker_truth_pool)
        tq = 100.0
        if ticker_truth_source_miss > 0:
            tq = 0.0
        if ticker_truth_source_hit == 0:
            tq -= 40.0
        stock_cands = merged.get("stock_candidates", [])
        if not stock_cands:
            tq -= 20.0
        tq = max(0.0, min(100.0, tq))
        merged["ticker_quality_score"] = tq
        merged["ticker_truth_source_hit"] = ticker_truth_source_hit
        merged["ticker_truth_source_miss"] = ticker_truth_source_miss

        merged["mapping_source"] = "round6_offline_replay"
        out_rows.append(merged)

    args.out_scorecard.parent.mkdir(parents=True, exist_ok=True)
    args.out_scorecard.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in out_rows) + "\n", encoding="utf-8")
    print(f"wrote {len(out_rows)} rows -> {args.out_scorecard}")


if __name__ == "__main__":
    main()
