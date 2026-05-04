#!/usr/bin/env python3
"""Run regression evaluation for AI mapping pipeline (v_prev vs v_new)."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml


@dataclass
class LabelRow:
    sample_id: str
    trace_id: str
    event_hash: str
    logged_at: str
    event_type_expected: str
    sectors_expected: List[str]
    tickers_expected: List[str]
    tier: str


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            rows.append(json.loads(s))
    return rows


def _read_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        if v is None:
            return default
        return int(v)
    except (TypeError, ValueError):
        return default


def _norm_token(s: str) -> str:
    return str(s or "").strip().lower()


def _norm_list(values: Iterable[Any]) -> List[str]:
    return [str(v).strip() for v in values if str(v).strip()]


def _row_key(trace_id: str, event_hash: str, logged_at: str = "") -> str:
    return f"{str(trace_id).strip()}::{str(event_hash).strip()}::{str(logged_at).strip()}".strip(":")


def _scorecard_key(row: Dict[str, Any]) -> str:
    return _row_key(
        str(row.get("trace_id", "")),
        str(row.get("event_hash", "")),
        str(row.get("logged_at", "")),
    )


def _scorecard_fallback_key(row: Dict[str, Any]) -> str:
    return _row_key(
        str(row.get("trace_id", "")),
        str(row.get("event_hash", "")),
        "",
    )


def _load_labels(labels_yaml: Path) -> Tuple[Dict[str, LabelRow], List[str]]:
    payload = _read_yaml(labels_yaml)
    samples = payload.get("samples", [])
    by_key: Dict[str, LabelRow] = {}
    warnings: List[str] = []
    if not isinstance(samples, list):
        return by_key, ["labels_file.samples is not a list"]
    for idx, item in enumerate(samples):
        if not isinstance(item, dict):
            warnings.append(f"invalid label row at index={idx}")
            continue
        trace_id = str(item.get("trace_id", "")).strip()
        event_hash = str(item.get("event_hash", "")).strip()
        logged_at = str(item.get("logged_at", "")).strip()
        if not trace_id:
            warnings.append(f"missing trace_id at index={idx}")
            continue
        if not event_hash:
            warnings.append(f"missing event_hash at index={idx}")
            continue
        row = LabelRow(
            sample_id=str(item.get("sample_id", "")).strip() or f"row_{idx}",
            trace_id=trace_id,
            event_hash=event_hash,
            logged_at=logged_at,
            event_type_expected=str(item.get("event_type_expected", "")).strip(),
            sectors_expected=_norm_list(item.get("sectors_expected", []) or []),
            tickers_expected=[_norm_token(x) for x in _norm_list(item.get("tickers_expected", []) or [])],
            tier=str(item.get("tier", "")).strip().lower(),
        )
        by_key[_row_key(trace_id, event_hash, logged_at)] = row
    return by_key, warnings


def _is_empty_mapping(row: Dict[str, Any]) -> bool:
    event_type = str(row.get("semantic_event_type", "")).strip().lower()
    sectors = _norm_list(row.get("sector_candidates", []) or [])
    if event_type and event_type != "other" and not sectors:
        return True
    return False


def _healthcare_misroute(row: Dict[str, Any], label: Optional[LabelRow]) -> bool:
    sectors = [_norm_token(s) for s in _norm_list(row.get("sector_candidates", []) or [])]
    has_healthcare = "healthcare" in sectors
    if not has_healthcare:
        return False
    if label is None:
        return False
    expected = [_norm_token(s) for s in label.sectors_expected]
    return "healthcare" not in expected


def _wrong_mapping(row: Dict[str, Any], label: Optional[LabelRow]) -> bool:
    if label is None:
        return False
    predicted = {_norm_token(x) for x in _norm_list(row.get("sector_candidates", []) or [])}
    expected = {_norm_token(x) for x in label.sectors_expected}
    if not expected:
        return False
    return bool(predicted) and predicted.isdisjoint(expected)


def _conduction_mapping_correct(row: Dict[str, Any], label: Optional[LabelRow]) -> Optional[int]:
    if label is None:
        return None
    predicted = {_norm_token(x) for x in _norm_list(row.get("sector_candidates", []) or [])}
    expected = {_norm_token(x) for x in label.sectors_expected}
    if not expected:
        return None
    return 1 if predicted.intersection(expected) else 0


def _ai_semantic_correct(row: Dict[str, Any], label: Optional[LabelRow]) -> Optional[int]:
    if label is None or not label.event_type_expected:
        return None
    predicted = _norm_token(row.get("semantic_event_type", ""))
    return 1 if predicted == _norm_token(label.event_type_expected) else 0


def _ticker_fp(row: Dict[str, Any]) -> int:
    return 1 if _safe_int(row.get("ticker_truth_source_miss", 0), 0) > 0 else 0


def _ticker_hit(row: Dict[str, Any]) -> int:
    return 1 if _safe_int(row.get("ticker_truth_source_hit", 0), 0) > 0 else 0


def _primary_sector_match(row: Dict[str, Any], label: Optional[LabelRow]) -> Optional[int]:
    if label is None:
        return None
    expected = {_norm_token(x) for x in label.sectors_expected}
    if not expected:
        return None
    primary = _norm_token(row.get("primary_sector", ""))
    if not primary:
        sectors = _norm_list(row.get("sector_candidates", []) or [])
        primary = _norm_token(sectors[0]) if sectors else ""
    if not primary:
        return 0
    return 1 if primary in expected else 0


def _bucket_name(row: Dict[str, Any], fallback: str = "unknown") -> str:
    return str(row.get("semantic_event_type", "") or fallback)


def _rate(n: float, d: float) -> float:
    if d <= 0:
        return 0.0
    return n / d


def _mean(vals: List[float]) -> float:
    if not vals:
        return 0.0
    return sum(vals) / len(vals)


def _topn(counter: Dict[str, int], n: int = 10) -> List[Dict[str, Any]]:
    items = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:n]
    return [{"key": k, "count": v} for k, v in items]


def _compute_metrics(
    rows: List[Dict[str, Any]],
    labels_by_key: Dict[str, LabelRow],
    tier_map: Dict[str, set[str]],
) -> Dict[str, Any]:
    groups: Dict[str, List[Dict[str, Any]]] = {"overall": rows, "tier1": [], "tier2": [], "tier3": []}
    for row in rows:
        label = labels_by_key.get(_scorecard_key(row)) or labels_by_key.get(_scorecard_fallback_key(row))
        event_type = _norm_token(row.get("semantic_event_type", ""))
        if label and label.tier in ("tier1", "tier2", "tier3"):
            groups[label.tier].append(row)
        elif event_type in tier_map["tier1"]:
            groups["tier1"].append(row)
        elif event_type in tier_map["tier2"]:
            groups["tier2"].append(row)
        else:
            groups["tier3"].append(row)

    error_buckets = {
        "empty_mapping": {},
        "wrong_mapping": {},
        "healthcare_misroute": {},
        "ticker_false_positive": {},
    }

    out: Dict[str, Any] = {"groups": {}}
    for gname, grows in groups.items():
        total = len(grows)
        sectors_with = 0
        stocks_with = 0
        recommended_with = 0
        watchlist_with = 0
        empty_mapping = 0
        wrong_mapping = 0
        healthcare_misroute = 0
        ticker_fp_count = 0
        ticker_hit_count = 0
        direct_ticker_base = 0
        direct_ticker_retained = 0
        inferred_ticker_total = 0
        inferred_ticker_qualified = 0
        penalty_trigger_count = 0
        penalty_trigger_all_buckets_count = 0
        primary_sector_matches: List[float] = []
        ai_correct: List[float] = []
        conduction_correct: List[float] = []
        sector_quality_scores: List[float] = []
        stock_quality_scores: List[float] = []
        mapping_accept_scores: List[float] = []
        ai_conf_scores: List[float] = []
        rec_conf_scores: List[float] = []
        by_event_type_total: Dict[str, int] = {}
        by_event_type_recommended: Dict[str, int] = {}

        for row in grows:
            label = labels_by_key.get(_scorecard_key(row)) or labels_by_key.get(_scorecard_fallback_key(row))
            sectors = _norm_list(row.get("sector_candidates", []) or [])
            stock_candidates = row.get("stock_candidates", []) or []
            stocks = []
            if isinstance(stock_candidates, list):
                stocks = [
                    str((item or {}).get("symbol", "")).strip().upper()
                    for item in stock_candidates
                    if isinstance(item, dict) and str((item or {}).get("symbol", "")).strip()
                ]
            if not stocks:
                stocks = _norm_list(row.get("ticker_candidates", []) or [])
            if not stocks:
                stocks = _norm_list(row.get("ai_recommended_stocks", []) or [])
            event_type_name = _bucket_name(row)
            by_event_type_total[event_type_name] = by_event_type_total.get(event_type_name, 0) + 1
            if stocks:
                by_event_type_recommended[event_type_name] = by_event_type_recommended.get(event_type_name, 0) + 1

            if sectors:
                sectors_with += 1
            if stocks:
                stocks_with += 1
            rec_buckets = row.get("stock_recommendation_buckets", {})
            if isinstance(rec_buckets, dict):
                rec_list = rec_buckets.get("recommended", [])
                watch_list = rec_buckets.get("watchlist", [])
                if isinstance(rec_list, list) and rec_list:
                    recommended_with += 1
                if isinstance(watch_list, list) and watch_list:
                    watchlist_with += 1

            if _is_empty_mapping(row):
                empty_mapping += 1
                key = _bucket_name(row)
                error_buckets["empty_mapping"][key] = error_buckets["empty_mapping"].get(key, 0) + 1

            if _wrong_mapping(row, label):
                wrong_mapping += 1
                key = _bucket_name(row)
                error_buckets["wrong_mapping"][key] = error_buckets["wrong_mapping"].get(key, 0) + 1

            if _healthcare_misroute(row, label):
                healthcare_misroute += 1
                key = _bucket_name(row)
                error_buckets["healthcare_misroute"][key] = error_buckets["healthcare_misroute"].get(key, 0) + 1

            if _ticker_fp(row):
                ticker_fp_count += 1
                key = _bucket_name(row)
                error_buckets["ticker_false_positive"][key] = error_buckets["ticker_false_positive"].get(key, 0) + 1
            if _ticker_hit(row):
                ticker_hit_count += 1
            direct_mentions = {_norm_token(x) for x in _norm_list(row.get("ai_recommended_stocks", []) or [])}
            candidates = row.get("stock_candidates", []) or []
            if direct_mentions:
                direct_ticker_base += 1
                retained = False
                for cand in candidates if isinstance(candidates, list) else []:
                    symbol = _norm_token((cand or {}).get("symbol", ""))
                    if symbol and symbol in direct_mentions:
                        retained = True
                        break
                if retained:
                    direct_ticker_retained += 1
            if isinstance(candidates, list):
                for cand in candidates:
                    if not isinstance(cand, dict):
                        continue
                    penalties = cand.get("penalties", [])
                    if isinstance(penalties, list) and penalties:
                        penalty_trigger_count += 1
                    direct_flag = bool(cand.get("whether_direct_ticker_mentioned", False))
                    if direct_flag:
                        continue
                    inferred_ticker_total += 1
                    if _safe_float(cand.get("confidence"), 0.0) >= 0.6:
                        inferred_ticker_qualified += 1
                    rec_conf_scores.append(_safe_float(cand.get("confidence"), 0.0))
            if isinstance(rec_buckets, dict):
                for bucket_key in ("recommended", "watchlist", "rejected"):
                    bucket = rec_buckets.get(bucket_key, [])
                    if not isinstance(bucket, list):
                        continue
                    for cand in bucket:
                        if not isinstance(cand, dict):
                            continue
                        penalties = cand.get("penalties", [])
                        if isinstance(penalties, list) and penalties:
                            penalty_trigger_all_buckets_count += 1

            ai_match = _ai_semantic_correct(row, label)
            if ai_match is not None:
                ai_correct.append(float(ai_match))
            c_match = _conduction_mapping_correct(row, label)
            if c_match is not None:
                conduction_correct.append(float(c_match))
            p_match = _primary_sector_match(row, label)
            if p_match is not None:
                primary_sector_matches.append(float(p_match))

            sector_quality_scores.append(_safe_float(row.get("sector_quality_score"), 0.0))
            stock_quality_scores.append(_safe_float(row.get("ticker_quality_score"), 0.0))
            mapping_accept_scores.append(_safe_float(row.get("mapping_acceptance_score"), 0.0))
            ai_conf_scores.append(_safe_float(row.get("ai_confidence"), 0.0))
            rec_conf_scores.append(_safe_float(row.get("recommendation_confidence_avg"), _safe_float(row.get("ai_confidence"), 0.0) / 100.0))

        coverage = {}
        for k, v in by_event_type_total.items():
            coverage[k] = round(_rate(by_event_type_recommended.get(k, 0), v), 4)

        group_metrics = {
            "total": total,
            "ai_semantic_accuracy": _mean(ai_correct),
            "ai_confidence_mean": _mean(ai_conf_scores),
            "conduction_mapping_accuracy": _mean(conduction_correct),
            "sector_recognition_rate": _rate(sectors_with, total),
            "sector_recall": _rate(sectors_with, total),
            "sector_quality_mean": _mean(sector_quality_scores),
            "empty_mapping_rate": _rate(empty_mapping, total),
            "empty_sector_rate": _rate(empty_mapping, total),
            "wrong_mapping_rate": _rate(wrong_mapping, total),
            "wrong_sector_rate": _rate(wrong_mapping, total),
            "healthcare_misroute_count": healthcare_misroute,
            "healthcare_false_mapping_count": healthcare_misroute,
            "primary_sector_accuracy": _mean(primary_sector_matches),
            "mapping_acceptance_mean": _mean(mapping_accept_scores),
            "stock_recommendation_rate": _rate(stocks_with, total),
            "effective_recommended_rate": _rate(recommended_with, total),
            "watchlist_rate": _rate(watchlist_with, total),
            "stock_quality_mean": _mean(stock_quality_scores),
            "stock_quality_score": _mean(stock_quality_scores),
            "ticker_hit_rate": _rate(ticker_hit_count, total),
            "ticker_hit_count": ticker_hit_count,
            "ticker_false_positive_rate": _rate(ticker_fp_count, total),
            "ticker_false_positive_count": ticker_fp_count,
            "direct_ticker_retention_rate": _rate(direct_ticker_retained, direct_ticker_base),
            "inferred_ticker_quality_score": _rate(inferred_ticker_qualified, inferred_ticker_total),
            "region_mismatch_penalty_trigger_rate": _rate(penalty_trigger_count, total),
            "region_mismatch_penalty_trigger_rate_all_buckets": _rate(penalty_trigger_all_buckets_count, total),
            "recommendation_confidence_avg": _mean(rec_conf_scores),
            "recommendation_coverage_by_event_type": coverage,
            "sector_weight_quality_score": _mean([_safe_float(r.get("sector_weight_quality_score"), 0.0) for r in grows]),
        }
        out["groups"][gname] = group_metrics

    out["error_buckets"] = {
        "empty_mapping_topn": _topn(error_buckets["empty_mapping"]),
        "wrong_mapping_topn": _topn(error_buckets["wrong_mapping"]),
        "healthcare_misroute_topn": _topn(error_buckets["healthcare_misroute"]),
        "ticker_false_positive_topn": _topn(error_buckets["ticker_false_positive"]),
    }
    return out


def _compare(prev: Dict[str, Any], new: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
    cmp_cfg = policy.get("comparison", {})
    min_delta = cmp_cfg.get("min_improvement_delta", {})
    flat_band = cmp_cfg.get("flat_band", {})
    labels = cmp_cfg.get("status_labels", {})

    ratio_metrics = {
        "ai_semantic_accuracy",
        "sector_recall",
        "empty_mapping_rate",
        "wrong_mapping_rate",
        "stock_recommendation_rate",
        "effective_recommended_rate",
        "watchlist_rate",
        "ticker_hit_rate",
        "ticker_false_positive_rate",
        "conduction_mapping_accuracy",
    }
    lower_better_metrics = {
        "empty_mapping_rate",
        "empty_sector_rate",
        "wrong_mapping_rate",
        "wrong_sector_rate",
        "ticker_false_positive_rate",
        "healthcare_misroute_count",
        "healthcare_false_mapping_count",
    }

    output = {"groups": {}}
    for gname in prev["groups"].keys():
        p = prev["groups"][gname]
        n = new["groups"][gname]
        gdiff: Dict[str, Any] = {}
        for k, pv in p.items():
            if k == "total":
                gdiff[k] = {"v_prev": pv, "v_new": n.get(k, 0), "delta": n.get(k, 0) - pv, "status": labels.get("flat", "flat")}
                continue
            nv = n.get(k, 0.0)
            if isinstance(pv, (int, float)) and isinstance(nv, (int, float)):
                delta = nv - pv
                if k in ratio_metrics:
                    improve = float(min_delta.get("ratio_metric", 0.01))
                    flat = float(flat_band.get("ratio_metric", 0.005))
                else:
                    improve = float(min_delta.get("score_metric", 1.0))
                    flat = float(flat_band.get("score_metric", 0.5))
                signed_delta = -delta if k in lower_better_metrics else delta
                if signed_delta >= improve:
                    status = labels.get("improved", "improved")
                elif abs(signed_delta) <= flat:
                    status = labels.get("flat", "flat")
                else:
                    status = labels.get("regressed", "regressed")
            else:
                delta = 0.0
                status = labels.get("flat", "flat")
            gdiff[k] = {"v_prev": pv, "v_new": nv, "delta": delta, "status": status}
        output["groups"][gname] = gdiff
    return output


def _eval_gate(metric: float, op: str, target: float) -> bool:
    if op == "<":
        return metric < target
    if op == "<=":
        return metric <= target
    if op == "=":
        return abs(metric - target) < 1e-12
    if op == ">":
        return metric > target
    if op == ">=":
        return metric >= target
    raise ValueError(f"unsupported op={op}")


def _run_gates(new_metrics: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
    gates = policy.get("gates", {})
    hard = gates.get("hard", {})
    target = gates.get("target", {})
    out = {"hard": {}, "target": {}, "hard_pass": True, "target_pass": True}

    overall = new_metrics["groups"]["overall"]
    tier1 = new_metrics["groups"]["tier1"]

    for name, rule in hard.items():
        m = overall.get(name, 0.0)
        ok = _eval_gate(float(m), str(rule.get("op")), float(rule.get("value")))
        out["hard"][name] = {"metric": m, "rule": rule, "pass": ok}
        out["hard_pass"] = out["hard_pass"] and ok

    for name, rule in target.items():
        source = tier1 if name.startswith("tier1_") else overall
        metric_name = name.replace("tier1_", "")
        m = source.get(metric_name, 0.0)
        ok = _eval_gate(float(m), str(rule.get("op")), float(rule.get("value")))
        out["target"][name] = {"metric": m, "rule": rule, "pass": ok}
        out["target_pass"] = out["target_pass"] and ok
    return out


def _to_markdown(
    out: Dict[str, Any],
    policy_path: Path,
    prev_path: Path,
    new_path: Path,
) -> str:
    lines: List[str] = []
    lines.append("# AI Mapping Regression Eval Report")
    lines.append("")
    lines.append(f"- Policy: `{policy_path}`")
    lines.append(f"- v_prev: `{prev_path}`")
    lines.append(f"- v_new: `{new_path}`")
    lines.append("")
    lines.append("## Gate Decision")
    lines.append("")
    gate = out["gate"]
    lines.append(f"- hard_pass: **{gate['hard_pass']}**")
    lines.append(f"- target_pass: **{gate['target_pass']}**")
    lines.append("")
    lines.append("## Overall Delta")
    lines.append("")
    lines.append("| metric | v_prev | v_new | delta | status |")
    lines.append("|---|---:|---:|---:|---|")
    for k, v in out["delta"]["groups"]["overall"].items():
        if k == "total":
            continue
        if isinstance(v["v_prev"], (int, float)) and isinstance(v["v_new"], (int, float)):
            lines.append(f"| {k} | {v['v_prev']:.4f} | {v['v_new']:.4f} | {v['delta']:.4f} | {v['status']} |")
        else:
            lines.append(f"| {k} | `{v['v_prev']}` | `{v['v_new']}` | n/a | {v['status']} |")
    lines.append("")
    lines.append("## Tier Delta")
    for tier in ("tier1", "tier2", "tier3"):
        lines.append("")
        lines.append(f"### {tier}")
        lines.append("")
        lines.append("| metric | v_prev | v_new | delta | status |")
        lines.append("|---|---:|---:|---:|---|")
        for k, v in out["delta"]["groups"][tier].items():
            if k == "total":
                continue
            if isinstance(v["v_prev"], (int, float)) and isinstance(v["v_new"], (int, float)):
                lines.append(f"| {k} | {v['v_prev']:.4f} | {v['v_new']:.4f} | {v['delta']:.4f} | {v['status']} |")
            else:
                lines.append(f"| {k} | `{v['v_prev']}` | `{v['v_new']}` | n/a | {v['status']} |")
    lines.append("")
    lines.append("## Error Buckets (v_new)")
    lines.append("")
    for key, items in out["v_new"].get("error_buckets", {}).items():
        lines.append(f"### {key}")
        if not items:
            lines.append("- none")
        else:
            for item in items:
                lines.append(f"- {item['key']}: {item['count']}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AI mapping regression evaluation.")
    parser.add_argument("--policy", type=Path, default=Path("configs/ai_mapping_regression_policy.yaml"))
    parser.add_argument("--prev-scorecard", type=Path, required=True)
    parser.add_argument("--new-scorecard", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--out-md", type=Path, required=True)
    args = parser.parse_args()

    policy = _read_yaml(args.policy)
    labels_path = Path(policy["datasets"]["benchmark"]["labels_file"])
    labels_by_key, label_warnings = _load_labels(labels_path)

    prev_rows = _read_jsonl(args.prev_scorecard)
    new_rows = _read_jsonl(args.new_scorecard)

    tier_map = policy.get("tier_mapping", {})
    tier_sets = {
        "tier1": {_norm_token(x) for x in tier_map.get("tier1", [])},
        "tier2": {_norm_token(x) for x in tier_map.get("tier2", [])},
        "tier3": {_norm_token(x) for x in tier_map.get("tier3", [])},
    }

    prev_metrics = _compute_metrics(prev_rows, labels_by_key, tier_sets)
    new_metrics = _compute_metrics(new_rows, labels_by_key, tier_sets)
    delta = _compare(prev_metrics, new_metrics, policy)
    gate = _run_gates(new_metrics, policy)

    out = {
        "policy": str(args.policy),
        "labels_file": str(labels_path),
        "label_rows": len(labels_by_key),
        "label_warnings": label_warnings,
        "v_prev": prev_metrics,
        "v_new": new_metrics,
        "delta": delta,
        "gate": gate,
    }

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.out_md.write_text(_to_markdown(out, args.policy, args.prev_scorecard, args.new_scorecard), encoding="utf-8")
    print(f"wrote json: {args.out_json}")
    print(f"wrote md: {args.out_md}")
    print(f"hard_pass={gate['hard_pass']} target_pass={gate['target_pass']} label_rows={len(labels_by_key)}")


if __name__ == "__main__":
    main()
