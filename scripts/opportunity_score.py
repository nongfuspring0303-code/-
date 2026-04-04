#!/usr/bin/env python3
"""
Phase 3 B-layer opportunity scoring.

B-1: Premium stock pool filtering.
B-2: Long/short opportunity scoring with differentiation metric support.
B-3: Opportunity card field completion.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml


def _root_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _norm_sector(name: Any) -> str:
    return str(name or "").strip().lower()


@dataclass
class PremiumStock:
    symbol: str
    name: str
    sector: str
    roe: float
    market_cap_billion: float
    liquidity_score: float
    last_price: float


class PremiumStockPool:
    """Loads and filters configurable premium stock pool."""

    def __init__(self, pool_config_path: str | None = None):
        self.pool_config_path = Path(pool_config_path) if pool_config_path else _root_dir() / "configs" / "premium_stock_pool.yaml"
        self._cfg = self._load_yaml(self.pool_config_path)
        self.filters = self._cfg.get("filters", {})
        self.rules = self._cfg.get("opportunity_rules", {})
        self._stocks_by_symbol = self._build_stock_index(self._cfg.get("stocks", []))

    @staticmethod
    def _load_yaml(path: Path) -> Dict[str, Any]:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    @staticmethod
    def _to_float(val: Any, default: float = 0.0) -> float:
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    def _build_stock_index(self, stocks: List[Dict[str, Any]]) -> Dict[str, PremiumStock]:
        out: Dict[str, PremiumStock] = {}
        for item in stocks:
            symbol = str(item.get("symbol", "")).strip().upper()
            if not symbol:
                continue
            out[symbol] = PremiumStock(
                symbol=symbol,
                name=str(item.get("name", symbol)),
                sector=str(item.get("sector", "未知")),
                roe=self._to_float(item.get("roe", 0)),
                market_cap_billion=self._to_float(item.get("market_cap_billion", 0)),
                liquidity_score=self._to_float(item.get("liquidity_score", 0)),
                last_price=self._to_float(item.get("last_price", 100.0), 100.0),
            )
        return out

    def _pass_thresholds(self, stock: PremiumStock) -> bool:
        roe_min = self._to_float(self.filters.get("roe_min", 15.0), 15.0)
        mkt_cap_min = self._to_float(self.filters.get("market_cap_billion_min", 500.0), 500.0)
        liq_min = self._to_float(self.filters.get("liquidity_score_min", 0.60), 0.60)
        return stock.roe > roe_min and stock.market_cap_billion > mkt_cap_min and stock.liquidity_score > liq_min

    def get_stock(self, symbol: str) -> PremiumStock | None:
        return self._stocks_by_symbol.get(str(symbol).strip().upper())

    def pick_by_sector(self, sector_name: str, limit: int | None = None) -> List[PremiumStock]:
        norm = _norm_sector(sector_name)
        selected = [s for s in self._stocks_by_symbol.values() if _norm_sector(s.sector) == norm and self._pass_thresholds(s)]
        selected.sort(key=lambda x: (x.liquidity_score, x.market_cap_billion), reverse=True)
        if limit is None:
            return selected
        return selected[: max(0, int(limit))]

    def filter_candidates(self, candidates: List[Dict[str, Any]]) -> List[PremiumStock]:
        filtered: List[PremiumStock] = []
        for item in candidates:
            symbol = str(item.get("symbol", "")).strip().upper()
            if not symbol:
                continue
            stock = self.get_stock(symbol)
            if stock and self._pass_thresholds(stock):
                filtered.append(stock)
        return filtered


class OpportunityScorer:
    """Builds opportunity_update payload with completed opportunity-card fields."""

    def __init__(self, pool_config_path: str | None = None):
        self.pool = PremiumStockPool(pool_config_path=pool_config_path)

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _normalize_direction(value: Any) -> str:
        raw = str(value or "WATCH").strip().upper()
        if raw in {"LONG", "SHORT", "WATCH"}:
            return raw
        if raw == "HURT":
            return "SHORT"
        if raw == "BENEFIT":
            return "LONG"
        return "WATCH"

    def _compute_score(self, impact_score: float, sector_confidence: float, event_beta: float) -> float:
        beta_score = min(1.0, max(0.0, event_beta / 1.5))
        score = 0.45 * impact_score + 0.35 * sector_confidence + 0.20 * beta_score
        return max(0.0, min(1.0, score))

    def _build_entry_zone(self, last_price: float) -> Dict[str, float]:
        support_buf = self._safe_float(self.pool.rules.get("support_buffer_pct", 0.03), 0.03)
        resistance_buf = self._safe_float(self.pool.rules.get("resistance_buffer_pct", 0.03), 0.03)
        support = round(last_price * (1 - support_buf), 2)
        resistance = round(last_price * (1 + resistance_buf), 2)
        return {"support": support, "resistance": resistance}

    def _build_risk_flags(
        self,
        stock: PremiumStock,
        score: float,
        sector_confidence: float,
        candidate_direction: str,
        target_signal: str,
    ) -> List[Dict[str, str]]:
        flags: List[Dict[str, str]] = []

        if stock.liquidity_score < 0.75:
            flags.append({"type": "liquidity", "level": "high", "description": "流动性评分偏低"})
        elif stock.liquidity_score < 0.82:
            flags.append({"type": "liquidity", "level": "medium", "description": "流动性一般"})

        if sector_confidence < 0.6:
            flags.append({"type": "confidence", "level": "high", "description": "板块置信度不足"})

        if score < 0.6:
            flags.append({"type": "volatility", "level": "medium", "description": "信号强度偏弱"})

        if stock.market_cap_billion < 700:
            flags.append({"type": "market_cap", "level": "medium", "description": "市值体量偏小"})

        if candidate_direction and candidate_direction != target_signal:
            flags.append({"type": "direction_conflict", "level": "high", "description": "个股方向与板块方向冲突"})

        return flags

    @staticmethod
    def _resolve_action(signal: str, risk_flags: List[Dict[str, str]]) -> str:
        if len(risk_flags) >= 3:
            return "BLOCK"
        if any(f.get("level") == "high" for f in risk_flags):
            return "PENDING_CONFIRM"
        if signal == "WATCH":
            return "WATCH"
        return "EXECUTE"

    def _candidate_direction(self, candidate: Dict[str, Any]) -> str:
        if "direction" not in candidate:
            return ""
        return self._normalize_direction(candidate.get("direction"))

    def _build_opportunity(
        self,
        trace_id: str,
        sector_name: str,
        sector_direction: str,
        impact_score: float,
        sector_confidence: float,
        stock: PremiumStock,
        candidate: Dict[str, Any],
        timestamp: str,
    ) -> Dict[str, Any]:
        event_beta = self._safe_float(candidate.get("event_beta", 1.0), 1.0)
        score = self._compute_score(impact_score, sector_confidence, event_beta)

        watch_threshold = self._safe_float(self.pool.rules.get("watch_score_threshold", 0.55), 0.55)
        execute_threshold = self._safe_float(self.pool.rules.get("execute_score_threshold", 0.70), 0.70)

        target_signal = sector_direction
        if score < watch_threshold:
            target_signal = "WATCH"
        elif score < execute_threshold and target_signal != "WATCH":
            # keep directional output, but risks will usually prevent direct execute
            target_signal = sector_direction

        candidate_direction = self._candidate_direction(candidate)
        risk_flags = self._build_risk_flags(stock, score, sector_confidence, candidate_direction, target_signal)
        final_action = self._resolve_action(target_signal, risk_flags)

        reasoning = f"{sector_name}方向{sector_direction}，综合评分{score:.2f}"
        if len(reasoning) > 50:
            reasoning = reasoning[:50]

        return {
            "trace_id": trace_id,
            "symbol": stock.symbol,
            "name": stock.name,
            "sector": sector_name,
            "signal": target_signal,
            "entry_zone": self._build_entry_zone(stock.last_price),
            "risk_flags": risk_flags,
            "final_action": final_action,
            "reasoning": reasoning,
            "confidence": round(score, 2),
            "timestamp": timestamp,
        }

    def build_opportunity_update(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        trace_id = str(payload.get("trace_id", "evt_unknown"))
        schema_version = str(payload.get("schema_version", "v1.0"))
        timestamp = str(payload.get("timestamp", _utc_now_iso()))

        sectors = payload.get("sectors", [])
        stock_candidates = payload.get("stock_candidates", [])
        candidates_by_sector: Dict[str, List[Dict[str, Any]]] = {}
        for cand in stock_candidates:
            key = _norm_sector(cand.get("sector", ""))
            candidates_by_sector.setdefault(key, []).append(cand)

        max_per_sector = int(self.pool.rules.get("max_candidates_per_sector", 5))
        opportunities: List[Dict[str, Any]] = []

        for sector in sectors:
            sector_name = str(sector.get("name", "未知板块"))
            norm_sector = _norm_sector(sector_name)
            sector_direction = self._normalize_direction(sector.get("direction", "WATCH"))
            impact_score = self._safe_float(sector.get("impact_score", 0.0), 0.0)
            sector_conf = self._safe_float(sector.get("confidence", 0.0), 0.0)

            seeded_candidates = candidates_by_sector.get(norm_sector, [])
            selected_stocks = self.pool.filter_candidates(seeded_candidates)

            if not selected_stocks:
                selected_stocks = self.pool.pick_by_sector(sector_name, limit=max_per_sector)
                seeded_candidates = [{"symbol": s.symbol, "sector": s.sector, "direction": sector_direction, "event_beta": 1.0} for s in selected_stocks]

            for stock in selected_stocks[:max_per_sector]:
                match_candidate = next((c for c in seeded_candidates if str(c.get("symbol", "")).upper() == stock.symbol), {})
                opportunities.append(
                    self._build_opportunity(
                        trace_id=trace_id,
                        sector_name=sector_name,
                        sector_direction=sector_direction,
                        impact_score=impact_score,
                        sector_confidence=sector_conf,
                        stock=stock,
                        candidate=match_candidate,
                        timestamp=timestamp,
                    )
                )

        opportunities.sort(key=lambda x: x.get("confidence", 0.0), reverse=True)

        return {
            "type": "opportunity_update",
            "trace_id": trace_id,
            "schema_version": schema_version,
            "opportunities": opportunities,
            "timestamp": timestamp,
            "stats": {
                "opportunity_count": len(opportunities),
                "premium_pool_only": True,
            },
        }


def evaluate_direction_consistency(
    scorer: OpportunityScorer,
    bullish_cases: List[Dict[str, Any]],
    bearish_cases: List[Dict[str, Any]],
) -> Dict[str, float]:
    def _ratio(cases: List[Dict[str, Any]], expected_signal: str) -> float:
        total = 0
        matched = 0
        for case in cases:
            update = scorer.build_opportunity_update(case)
            for opp in update.get("opportunities", []):
                total += 1
                if opp.get("signal") == expected_signal:
                    matched += 1
        if total == 0:
            return 0.0
        return matched / total

    bull_long = _ratio(bullish_cases, "LONG")
    bear_short = _ratio(bearish_cases, "SHORT")
    differentiation_rate = (bull_long + bear_short) / 2

    return {
        "bullish_long_ratio": round(bull_long, 4),
        "bearish_short_ratio": round(bear_short, 4),
        "differentiation_rate": round(differentiation_rate, 4),
    }
