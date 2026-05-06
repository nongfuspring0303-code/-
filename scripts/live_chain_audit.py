#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _collect_trace_view(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    traces: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        typ = row.get("type")
        payload = row.get("payload") or {}
        trace_id = row.get("trace_id") or payload.get("trace_id")
        if not trace_id:
            continue
        ts = _parse_dt(row.get("timestamp")) or _parse_dt(payload.get("timestamp")) or _parse_dt(payload.get("news_timestamp"))
        item = traces.setdefault(
            trace_id,
            {"event": {}, "sectors": [], "opportunities": [], "first_ts": None, "last_ts": None},
        )
        if ts is not None:
            if item["first_ts"] is None or ts < item["first_ts"]:
                item["first_ts"] = ts
            if item["last_ts"] is None or ts > item["last_ts"]:
                item["last_ts"] = ts

        if typ == "event_update":
            for key in ("headline", "headline_cn", "ai_verdict", "ai_reason", "source", "news_timestamp"):
                val = payload.get(key)
                if val not in (None, ""):
                    item["event"][key] = val
        elif typ == "sector_update":
            sectors = payload.get("sectors") or payload.get("sector_impacts") or payload.get("sectorImpacts") or []
            for sec in sectors:
                if not isinstance(sec, dict):
                    continue
                item["sectors"].append(
                    {
                        "sector": sec.get("name") or sec.get("sector"),
                        "direction": sec.get("direction"),
                        "impact_score": sec.get("impact_score", 0.0),
                        "confidence": sec.get("confidence"),
                    }
                )
        elif typ == "opportunity_update":
            for opp in payload.get("opportunities") or []:
                if not isinstance(opp, dict):
                    continue
                item["opportunities"].append(
                    {
                        "trace_id": opp.get("trace_id"),
                        "request_id": opp.get("request_id"),
                        "batch_id": opp.get("batch_id"),
                        "symbol": opp.get("symbol"),
                        "sector": opp.get("sector"),
                        "action": opp.get("final_action") or opp.get("signal"),
                        "confidence": opp.get("confidence"),
                        "outer_trace_id": trace_id,
                        "outer_request_id": payload.get("request_id"),
                        "outer_batch_id": payload.get("batch_id"),
                    }
                )
    return traces


