#!/usr/bin/env python3
"""
GLM 语义解析质量评分分析工具

读取 trace_scorecard.jsonl，按新闻类型统计 AI 的板块/个股识别质量评分。
输出格式化的 Markdown 报告。

Usage:
    python3 scripts/analyze_glm_semantic_quality.py \\
        --scorecard logs/trace_scorecard.jsonl \\
        --out reports/glm_quality_report.md
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


def load_scorecard(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def analyze(records: list[dict[str, Any]]) -> str:
    # Group data by event_type
    data: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "count": 0, "stocks_with": 0, "sectors_with": 0,
        "sector_scores": [], "ticker_scores": [],
        "mapping_scores": [], "output_scores": [], "confidences": [],
        "ticker_hit": 0, "ticker_miss": 0,
    })

    for d in records:
        et = d.get("semantic_event_type", "") or "(empty)"
        g = data[et]
        g["count"] += 1

        stocks = d.get("ai_recommended_stocks", []) or []
        sectors = d.get("sector_candidates", []) or []
        if stocks and any(s.strip() for s in stocks):
            g["stocks_with"] += 1
        if sectors and any(s.strip() for s in sectors):
            g["sectors_with"] += 1

        score_map = {
            "sector_quality_score": "sector_scores",
            "ticker_quality_score": "ticker_scores",
            "mapping_acceptance_score": "mapping_scores",
            "output_quality_score": "output_scores",
        }
        for src_key, dst_key in score_map.items():
            v = d.get(src_key)
            if v is not None:
                g[dst_key].append(v)

        conf = d.get("ai_confidence")
        if conf:
            g["confidences"].append(conf)
        g["ticker_hit"] += d.get("ticker_truth_source_hit", 0) or 0
        g["ticker_miss"] += d.get("ticker_truth_source_miss", 0) or 0

    sorted_types = sorted(data.keys(), key=lambda k: -data[k]["count"])
    total = sum(g["count"] for g in data.values())

    lines: list[str] = []
    def out(text: str = "") -> None:
        lines.append(text)

    out("# GLM 语义解析质量评分报告")
    out()
    out(f"**数据规模**: {total} 条 trace_scorecard，{len(sorted_types)} 种事件类型")
    out(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    out()
    out("## 总表")
    out()
    header = "| 新闻类型 | 数量 | 个股推荐率 | 板块识别率 | 板块质量均分 | 个股质量均分 | 映射接受均分 | 输出质量均分 | AI信心均分 | ticker✅ | ticker❌ | 评价 |"
    sep = "|---------|:---:|:---------:|:---------:|:----------:|:----------:|:----------:|:----------:|:--------:|:-------:|:-------:|:---:|"
    out(header)
    out(sep)

    def avg(vals):
        return sum(vals) / len(vals) if vals else 0

    for et in sorted_types:
        g = data[et]
        c = g["count"]
        stock_rate = g["stocks_with"] / c * 100
        sector_rate = g["sectors_with"] / c * 100
        a_sq = avg(g["sector_scores"])
        a_tq = avg(g["ticker_scores"])
        a_mq = avg(g["mapping_scores"])
        a_oq = avg(g["output_scores"])
        a_cf = avg(g["confidences"])
        hit, miss = g["ticker_hit"], g["ticker_miss"]

        if a_tq >= 50 and stock_rate >= 40:
            rating = "✅"
        elif a_tq < 20 or (c >= 3 and miss > hit * 2 and miss >= 2):
            rating = "❌"
        elif c >= 5 and a_tq >= 30:
            rating = "⚠️"
        else:
            rating = "⋯"

        out(f"| {et[:18]} | {c} | {stock_rate:.1f}% | {sector_rate:.1f}% "
            f"| {a_sq:.1f} | {a_tq:.1f} | {a_mq:.1f} | {a_oq:.1f} "
            f"| {a_cf:.1f} | {hit} | {miss} | {rating} |")

    # Total row
    all_sq = [s for g in data.values() for s in g["sector_scores"]]
    all_tq = [s for g in data.values() for s in g["ticker_scores"]]
    all_mq = [s for g in data.values() for s in g["mapping_scores"]]
    all_oq = [s for g in data.values() for s in g["output_scores"]]
    all_cf = [s for g in data.values() for s in g["confidences"]]
    th = sum(g["ticker_hit"] for g in data.values())
    tm = sum(g["ticker_miss"] for g in data.values())
    sw = sum(g["stocks_with"] for g in data.values())
    se = sum(g["sectors_with"] for g in data.values())

    out(f"| **合计** | **{total}** | **{sw/total*100:.1f}%** | **{se/total*100:.1f}%** "
        f"| **{avg(all_sq):.1f}** | **{avg(all_tq):.1f}** | **{avg(all_mq):.1f}** "
        f"| **{avg(all_oq):.1f}** | **{avg(all_cf):.1f}** | **{th}** | **{tm}** | |")

    out()
    out("## 关键指标")
    out()
    out(f"| 指标 | 数值 | 评价 |")
    out(f"|------|:---:|:----|")
    out(f"| 整体个股推荐率 | {sw/total*100:.1f}% | {'✅' if sw/total >= 0.6 else '⚠️' if sw/total >= 0.4 else '❌'} |")
    out(f"| 整体板块识别率 | {se/total*100:.1f}% | {'✅' if se/total >= 0.6 else '⚠️' if se/total >= 0.4 else '❌'} |")
    out(f"| 个股质量均分 | {avg(all_tq):.1f} / 100 | {'✅' if avg(all_tq) >= 60 else '⚠️' if avg(all_tq) >= 40 else '🔴 极差'} |")
    out(f"| 板块质量均分 | {avg(all_sq):.1f} / 100 | {'✅' if avg(all_sq) >= 60 else '⚠️' if avg(all_sq) >= 40 else '🔴'} |")
    out(f"| 映射接受均分 | {avg(all_mq):.1f} / 100 | ✅ |")
    out(f"| AI 平均信心分 | {avg(all_cf):.1f} / 100 | ✅ |")
    out(f"| ticker 总命中 vs 误报 | {th} ✅ / {tm} ❌ | {'✅' if th > tm else '🔴 误报多于命中'} |")

    out()
    out("## 表现较好的新闻类型（样本 >= 3）")
    out()
    for et in sorted_types:
        g = data[et]
        if g["count"] < 3:
            continue
        a_tq = avg(g["ticker_scores"])
        stock_rate = g["stocks_with"] / g["count"] * 100
        if a_tq >= 50 or stock_rate >= 50:
            out(f"- ✅ **{et}**: 个股质量={a_tq:.1f}  推荐率={stock_rate:.1f}%  "
                f"命中/误报={g['ticker_hit']}/{g['ticker_miss']}")

    out()
    out("## 表现较差的新闻类型（样本 >= 3）")
    out()
    for et in sorted_types:
        g = data[et]
        if g["count"] < 3:
            continue
        a_tq = avg(g["ticker_scores"])
        stock_rate = g["stocks_with"] / g["count"] * 100
        hit, miss = g["ticker_hit"], g["ticker_miss"]
        if a_tq < 20 or (a_tq < 40 and miss > hit * 2 and miss >= 2):
            out(f"- ❌ **{et}**: 个股质量={a_tq:.1f}  推荐率={stock_rate:.1f}%  "
                f"命中/误报={hit}/{miss}")

    out()
    out("## 典型误报模式")
    out()
    problems: list[tuple[str, list[str]]] = []
    for d in records:
        stocks = d.get("ai_recommended_stocks", []) or []
        miss = d.get("ticker_truth_source_miss", 0) or 0
        if stocks and miss > 0:
            ptype = d.get("semantic_event_type", "?")
            problems.append((ptype, stocks))

    seen: set[str] = set()
    for ptype, pstocks in problems:
        key = str(sorted(pstocks))
        if key not in seen:
            seen.add(key)
            out(f"- **{ptype}**: `{pstocks}` → 非有效股票代码")
    out()
    out(f"> 共 {len(problems)} 次误报，{len(seen)} 种独特模式")

    out()
    out("---")
    out()
    out("*报告由 scripts/analyze_glm_semantic_quality.py 自动生成*")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="GLM Semantic Parsing Quality Report",
    )
    parser.add_argument(
        "--scorecard", required=True, type=Path,
        help="Path to trace_scorecard.jsonl",
    )
    parser.add_argument(
        "--out", required=True, type=Path,
        help="Output markdown report path",
    )
    args = parser.parse_args()

    if not args.scorecard.exists():
        print(f"ERROR: scorecard not found: {args.scorecard}", file=sys.stderr)
        sys.exit(1)

    records = load_scorecard(args.scorecard)
    report = analyze(records)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print(f"Report written: {args.out}")
    print(f"Records analyzed: {len(records)}")


if __name__ == "__main__":
    main()
