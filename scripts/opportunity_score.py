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
from typing import Any, Dict, List, Optional
import json
import logging
import os
import re
import time
import urllib.request

import yaml

logger = logging.getLogger(__name__)

from config_center import ConfigCenter
from market_data_adapter import MarketDataAdapter

try:
    from transmission_engine.core.state_machine import evaluate_state
except Exception:  # pragma: no cover
    evaluate_state = None


def _root_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _norm_sector(name: Any) -> str:
    return str(name or "").strip().lower()


class SectorAliasResolver:
    """Loads configurable sector alias dictionary and resolves canonical names."""

    def __init__(self, alias_config_path: Optional[str] = None):
        self.alias_config_path = Path(alias_config_path) if alias_config_path else _root_dir() / "configs" / "sector_aliases.yaml"
        self._alias_to_canonical = self._load_aliases(self.alias_config_path)

    @staticmethod
    def _load_yaml(path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _load_aliases(self, path: Path) -> Dict[str, str]:
        cfg = self._load_yaml(path)
        aliases = cfg.get("aliases", {})
        if not isinstance(aliases, dict):
            return {}
        out: Dict[str, str] = {}
        for canonical, values in aliases.items():
            canonical_name = str(canonical or "").strip()
            if not canonical_name:
                continue
            out[_norm_sector(canonical_name)] = canonical_name
            if isinstance(values, list):
                for alias in values:
                    alias_name = str(alias or "").strip()
                    if alias_name:
                        out[_norm_sector(alias_name)] = canonical_name
        return out

    def canonical(self, name: Any) -> str:
        raw = str(name or "").strip()
        if not raw:
            return ""
        return self._alias_to_canonical.get(_norm_sector(raw), raw)


@dataclass
class PremiumStock:
    symbol: str
    name: str
    sector: str
    roe: float
    market_cap_billion: float
    liquidity_score: float
    last_price: float
    price_source: str = "reference_snapshot"


class PremiumStockPool:
    """Loads and filters configurable premium stock pool."""

    def __init__(self, pool_config_path: Optional[str] = None):
        self.pool_config_path = Path(pool_config_path) if pool_config_path else _root_dir() / "configs" / "premium_stock_pool.yaml"
        self.sector_aliases = SectorAliasResolver()
        self._cfg = self._load_yaml(self.pool_config_path)
        self.filters = self._cfg.get("filters", {})
        self.rules = self._cfg.get("opportunity_rules", {})
        self.price_source = str(self._cfg.get("price_source", "reference_snapshot"))
        
        # 静态核心池
        self._static_stocks_by_symbol = self._build_stock_index(self._cfg.get("stocks", []))
        
        # 动态补充池（从 stock_cache/ 目录加载）
        self._dynamic_stocks_by_symbol = self._build_dynamic_stock_index()
        
        # 合并两个池（静态池优先）
        self._stocks_by_symbol = {**self._dynamic_stocks_by_symbol, **self._static_stocks_by_symbol}

    def _dynamic_cache_dir(self) -> Path:
        runtime = self._cfg.get("runtime", {}) if isinstance(self._cfg, dict) else {}
        stock_pool_cfg = runtime.get("stock_pool", {}) if isinstance(runtime, dict) else {}
        configured = str(stock_pool_cfg.get("dynamic_cache_dir", "") or "").strip()
        if not configured:
            return _root_dir().parent / "stock_cache"
        path = Path(configured)
        if path.is_absolute():
            return path
        return _root_dir().parent / path

    def canonical_sector(self, name: Any) -> str:
        return self.sector_aliases.canonical(name)

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
                price_source=str(item.get("price_source", self.price_source)),
            )
        return out

    def _build_dynamic_stock_index(self) -> Dict[str, PremiumStock]:
        """从 stock_cache/ 目录动态加载股票数据"""
        out: Dict[str, PremiumStock] = {}
        
        # 检查 pandas 是否可用
        try:
            import pandas as pd
        except ImportError:
            logger.warning("pandas not available, dynamic stock pool disabled")
            return out
        
        # stock_cache 目录路径
        stock_cache_dir = self._dynamic_cache_dir()
        if not stock_cache_dir.exists():
            logger.warning(f"Stock cache directory not found: {stock_cache_dir}")
            return out
        
        # 扫描所有 *_history.csv 文件
        csv_files = list(stock_cache_dir.glob("*_history.csv"))
        logger.info(f"Found {len(csv_files)} stock history files in {stock_cache_dir}")
        
        for csv_file in csv_files:
            # 从文件名提取股票代码（去除 _history.csv 后缀）
            symbol = csv_file.stem.replace("_history", "").upper()
            if not symbol:
                continue
            
            try:
                # 读取最新价格数据
                df = pd.read_csv(csv_file)
                if df.empty:
                    continue
                
                # 获取最新行数据
                latest = df.iloc[-1]
                last_price = self._to_float(latest.get("close", 100.0), 100.0)
                
                # 计算平均交易量作为流动性指标
                avg_volume = df["volume"].mean() if "volume" in df.columns else 0
                
                # 动态股票使用默认质量指标（因为CSV文件中没有这些信息）
                # 这些股票可以通过筛选器进行质量控制
                out[symbol] = PremiumStock(
                    symbol=symbol,
                    name=f"{symbol} (动态加载)",
                    sector="未知",  # 动态加载的股票暂时标记为未知
                    roe=15.0,  # 使用最低通过阈值
                    market_cap_billion=50.0,  # 使用最低通过阈值
                    liquidity_score=0.6,  # 使用最低通过阈值
                    last_price=last_price,
                    price_source="dynamic_cache",
                )
                
            except Exception as e:
                logger.warning(f"Failed to load stock data for {symbol} from {csv_file}: {e}")
                continue
        
        logger.info(f"Successfully loaded {len(out)} stocks from dynamic cache")
        return out

    def _pass_thresholds(self, stock: PremiumStock) -> bool:
        roe_min = self._to_float(self.filters.get("roe_min", 15.0), 15.0)
        mkt_cap_min = self._to_float(self.filters.get("market_cap_billion_min", 500.0), 500.0)
        liq_min = self._to_float(self.filters.get("liquidity_score_min", 0.60), 0.60)
        return stock.roe >= roe_min and stock.market_cap_billion >= mkt_cap_min and stock.liquidity_score >= liq_min

    def get_stock(self, symbol: str) -> Optional[PremiumStock]:
        return self._stocks_by_symbol.get(str(symbol).strip().upper())

    def get_stock_source(self, symbol: str) -> str:
        """获取股票来源（static 或 dynamic）"""
        normalized = str(symbol).strip().upper()
        if normalized in self._static_stocks_by_symbol:
            return "static"
        elif normalized in self._dynamic_stocks_by_symbol:
            return "dynamic"
        else:
            return "unknown"

    def pick_by_sector(self, sector_name: str, limit: Optional[int] = None) -> List[PremiumStock]:
        norm = _norm_sector(self.canonical_sector(sector_name))
        selected = [
            s
            for s in self._stocks_by_symbol.values()
            if _norm_sector(self.canonical_sector(s.sector)) == norm and self._pass_thresholds(s)
        ]
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

    def __init__(
        self,
        pool_config_path: Optional[str] = None,
        semantic_chain_policy_path: Optional[str] = None,
        template_candidate_guard_path: Optional[str] = None,
    ):
        self.pool = PremiumStockPool(pool_config_path=pool_config_path)
        self.config = ConfigCenter()
        self.config.register("gate_policy", _root_dir() / "configs" / "gate_policy.yaml")
        self._gate_policy = self.config.get_registered("gate_policy", {})
        self._semantic_chain_policy = self._load_semantic_chain_policy(semantic_chain_policy_path)
        self._template_candidate_guard = self._load_template_candidate_guard(template_candidate_guard_path)
        self._price_cache: Dict[str, Dict[str, Any]] = {}
        self._price_fetch_enabled = self._get_price_fetch_enabled()
        self._price_cache_ttl = self._get_price_cache_ttl()
        self._price_fetch_base = self._get_price_fetch_base()
        self._market_data_adapter = MarketDataAdapter(config_getter=self.config.get)
        self._last_provider_meta: Dict[str, Any] = self._empty_provider_meta()

    def _load_semantic_chain_policy(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        path = Path(config_path) if config_path else _root_dir() / "configs" / "semantic_chain_policy.yaml"
        if not path.exists():
            return self._semantic_chain_policy_failed("missing_config")
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = yaml.safe_load(handle) or {}
            if not isinstance(payload, dict):
                return self._semantic_chain_policy_failed("invalid_config")
            loaded = dict(payload)
            loaded["policy_load_status"] = "loaded"
            loaded["policy_error_reason"] = ""
            return loaded
        except Exception:
            return self._semantic_chain_policy_failed("invalid_config")

    @staticmethod
    def _semantic_chain_policy_failed(reason: str) -> Dict[str, Any]:
        return {
            "schema_version": "semantic_chain_policy.v1",
            "threshold_status": "proposed",
            "enforcement_mode": "disabled",
            "policy_load_status": "failed",
            "policy_error_reason": str(reason or "invalid_config"),
            "audit": {
                "primary_sector_only": False,
                "secondary_sector_audit_only": False,
            },
        }

    def _load_template_candidate_guard(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        path = Path(config_path) if config_path else _root_dir() / "configs" / "template_candidate_guard.yaml"
        if not path.exists():
            return self._template_candidate_guard_failed("missing_config")
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = yaml.safe_load(handle) or {}
            if not isinstance(payload, dict):
                return self._template_candidate_guard_failed("invalid_config")
            loaded = dict(payload)
            loaded["threshold_status"] = str(loaded.get("threshold_status", "proposed"))
            loaded["enforcement_mode"] = str(loaded.get("enforcement_mode", "observe_only"))
            loaded["policy_load_status"] = "loaded"
            loaded["policy_error_reason"] = ""
            loaded["support_score_min"] = self._safe_float(loaded.get("support_score_min", 0.0), 0.0)
            loaded["template_phrases"] = self._normalize_guard_list(loaded.get("template_phrases", []))
            loaded["accepted_support_types"] = self._normalize_guard_list(loaded.get("accepted_support_types", []))
            return loaded
        except Exception:
            return self._template_candidate_guard_failed("invalid_config")

    @staticmethod
    def _template_candidate_guard_failed(reason: str) -> Dict[str, Any]:
        return {
            "schema_version": "template_candidate_guard.v1",
            "threshold_status": "proposed",
            "enforcement_mode": "disabled",
            "policy_load_status": "failed",
            "policy_error_reason": str(reason or "invalid_config"),
            "support_score_min": 0.0,
            "template_phrases": [],
            "accepted_support_types": [],
        }

    @staticmethod
    def _normalize_guard_list(values: Any) -> List[str]:
        if not isinstance(values, list):
            return []
        out: List[str] = []
        for item in values:
            text = str(item or "").strip().lower()
            if text:
                out.append(text)
        return out

    @staticmethod
    def _normalize_guard_text(value: Any) -> str:
        return str(value or "").strip().lower()

    @staticmethod
    def _empty_provider_meta() -> Dict[str, Any]:
        return {
            "provider_chain": [],
            "providers_attempted": [],
            "providers_succeeded": [],
            "providers_failed": [],
            "provider_failure_reasons": {},
            "fallback_used": False,
            "fallback_reason": "",
            "unresolved_symbols": [],
        }

    def _snapshot_provider_meta(self) -> Dict[str, Any]:
        adapter = self._market_data_adapter
        if adapter is None:
            return self._empty_provider_meta()
        meta = getattr(adapter, "last_meta", None)
        if meta is None:
            return self._empty_provider_meta()
        return {
            "provider_chain": list(getattr(meta, "provider_chain", []) or []),
            "providers_attempted": list(getattr(meta, "attempted", []) or []),
            "providers_succeeded": list(getattr(meta, "succeeded", []) or []),
            "providers_failed": list(getattr(meta, "failed", []) or []),
            "provider_failure_reasons": dict(getattr(meta, "failure_reasons", {}) or {}),
            "fallback_used": bool(getattr(meta, "fallback_used", False)),
            "fallback_reason": str(getattr(meta, "fallback_reason", "") or ""),
            "unresolved_symbols": list(getattr(meta, "unresolved_symbols", []) or []),
        }

    def _gp(self, dotted_path: str, default: Any) -> Any:
        current: Any = self._gate_policy
        for part in dotted_path.split("."):
            if not isinstance(current, dict) or part not in current:
                return default
            current = current[part]
        return current

    def _get_price_fetch_enabled(self) -> bool:
        env = os.getenv("EDT_PRICE_FETCH", "").strip().lower()
        if env in {"1", "true", "yes"}:
            return True
        if env in {"0", "false", "no"}:
            return False
        return bool(self.config.get("runtime.price_fetch.enabled", True))

    def _get_price_cache_ttl(self) -> int:
        try:
            return int(self.config.get("runtime.price_fetch.cache_ttl_seconds", 120))
        except (TypeError, ValueError):
            return 120

    def _get_price_fetch_base(self) -> str:
        return str(self.config.get("runtime.price_fetch.yahoo_quote_base", "https://query1.finance.yahoo.com/v7/finance/quote?symbols=")).strip()

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_bool(value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            raw = value.strip().lower()
            if raw in {"1", "true", "yes", "y", "on"}:
                return True
            if raw in {"0", "false", "no", "n", "off"}:
                return False
        if value is None:
            return default
        return bool(value)

    def _resolve_primary_sector(self, sectors: List[Dict[str, Any]]) -> str:
        explicit = ""
        for sector in sectors:
            name = str(sector.get("name", "")).strip()
            role = str(sector.get("role", "")).strip().lower()
            if role == "primary" and name:
                return name
            if not explicit and name:
                explicit = name
        return explicit

    def _build_audit_sectors(
        self,
        sectors: List[Dict[str, Any]],
        primary_sector_name: str,
    ) -> List[Dict[str, Any]]:
        audit_rows: List[Dict[str, Any]] = []
        for sector in sectors:
            name = str(sector.get("name", "未知板块"))
            role = "primary" if name and name == primary_sector_name else "secondary"
            audit_rows.append(
                {
                    "name": name,
                    "direction": self._normalize_direction(sector.get("direction", "WATCH")),
                    "impact_score": self._safe_float(sector.get("impact_score", 0.0), 0.0),
                    "confidence": self._safe_float(sector.get("confidence", 0.0), 0.0),
                    "role": role,
                }
            )
        return audit_rows

    def _normalize_direction(self, value: Any) -> str:
        raw = str(value or "WATCH").strip().upper()
        if raw in {"LONG", "SHORT", "WATCH"}:
            return raw
        if raw == "HURT":
            return "SHORT" if bool(self.config.get("runtime.hurt_to_short", False)) else "WATCH"
        if raw == "BENEFIT":
            return "LONG"
        return "WATCH"

    def _compute_score(self, impact_score: float, sector_confidence: float, event_beta: float) -> float:
        beta_score = min(1.0, max(0.0, event_beta / 1.5))
        score = 0.45 * impact_score + 0.35 * sector_confidence + 0.20 * beta_score
        return max(0.0, min(1.0, score))

    def _compute_transmission_score(self, candidate: Dict[str, Any], impact_score: float, sector_confidence: float) -> Dict[str, float]:
        event_exposure = self._safe_float(candidate.get("event_exposure", impact_score * 100.0), impact_score * 100.0)
        event_relevance = self._safe_float(candidate.get("event_relevance", sector_confidence * 100.0), sector_confidence * 100.0)
        relative_strength = self._safe_float(candidate.get("relative_strength", 70.0), 70.0)
        liquidity_score = self._safe_float(candidate.get("liquidity_score", 80.0), 80.0)
        risk_filter_score = self._safe_float(candidate.get("risk_filter_score", 75.0), 75.0)

        event_exposure = max(0.0, min(100.0, event_exposure))
        event_relevance = max(0.0, min(100.0, event_relevance))
        relative_strength = max(0.0, min(100.0, relative_strength))
        liquidity_score = max(0.0, min(100.0, liquidity_score))
        risk_filter_score = max(0.0, min(100.0, risk_filter_score))

        score_breakdown = {
            "event_exposure": round(0.35 * event_exposure, 2),
            "event_relevance": round(0.25 * event_relevance, 2),
            "relative_strength": round(0.20 * relative_strength, 2),
            "liquidity_score": round(0.10 * liquidity_score, 2),
            "risk_filter_score": round(0.10 * risk_filter_score, 2),
        }
        total = round(sum(score_breakdown.values()), 2)
        return {"total": total, "score_breakdown": score_breakdown}

    def _grade_signal(self, score_100: float) -> str:
        a_min = self._safe_float(self._gp("signal_grade.a_min", 78.0), 78.0)
        b_min = self._safe_float(self._gp("signal_grade.b_min", 62.0), 62.0)
        if score_100 >= a_min:
            return "A"
        if score_100 >= b_min:
            return "B"
        return "C"

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

        if stock.market_cap_billion < 500:
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

    def _template_rationale_matches(self, rationale: Any) -> bool:
        text = self._normalize_guard_text(rationale)
        if not text:
            return False
        phrases = self._normalize_guard_list(self._template_candidate_guard.get("template_phrases", []))
        return any(phrase and phrase in text for phrase in phrases)

    def _build_ticker_support_context(
        self,
        *,
        sector_name: str,
        sector_score_source: str,
        candidate: Dict[str, Any],
    ) -> Dict[str, Any]:
        policy_load_status = str(self._template_candidate_guard.get("policy_load_status", "failed"))
        policy_error_reason = str(self._template_candidate_guard.get("policy_error_reason", ""))
        supporting_sector = str(candidate.get("supporting_sector") or "").strip()
        rationale = str(candidate.get("rationale") or candidate.get("support_rationale") or "").strip()
        raw_support_score = candidate.get("support_score", None)
        support_score = None
        if raw_support_score not in {None, ""}:
            support_score = round(self._safe_float(raw_support_score, 0.0), 4)

        reasons: List[str] = []
        if str(candidate.get("legacy_event_broadcast") or "").strip().lower() in {"1", "true", "yes", "y", "on"} or bool(candidate.get("legacy_event_broadcast", False)):
            reasons.append("legacy_event_broadcast")
        if policy_load_status != "loaded":
            reasons.append(policy_error_reason or "missing_config")
        if not supporting_sector:
            reasons.append("missing_supporting_sector")
        if not rationale:
            reasons.append("missing_rationale")
        elif self._template_rationale_matches(rationale):
            reasons.append("template_rationale")

        ticker_allowed = policy_load_status == "loaded" and not reasons
        if ticker_allowed:
            guard_status = "ticker_allowed"
            guard_reason = ""
            source = str(candidate.get("sector_score_source") or sector_score_source or "semantic_sector").strip()
            if source == "legacy_event_broadcast":
                source = "semantic_sector"
        else:
            guard_status = "sector_only"
            guard_reason = ",".join(sorted(set(reasons))) or "sector_only"
            source = str(candidate.get("sector_score_source") or sector_score_source or "sector_marginal").strip()
            if source == "legacy_event_broadcast":
                source = "sector_marginal"
            if not source:
                source = "sector_marginal"

        if not support_score and not ticker_allowed:
            raw_support_score = None

        return {
            "ticker_allowed": ticker_allowed,
            "ticker_guard_status": guard_status,
            "ticker_guard_reason": guard_reason,
            "supporting_sector": supporting_sector,
            "rationale": rationale,
            "support_score": support_score,
            "sector_score_source": source,
            "template_guard_state": {
                "threshold_status": str(self._template_candidate_guard.get("threshold_status", "proposed")),
                "enforcement_mode": str(self._template_candidate_guard.get("enforcement_mode", "observe_only")),
                "policy_load_status": policy_load_status,
                "policy_error_reason": policy_error_reason,
                "support_score_min": self._safe_float(self._template_candidate_guard.get("support_score_min", 0.0), 0.0),
            },
        }

    def _candidate_direction(self, candidate: Dict[str, Any]) -> str:
        if "direction" not in candidate:
            return ""
        return self._normalize_direction(candidate.get("direction"))

    def _candidate_realtime_price(self, candidate: Dict[str, Any]) -> Optional[float]:
        price = self._safe_float(candidate.get("realtime_price"), 0.0)
        if price <= 0:
            return None
        return price

    def _fetch_realtime_price(self, symbol: str) -> Optional[float]:
        if not self._price_fetch_enabled:
            return None
        key = symbol.upper().strip()
        if not key:
            return None

        if self._market_data_adapter is not None:
            return self._market_data_adapter.quote_one(key)

        now = time.time()
        cached = self._price_cache.get(key)
        if cached and now - cached.get("ts", 0) < self._price_cache_ttl:
            return cached.get("price")
        url = f"{self._price_fetch_base}{key}"
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                payload = json.loads(resp.read().decode("utf-8", errors="replace"))
            quote = (((payload.get("quoteResponse") or {}).get("result") or [None])[0]) or {}
            price = quote.get("regularMarketPrice")
            if price is None:
                return None
            price_val = float(price)
            if price_val <= 0:
                return None
            self._price_cache[key] = {"price": price_val, "ts": now}
            return price_val
        except Exception:
            return None

    def _batch_prefetch_prices(self, stock_candidates: List[Dict[str, Any]]) -> Dict[str, float]:
        if not self._price_fetch_enabled or self._market_data_adapter is None:
            return {}
        symbols = []
        for candidate in stock_candidates:
            raw = str(candidate.get("symbol", "")).upper().strip()
            if raw:
                symbols.append(raw)
        if not symbols:
            return {}
        return self._market_data_adapter.quote_many(symbols)

    def _build_opportunity(
        self,
        trace_id: str,
        event_hash: str,
        semantic_trace_id: str,
        sector_name: str,
        sector_role: str,
        primary_sector: str,
        sector_direction: str,
        impact_score: float,
        sector_confidence: float,
        stock: Optional[PremiumStock],
        candidate: Dict[str, Any],
        timestamp: str,
        sector_score_source: str,
        ticker_guard: Optional[Dict[str, Any]] = None,
        prefetched_prices: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        ticker_guard = ticker_guard or {}
        event_beta = self._safe_float(candidate.get("event_beta", 1.0), 1.0)
        if stock is None:
            event_beta = max(1.0, event_beta)
        score = self._compute_score(impact_score, sector_confidence, event_beta)
        transmission = self._compute_transmission_score(candidate, impact_score, sector_confidence)
        score_100 = transmission["total"]
        grade = self._grade_signal(score_100)

        watch_threshold = self._safe_float(self.pool.rules.get("watch_score_threshold", 0.55), 0.55)
        execute_threshold = self._safe_float(self.pool.rules.get("execute_score_threshold", 0.70), 0.70)

        target_signal = sector_direction
        if score < watch_threshold:
            target_signal = "WATCH"
        elif score < execute_threshold and target_signal != "WATCH":
            # keep directional output, but risks will usually prevent direct execute
            target_signal = sector_direction

        candidate_direction = self._candidate_direction(candidate)
        supporting_sector = str(ticker_guard.get("supporting_sector") or sector_name or "").strip()
        rationale = str(ticker_guard.get("rationale") or "").strip()
        support_score = ticker_guard.get("support_score", None)
        sector_score_source = str(ticker_guard.get("sector_score_source") or sector_score_source or "sector_marginal").strip()
        ticker_guard_status = str(ticker_guard.get("ticker_guard_status") or ("ticker_allowed" if stock is not None else "sector_only")).strip()
        ticker_guard_reason = str(ticker_guard.get("ticker_guard_reason") or "")
        is_sector_only = stock is None or ticker_guard_status != "ticker_allowed"

        if is_sector_only:
            reason_text = ticker_guard_reason or "sector_only"
            sector_rationale = rationale
            if not sector_rationale or self._template_rationale_matches(sector_rationale):
                sector_rationale = f"sector-only fallback: {reason_text}"
            reasoning = sector_rationale or f"{sector_name} sector-only fallback，{reason_text}"
            if len(reasoning) > 70:
                reasoning = reasoning[:70]
            return {
                "event_hash": event_hash,
                "semantic_trace_id": semantic_trace_id,
                "trace_id": trace_id,
                "sector": sector_name,
                "sector_role": sector_role,
                "primary_sector": primary_sector,
                "sector_score_source": sector_score_source,
                "supporting_sector": supporting_sector or sector_name,
                "rationale": sector_rationale,
                "support_score": support_score,
                "ticker_guard_status": "sector_only",
                "ticker_guard_reason": reason_text,
                "signal": target_signal,
                "decision_price": None,
                "decision_price_source": "sector_only",
                "needs_price_refresh": False,
                "price_source": "sector_only",
                "risk_flags": self._build_risk_flags(PremiumStock(symbol="SECTOR_ONLY", name=sector_name, sector=sector_name, roe=15.0, market_cap_billion=500.0, liquidity_score=0.8, last_price=0.0), score, sector_confidence, candidate_direction, target_signal),
                "final_action": "WATCH",
                "reasoning": reasoning,
                "confidence": round(score, 2),
                "score_100": score_100,
                "signal_grade": grade,
                "state_machine_step": "fallback",
                "gate_reason_code": "DEFAULT_WATCH",
                "score_breakdown": transmission["score_breakdown"],
                "timestamp": timestamp,
            }

        assert stock is not None
        realtime_price = self._candidate_realtime_price(candidate)
        if realtime_price is None and prefetched_prices:
            realtime_price = prefetched_prices.get(stock.symbol)
        if realtime_price is None:
            realtime_price = self._fetch_realtime_price(stock.symbol)
        risk_flags = self._build_risk_flags(stock, score, sector_confidence, candidate_direction, target_signal)
        if realtime_price is None:
            risk_flags.append({"type": "price_data", "level": "high", "description": "缺少实时价格，需等待行情刷新"})
        final_action = self._resolve_action(target_signal, risk_flags)
        if realtime_price is None:
            final_action = "WATCH"

        reasoning = rationale or f"{sector_name}方向{sector_direction}，综合评分{score:.2f}"
        if len(reasoning) > 70:
            reasoning = reasoning[:70]

        return {
            "event_hash": event_hash,
            "semantic_trace_id": semantic_trace_id,
            "trace_id": trace_id,
            "symbol": stock.symbol,
            "name": stock.name,
            "sector": sector_name,
            "sector_role": sector_role,
            "primary_sector": primary_sector,
            "sector_score_source": sector_score_source,
            "supporting_sector": supporting_sector,
            "rationale": rationale,
            "support_score": support_score,
            "ticker_guard_status": ticker_guard_status,
            "ticker_guard_reason": ticker_guard_reason,
            "signal": target_signal,
            "entry_zone": self._build_entry_zone(realtime_price if realtime_price is not None else stock.last_price),
            "decision_price": realtime_price,
            "decision_price_source": "live" if realtime_price is not None else "missing",
            "needs_price_refresh": realtime_price is None,
            "price_source": "live" if realtime_price is not None else stock.price_source,
            "risk_flags": risk_flags,
            "final_action": final_action,
            "reasoning": reasoning,
            "confidence": round(score, 2),
            "score_100": score_100,
            "signal_grade": grade,
            "state_machine_step": "trade_admission" if grade == "A" and final_action == "EXECUTE" else "fallback",
            "gate_reason_code": "ALL_PASSED" if grade == "A" and final_action == "EXECUTE" else "DEFAULT_WATCH",
            "score_breakdown": transmission["score_breakdown"],
            "timestamp": timestamp,
        }

    def build_opportunity_update(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        trace_id = str(payload.get("trace_id") or "evt_unknown")
        event_hash = str(payload.get("event_hash") or "")
        semantic_trace_id = str(payload.get("semantic_trace_id") or "")
        schema_version = str(payload.get("schema_version", "v1.0"))
        timestamp = str(payload.get("timestamp", _utc_now_iso()))
        # Clear adapter meta at the beginning of each trace to avoid cross-trace provenance leakage.
        if self._market_data_adapter is not None and hasattr(self._market_data_adapter, "reset_meta"):
            self._market_data_adapter.reset_meta()
        self._last_provider_meta = self._empty_provider_meta()

        sectors = payload.get("sectors", [])
        stock_candidates = payload.get("stock_candidates", [])
        primary_sector = str(payload.get("primary_sector") or self._resolve_primary_sector(sectors))
        audit_sectors = self._build_audit_sectors(sectors, primary_sector)
        policy_load_status = str(self._semantic_chain_policy.get("policy_load_status", "failed"))
        policy_error_reason = str(self._semantic_chain_policy.get("policy_error_reason", ""))
        primary_sector_only = (
            policy_load_status == "loaded"
            and self._safe_bool(
                self._semantic_chain_policy.get("audit", {}).get("primary_sector_only", False),
                False,
            )
        )
        identity_incomplete = not bool(event_hash and semantic_trace_id)
        missing_identity_reasons: List[str] = []
        if not event_hash:
            missing_identity_reasons.append("missing_event_hash")
        if not semantic_trace_id:
            missing_identity_reasons.append("missing_semantic_trace_id")
        candidates_by_sector: Dict[str, List[Dict[str, Any]]] = {}
        for cand in stock_candidates:
            key = _norm_sector(self.pool.canonical_sector(cand.get("sector", "")))
            candidates_by_sector.setdefault(key, []).append(cand)

        max_per_sector = int(self.pool.rules.get("max_candidates_per_sector", 5))
        max_global_candidates = int(self._safe_float(self._gp("signal_grade.max_stock_candidates", 5), 5))
        prefetched_prices = self._batch_prefetch_prices(stock_candidates)
        opportunities: List[Dict[str, Any]] = []
        is_multi_sector = len(audit_sectors) > 1

        for sector in audit_sectors:
            sector_role = str(sector.get("role", "secondary"))
            if primary_sector_only and sector_role != "primary":
                continue
            sector_name = str(sector.get("name", "未知板块"))
            norm_sector = _norm_sector(self.pool.canonical_sector(sector_name))
            sector_direction = self._normalize_direction(sector.get("direction", "WATCH"))
            impact_score = self._safe_float(sector.get("impact_score", 0.0), 0.0)
            sector_conf = self._safe_float(sector.get("confidence", 0.0), 0.0)
            sector_score_source = str(sector.get("sector_score_source") or "semantic_sector").strip() or "semantic_sector"

            seeded_candidates = candidates_by_sector.get(norm_sector, [])
            selected_stocks = self.pool.filter_candidates(seeded_candidates)

            if is_multi_sector and sector_role == "secondary":
                fallback_candidate = seeded_candidates[0] if seeded_candidates else {}
                sector_only_guard = self._build_ticker_support_context(
                    sector_name=sector_name,
                    sector_score_source=sector_score_source,
                    candidate=fallback_candidate,
                )
                guard_reasons = [reason for reason in [sector_only_guard.get("ticker_guard_reason", ""), "secondary_sector_audit_only"] if reason]
                sector_only_guard = {
                    **sector_only_guard,
                    "ticker_allowed": False,
                    "ticker_guard_status": "sector_only",
                    "ticker_guard_reason": ",".join(sorted(set(guard_reasons))),
                }
                opportunities.append(
                    self._build_opportunity(
                        trace_id=trace_id,
                        event_hash=event_hash,
                        semantic_trace_id=semantic_trace_id,
                        sector_name=sector_name,
                        sector_role=sector_role,
                        primary_sector=primary_sector,
                        sector_direction=sector_direction,
                        impact_score=impact_score,
                        sector_confidence=sector_conf,
                        stock=None,
                        candidate=fallback_candidate,
                        timestamp=timestamp,
                        sector_score_source=sector_only_guard["sector_score_source"],
                        ticker_guard=sector_only_guard,
                        prefetched_prices=prefetched_prices,
                    )
                )
                continue

            if not selected_stocks:
                selected_stocks = self.pool.pick_by_sector(sector_name, limit=max_per_sector)
                seeded_candidates = [
                    {
                        "symbol": s.symbol,
                        "sector": s.sector,
                        "direction": sector_direction,
                        "event_beta": 1.0,
                        "supporting_sector": sector_name,
                        "rationale": f"{s.symbol} is a sector representative for {sector_name}.",
                        "sector_score_source": "semantic_sector",
                        "source": "pool_fallback",
                    }
                    for s in selected_stocks
                ]

            sector_valid_ticker_emitted = False
            sector_fallback_candidate: Dict[str, Any] = {}
            for stock in selected_stocks[:max_per_sector]:
                match_candidate = next((c for c in seeded_candidates if str(c.get("symbol", "")).upper() == stock.symbol), {})
                ticker_guard = self._build_ticker_support_context(
                    sector_name=sector_name,
                    sector_score_source=sector_score_source,
                    candidate=match_candidate,
                )
                if not ticker_guard["ticker_allowed"]:
                    if not sector_fallback_candidate:
                        sector_fallback_candidate = dict(match_candidate or {})
                    continue
                opportunities.append(
                    self._build_opportunity(
                        trace_id=trace_id,
                        event_hash=event_hash,
                        semantic_trace_id=semantic_trace_id,
                        sector_name=sector_name,
                        sector_role=str(sector.get("role", "secondary")),
                        primary_sector=primary_sector,
                        sector_direction=sector_direction,
                        impact_score=impact_score,
                        sector_confidence=sector_conf,
                        stock=stock,
                        candidate=match_candidate,
                        timestamp=timestamp,
                        sector_score_source=ticker_guard["sector_score_source"],
                        ticker_guard=ticker_guard,
                        prefetched_prices=prefetched_prices,
                    )
                )
                sector_valid_ticker_emitted = True

            if not sector_valid_ticker_emitted:
                fallback_candidate = sector_fallback_candidate or (seeded_candidates[0] if seeded_candidates else {})
                sector_only_guard = self._build_ticker_support_context(
                    sector_name=sector_name,
                    sector_score_source=sector_score_source,
                    candidate=fallback_candidate,
                )
                opportunities.append(
                    self._build_opportunity(
                        trace_id=trace_id,
                        event_hash=event_hash,
                        semantic_trace_id=semantic_trace_id,
                        sector_name=sector_name,
                        sector_role=str(sector.get("role", "secondary")),
                        primary_sector=primary_sector,
                        sector_direction=sector_direction,
                        impact_score=impact_score,
                        sector_confidence=sector_conf,
                        stock=None,
                        candidate=fallback_candidate,
                        timestamp=timestamp,
                        sector_score_source=sector_only_guard["sector_score_source"],
                        ticker_guard=sector_only_guard,
                        prefetched_prices=prefetched_prices,
                    )
                )

        opportunities.sort(key=lambda x: x.get("score_100", 0.0), reverse=True)
        opportunities = opportunities[: max(0, max_global_candidates)]

        grade_a = 0
        grade_b = 0
        grade_c = 0
        for opp in opportunities:
            grade = str(opp.get("signal_grade", "C")).upper()
            if grade == "A":
                grade_a += 1
            elif grade == "B":
                grade_b += 1
            else:
                grade_c += 1

        state_out = {
            "action": "WATCH",
            "state_machine_step": "fallback",
            "gate_reason_code": "DEFAULT_WATCH",
            "gate_reason": "fallback default",
        }
        if evaluate_state is not None:
            asset_validation_raw = payload.get("asset_validation", {})
            if not isinstance(asset_validation_raw, dict):
                asset_validation_raw = {}
            asset_validation_score = self._safe_float(asset_validation_raw.get("score", 0.0), 0.0)
            gate_event = {
                "trace_id": trace_id,
                "schema_version": schema_version,
                "news_timestamp": timestamp,
                "mixed_regime": bool(payload.get("mixed_regime", False)),
                "asset_validation": {"score": asset_validation_score},
                "risk_blocked": bool(payload.get("risk_blocked", False)),
            }
            state_out = evaluate_state(gate_event, self._gate_policy)

        for opp in opportunities:
            opp["state_machine_step"] = state_out["state_machine_step"]
            opp["gate_reason_code"] = state_out["gate_reason_code"]

        self._last_provider_meta = self._snapshot_provider_meta()

        return {
            "type": "opportunity_update",
            "event_hash": event_hash,
            "semantic_trace_id": semantic_trace_id,
            "trace_id": trace_id,
            "schema_version": schema_version,
            "primary_sector": primary_sector,
            "audit_sectors": audit_sectors,
            "identity_incomplete": identity_incomplete,
            "missing_identity_reasons": missing_identity_reasons,
            "strict_join_ready": not identity_incomplete,
            "policy_state": {
                "threshold_status": str(self._semantic_chain_policy.get("threshold_status", "proposed")),
                "enforcement_mode": str(self._semantic_chain_policy.get("enforcement_mode", "observe_only")),
                "policy_load_status": policy_load_status,
                "policy_error_reason": policy_error_reason,
                "primary_sector_only": primary_sector_only,
            },
            "template_guard_state": {
                "threshold_status": str(self._template_candidate_guard.get("threshold_status", "proposed")),
                "enforcement_mode": str(self._template_candidate_guard.get("enforcement_mode", "observe_only")),
                "policy_load_status": str(self._template_candidate_guard.get("policy_load_status", "failed")),
                "policy_error_reason": str(self._template_candidate_guard.get("policy_error_reason", "")),
                "support_score_min": self._safe_float(self._template_candidate_guard.get("support_score_min", 0.0), 0.0),
            },
            "opportunities": opportunities,
            "timestamp": timestamp,
            "action": state_out["action"],
            "state_machine_step": state_out["state_machine_step"],
            "gate_reason_code": state_out["gate_reason_code"],
            "gate_reason": state_out["gate_reason"],
            "stats": {
                "opportunity_count": len(opportunities),
                "premium_pool_only": True,
                "grade_counts": {
                    "A": grade_a,
                    "B": grade_b,
                    "C": grade_c,
                },
            },
            "provider_meta": dict(self._last_provider_meta),
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