def _dedup_dict_rows(rows: List[Dict[str, Any]], keys: List[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for row in rows:
        sig = tuple(row.get(k) for k in keys)
        if sig in seen:
            continue
        seen.add(sig)
        out.append(row)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Live chain audit for hit->sector->opportunity quality")
    parser.add_argument("--log", type=Path, default=Path("logs/event_bus_live.jsonl"))
    parser.add_argument("--window-start", type=str, default="2026-05-06T00:00:00Z")
    parser.add_argument("--anchor", type=str, default="2026-05-07T01:51:38Z")
    parser.add_argument("--out-dir", type=Path, default=Path("reports/manual_check"))
    args = parser.parse_args()

    window_start = _parse_dt(args.window_start)
    anchor = _parse_dt(args.anchor)
    if window_start is None or anchor is None:
        raise SystemExit("invalid --window-start or --anchor")

    rows = _read_jsonl(args.log)
    traces = _collect_trace_view(rows)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    details: List[Dict[str, Any]] = []
    for trace_id, item in traces.items():
        ts = item["first_ts"] or item["last_ts"]
        if ts is None or ts < window_start:
            continue
        verdict = str(item["event"].get("ai_verdict", "")).lower()
        if verdict != "hit":
            continue
        sectors = _dedup_dict_rows(
            [s for s in item["sectors"] if str(s.get("sector", "")).strip()],
            ["sector", "direction", "impact_score"],
        )
        opps = _dedup_dict_rows(
            [o for o in item["opportunities"] if str(o.get("symbol", "")).strip()],
            ["symbol", "sector", "action"],
        )
        if not sectors or not opps:
            continue
        secset = {s.get("sector") for s in sectors}
        details.append(
            {
                "trace_id": trace_id,
                "first_ts_utc": ts.isoformat().replace("+00:00", "Z"),
                "headline": item["event"].get("headline") or item["event"].get("headline_cn") or "",
                "ai_reason": item["event"].get("ai_reason") or "",
                "sectors": sectors,
                "opportunities": opps,
                "stock_sector_consistent": all(o.get("sector") in secset for o in opps),
            }
        )
    details.sort(key=lambda x: x["first_ts_utc"])

    consistency_rows: List[Dict[str, Any]] = []
    for trace_id, item in traces.items():
        for opp in item["opportunities"]:
            if not str(opp.get("outer_trace_id", "")).startswith("evt_live_"):
                continue
            ts = item["last_ts"] or item["first_ts"]
            if ts is None or ts < anchor:
                continue
            mismatch: List[str] = []
            if opp.get("trace_id") != opp.get("outer_trace_id"):
                mismatch.append("trace_id")
            if opp.get("request_id") != opp.get("outer_request_id"):
                mismatch.append("request_id")
            if opp.get("batch_id") != opp.get("outer_batch_id"):
                mismatch.append("batch_id")
            consistency_rows.append(
                {
                    "trace_id": opp.get("outer_trace_id"),
                    "symbol": opp.get("symbol"),
                    "mismatch": mismatch,
                    "timestamp_utc": ts.isoformat().replace("+00:00", "Z"),
                }
            )

    primary_rows: List[Dict[str, Any]] = []
    for trace_id, item in traces.items():
        ts = item["last_ts"] or item["first_ts"]
        if ts is None or ts < anchor:
            continue
        if not str(trace_id).startswith("evt_live_"):
            continue
        sectors = [s for s in item["sectors"] if str(s.get("sector", "")).strip()]
        opps = [o for o in item["opportunities"] if str(o.get("symbol", "")).strip()]
        if not sectors or not opps:
            continue
        primary = max(sectors, key=lambda x: float(x.get("impact_score") or 0.0)).get("sector")
        opp_sector_set = sorted({str(o.get("sector")) for o in opps if o.get("sector")})
        primary_rows.append(
            {
                "trace_id": trace_id,
                "primary_sector": primary,
                "opportunity_sectors": opp_sector_set,
                "primary_sector_only_pass": all(o.get("sector") == primary for o in opps),
                "timestamp_utc": ts.isoformat().replace("+00:00", "Z"),
            }
        )

    summary = {
        "window_start_utc": window_start.isoformat().replace("+00:00", "Z"),
        "window_end_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "anchor_utc": anchor.isoformat().replace("+00:00", "Z"),
        "hit_with_sector_and_stock_count": len(details),
        "stock_sector_consistency_rate": round(
            sum(1 for row in details if row["stock_sector_consistent"]) / len(details), 4
        )
        if details
        else None,
        "opportunity_field_consistency_rows": len(consistency_rows),
        "opportunity_field_consistency_mismatch_rows": sum(1 for row in consistency_rows if row["mismatch"]),
        "opportunity_field_consistency_match_rate": round(
            sum(1 for row in consistency_rows if not row["mismatch"]) / len(consistency_rows), 4
        )
        if consistency_rows
        else None,
        "primary_sector_only_eligible_traces": len(primary_rows),
        "primary_sector_only_pass_rate": round(
            sum(1 for row in primary_rows if row["primary_sector_only_pass"]) / len(primary_rows), 4
        )
        if primary_rows
        else None,
    }

    out_json = args.out_dir / "live_chain_audit.json"
    out_md = args.out_dir / "live_chain_audit.md"
    out_json.write_text(
        json.dumps(
            {
                "summary": summary,
                "details": details,
                "opportunity_field_consistency": consistency_rows,
                "primary_sector_only": primary_rows,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    md_lines = [
        "# Live Chain Audit",
        "",
        f"- window_start_utc: `{summary['window_start_utc']}`",
        f"- anchor_utc: `{summary['anchor_utc']}`",
        f"- hit_with_sector_and_stock_count: `{summary['hit_with_sector_and_stock_count']}`",
        f"- stock_sector_consistency_rate: `{summary['stock_sector_consistency_rate']}`",
        f"- opportunity_field_consistency_match_rate: `{summary['opportunity_field_consistency_match_rate']}`",
        f"- primary_sector_only_pass_rate: `{summary['primary_sector_only_pass_rate']}`",
        "",
        "## Primary Sector Only",
        "",
        "| trace_id | primary_sector | opportunity_sectors | pass |",
        "|---|---|---|---|",
    ]
    for row in primary_rows:
        md_lines.append(
            f"| {row['trace_id']} | {row['primary_sector']} | {','.join(row['opportunity_sectors'])} | {row['primary_sector_only_pass']} |"
        )
    out_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(f"OK: wrote {out_json}")
    print(
        "summary:",
        json.dumps(
            {
                "hit_with_sector_and_stock_count": summary["hit_with_sector_and_stock_count"],
                "opportunity_field_consistency_match_rate": summary["opportunity_field_consistency_match_rate"],
                "primary_sector_only_pass_rate": summary["primary_sector_only_pass_rate"],
            },
            ensure_ascii=False,
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
