#!/usr/bin/env python3
"""
Intel modules for EDT (T2.1 - T2.4).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from edt_module_base import EDTModule, ModuleInput, ModuleOutput, ModuleStatus
from ai_semantic_analyzer import SemanticAnalyzer


logger = logging.getLogger(__name__)


def _default_config_path() -> str:
    return str(Path(__file__).resolve().parent.parent / "configs" / "edt-modules-config.yaml")


def _host_matches_domain(host: str, domain: str) -> bool:
    """Strict domain matching to avoid substring spoofing."""
    normalized_host = host.lower().strip(".")
    normalized_domain = domain.lower().strip(".")
    return normalized_host == normalized_domain or normalized_host.endswith(f".{normalized_domain}")


def _keyword_matches(text: str, keyword: str) -> bool:
    """Match a configured keyword as a token or phrase, not a loose substring."""
    needle = keyword.strip().lower()
    haystack = text.lower()
    if not needle:
        return False
    if " " in needle or any(ord(ch) > 127 for ch in needle):
        return needle in haystack
    tokens = set()
    current = []
    for ch in haystack:
        if ch.isalnum():
            current.append(ch)
        else:
            if current:
                tokens.add("".join(current))
                current = []
    if current:
        tokens.add("".join(current))
    return needle in tokens


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


class EventCapture(EDTModule):
    """Capture raw event and provide first-pass category."""

    def __init__(self, config_path: Optional[str] = None):
        super().__init__("EventCapture", "1.0.0", config_path or _default_config_path())
        self.semantic = None
        self._semantic_init_error = ""
        try:
            self.semantic = SemanticAnalyzer(config_path=config_path)
        except Exception as exc:
            self._semantic_init_error = f"{type(exc).__name__}: {exc}"
            logger.warning("EventCapture semantic analyzer init failed: %s", self._semantic_init_error)

    def validate_input(self, input_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        required = ["headline", "source", "timestamp"]
        for key in required:
            if key not in input_data:
                return False, f"Missing required field: {key}"
        return True, None

    def execute(self, input_data: ModuleInput) -> ModuleOutput:
        raw = input_data.raw_data
        headline_text = str(raw["headline"])
        headline = headline_text.lower()
        keywords = [k.lower() for k in self._get_config("modules.EventCapture.params.keywords", [])]
        
        # 关键词匹配才触发，VIX仅作为放大器（不单独触发）
        keyword_matched = any(_keyword_matches(headline, k) for k in keywords)
        vix_level = _safe_float(raw.get("vix"), 0.0)
        vix_amplify_threshold = float(self._get_config("modules.EventCapture.params.vix_amplify_threshold", 20))
        vix_amplify = vix_level >= vix_amplify_threshold
        
        ai_verdict = "not_called"
        ai_confidence = 0
        ai_reason = "keyword_rule_hit"
        capture_source = "rules"
        captured = True
        matched_keywords = []

        raw_text = str(raw.get("raw_text", "") or "")
        
        # 关键词分数定义
        KEYWORD_SCORES = {
            # 国家 (80分)
            "US": 80, "USA": 80, "America": 80, "American": 80,
            "Iran": 80, "Iranian": 80,
            "Israel": 80, "Israeli": 80,
            "Russia": 80, "Russian": 80,
            "China": 80, "Chinese": 80,
            "Ukraine": 80, "Ukrainian": 80,
            "Taiwan": 80, "Taiwanese": 80,
            "North Korea": 80, "Kim": 80,
            "美国": 80, "伊朗": 80, "以色列": 80, "俄罗斯": 80,
            "中国": 80, "乌克兰": 80, "台湾": 80, "朝鲜": 80,
            
            # 重大事件 (80分)
            "war": 80, " Wars ": 80, " Wars": 80,
            "missile": 80, "missiles": 80, "attack": 80, "strike": 80,
            "tariff": 80, "trade war": 80,
            "pandemic": 80, "epidemic": 80, "outbreak": 80,
            "sanction": 80, "embargo": 80,
            "nuclear": 80, "核": 80,
            "战争": 80, "导弹": 80, "袭击": 80,
            "关税": 80, "贸易战": 80, "疫情": 80, "病毒": 80, "制裁": 80,
            
            # 重要 (70分)
            "rate": 70, "interest rate": 70, "fed": 70, "FOMC": 70,
            "cut": 70, "hike": 70, "easing": 70, "tightening": 70,
            "earnings": 70, "revenue": 70, "profit": 70, "quarterly": 70,
            "QE": 70, "quantitative": 70,
            "降息": 70, "加息": 70, "央行": 70, "利率": 70,
            "财报": 70, "营收": 70, "盈利": 70, "季度": 70,
            
            # 情绪/市场波动 (60分)
            "rise": 60, "fall": 60, "gain": 60, "loss": 60,
            "up": 60, "down": 60, "surge": 60, "drop": 60,
            "bullish": 60, "bearish": 60,
            "soar": 60, "plunge": 60, "crash": 60, "rally": 60,
            "skyrocket": 60, "tumble": 60, "rebound": 60,
            "暴涨": 60, "大涨": 60, "飙升": 60, "创新高": 60,
            "暴跌": 60, "大跌": 60, "崩盘": 60, "跳水": 60, "闪崩": 60,
            "恐慌": 60, "上涨": 60, "利好": 60, "突破": 60, "下跌": 60,
            "大跌": 60, "挫败": 60,
        }
        
        raw_text = str(raw.get("raw_text", "") or "")
        
        # AI 是否可用
        ai_available = self.semantic is not None
        
        semantic_out = None
        
        if ai_available:
            try:
                semantic_out = self.semantic.analyze(headline_text, raw_text)
            except Exception as exc:
                logger.warning("EventCapture semantic analyze failed: %s", exc)
                semantic_out = None
        
        # 额外加分：关键词命中 +20 (只有AI成功时加)
        bonus = 0
        if keyword_matched:
            matched_keywords = [k for k in keywords if _keyword_matches(headline, k)]
            if ai_available and semantic_out:
                bonus = min(20, len(matched_keywords) * 10)
        
        # 决定使用 AI 结果还是关键词回退
        if semantic_out and semantic_out.get("confidence", 0) > 0:
            # AI 成功: AI分 + keyword bonus
            ai_verdict = str(semantic_out.get("verdict", "abstain") or "abstain")
            base_confidence = _safe_float(semantic_out.get("confidence"), 60)
            ai_reason = f"ai({semantic_out.get('reason', '')})"
            if bonus > 0:
                ai_reason += f"+keyword_bonus({bonus})"
            use_ai = True
            event_type = semantic_out.get("event_type", "unknown")
            sentiment = semantic_out.get("sentiment", "neutral")
        else:
            # AI 失败: 用关键词本身的分数，没有 bonus
            ai_verdict = "keyword_fallback"
            # 取匹配的关键词中的最高分
            max_kw_score = 60
            for k in matched_keywords if keyword_matched else []:
                kw_score = KEYWORD_SCORES.get(k.lower(), 60)
                max_kw_score = max(max_kw_score, kw_score)
            base_confidence = max_kw_score
            ai_reason = f"keyword_fallback(score={base_confidence})"
            use_ai = False
            
            # 关键词判断 event_type
            event_type = "unknown"
            if any(_keyword_matches(headline, k) for k in ("tariff", "关税", "贸易战", "出口管制", "进口限制")):
                event_type = "tariff"
            elif any(_keyword_matches(headline, k) for k in ("war", "战争", "地缘", "制裁", "导弹", "袭击")):
                event_type = "geo_political"
            elif any(_keyword_matches(headline, k) for k in ("疫情", "病毒", "流感")):
                event_type = "pandemic"
            elif any(_keyword_matches(headline, k) for k in ("降息", "加息", "央行", "利率", "QE", "量化宽松")):
                event_type = "monetary"
            elif any(_keyword_matches(headline, k) for k in ("财报", "营收", "盈利", "季度")):
                event_type = "earnings"
            
            # 关键词判断 sentiment
            sentiment = "neutral"
            if any(_keyword_matches(headline, k) for k in ("关税", "war", "战争", "制裁", "疫情", "导弹", "加息")):
                sentiment = "negative"
            elif any(_keyword_matches(headline, k) for k in ("降息", "QE", "上涨", "利好")):
                sentiment = "positive"
        
        ai_confidence = min(100, base_confidence + bonus)
        
        # 关键词优先判断 category
        category = "E"
        if any(_keyword_matches(headline, k) for k in ("tariff", "trade war", "关税", "进口限制", "出口管制")):
            category = "C"
        elif any(_keyword_matches(headline, k) for k in ("war", "sanction", "地缘")):
            category = "D"
        elif any(_keyword_matches(headline, k) for k in ("virus", "疫情")):
            category = "B"
        elif any(_keyword_matches(headline, k) for k in ("fed", "rate", "policy", "fomc", "央行", "降息", "加息")):
            category = "E"
        
        # event_type: AI有就用，没有就用关键词判断
        if use_ai and semantic_out:
            event_type = semantic_out.get("event_type", "unknown")
        else:
            # 关键词判断 event_type
            event_type = "unknown"
            if any(_keyword_matches(headline, k) for k in ("tariff", "关税", "贸易战", "出口管制")):
                event_type = "tariff"
            elif any(_keyword_matches(headline, k) for k in ("war", "战争", "地缘", "制裁", "导弹", "袭击")):
                event_type = "geo_political"
            elif any(_keyword_matches(headline, k) for k in ("疫情", "病毒", "流感")):
                event_type = "pandemic"
            elif any(_keyword_matches(headline, k) for k in ("降息", "加息", "央行", "利率", "QE", "量化宽松")):
                event_type = "monetary"
            elif any(_keyword_matches(headline, k) for k in ("财报", "营收", "盈利", "季度")):
                event_type = "earnings"
        
        ai_reason = (f"ai({semantic_out.get('reason', '')})" + (f"+keyword_bonus({bonus})" if bonus > 0 else "")) if (not use_ai and semantic_out) else ai_reason
        
        threshold = _safe_float(
            self._get_config(
                "modules.EventCapture.params.ai_confidence_threshold",
                self._get_config("runtime.semantic.min_confidence", 70),
            ),
            70.0,
        )

        # 捕获判断：AI hit 或者关键词匹配都捕获
        if keyword_matched:
            captured = True
            capture_source = "rules"
        elif ai_verdict == "hit" and ai_confidence >= threshold:
            captured = True
            capture_source = "ai"
        else:
            captured = False
            capture_source = "none"
        
        # 如果是关键词回退，加 reason
        if not use_ai and keyword_matched:
            ai_reason = f"keyword_fallback({event_type},{sentiment})+keyword_bonus({bonus})"

        return ModuleOutput(
            status=ModuleStatus.SUCCESS,
            data={
                "captured": captured,
                "capture_source": capture_source,
                "ai_verdict": ai_verdict,
                "ai_confidence": ai_confidence,
                "base_confidence": base_confidence,
                "keyword_bonus": bonus,
                "ai_reason": ai_reason,
                "vix_amplify": vix_amplify,
                "vix_level": vix_level,
                "headline": raw["headline"],
                "source": raw["source"],
                "timestamp": raw["timestamp"],
                "category_hint": category,
                "event_type": event_type,
                "sentiment": sentiment,
                "matched_keywords": matched_keywords,
            },
        )


class SourceRankerModule(EDTModule):
    """Rank source into A/B/C and fast-track eligibility."""

    def __init__(self, config_path: Optional[str] = None):
        super().__init__("SourceRanker", "1.0.0", config_path or _default_config_path())

    def validate_input(self, input_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        if "source_url" not in input_data:
            return False, "Missing required field: source_url"
        return True, None

    def execute(self, input_data: ModuleInput) -> ModuleOutput:
        raw = input_data.raw_data
        source_url = raw["source_url"]
        host = urlparse(source_url).netloc.lower()
        host = host[4:] if host.startswith("www.") else host

        ranks = self._get_config("modules.SourceRanker.params.ranks", {})
        rank = "C"
        rank_detail = "Unknown source"
        for rk in ("A", "B", "C"):
            domains = [d.lower() for d in ranks.get(rk, [])]
            if any(_host_matches_domain(host, d) for d in domains):
                rank = rk
                rank_detail = f"Matched {rk}-rank list"
                break

        is_fast_track = rank == "B"
        expires_at = None
        if is_fast_track:
            timeout = int(self._get_config("modules.SourceRanker.params.fast_track_timeout", 5400))
            expires_at = (datetime.now(timezone.utc) + timedelta(seconds=timeout)).isoformat()

        return ModuleOutput(
            status=ModuleStatus.SUCCESS,
            data={
                "rank": rank,
                "rank_detail": rank_detail,
                "is_fast_track_eligible": is_fast_track,
                "fast_track_expires_at": expires_at,
                "needs_escalation": rank in ("B", "C"),
                "reasoning": f"host={host}, rank={rank}",
            },
        )


class SeverityEstimator(EDTModule):
    """Estimate severity E0-E4 from market stress signals."""

    def __init__(self, config_path: Optional[str] = None):
        super().__init__("SeverityEstimator", "1.0.0", config_path or _default_config_path())

    def execute(self, input_data: ModuleInput) -> ModuleOutput:
        raw = input_data.raw_data
        vix = _safe_float(raw.get("vix"), 0.0)
        vix_change_pct = _safe_float(raw.get("vix_change_pct"), 0.0)
        spx_move_pct = _safe_float(raw.get("spx_move_pct"), 0.0)
        sector_move_pct = _safe_float(raw.get("sector_move_pct"), 0.0)

        p = self._get_config("modules.SeverityEstimator.params", {})
        if vix >= float(p.get("vix_e4_absolute", 40)) or spx_move_pct >= float(p.get("spx_vol_e4_pct", 3.0)):
            sev, a0 = "E4", 40
        elif (
            vix >= float(p.get("vix_e3_absolute", 25))
            or vix_change_pct >= float(p.get("vix_change_e3_pct", 30))
            or spx_move_pct >= float(p.get("spx_vol_e3_pct", 2.5))
        ):
            sev, a0 = "E3", 30
        elif sector_move_pct >= float(p.get("etf_vol_e2_pct", 5.0)):
            sev, a0 = "E2", 20
        elif vix > 0:
            sev, a0 = "E1", 10
        else:
            sev, a0 = "E0", 0

        return ModuleOutput(status=ModuleStatus.SUCCESS, data={"severity": sev, "A0": a0})


class EventObjectifier(EDTModule):
    """Build normalized event object from capture/rank/severity outputs."""

    def __init__(self, config_path: Optional[str] = None):
        super().__init__("EventObjectifier", "1.0.0", config_path or _default_config_path())

    def execute(self, input_data: ModuleInput) -> ModuleOutput:
        raw = input_data.raw_data
        category = raw.get("category", "E")
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        seq = int(raw.get("sequence", 1))
        version = raw.get("version", "1.0")
        event_id = f"ME-{category}-{date_str}-{seq:03d}.V{version}"

        obj = {
            "event_id": event_id,
            "category": category,
            "source_rank": raw.get("source_rank", "C"),
            "severity": raw.get("severity", "E1"),
            "lifecycle_state": raw.get("lifecycle_state", "Detected"),
            "catalyst_state": raw.get("catalyst_state", "first_impulse"),
            "confidence": float(raw.get("confidence", 70)),
            "headline": raw.get("headline", ""),
            "source_url": raw.get("source_url", ""),
            "detected_at": raw.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "version": version,
        }
        return ModuleOutput(status=ModuleStatus.SUCCESS, data=obj)


class IntelPipeline:
    """Pipeline: capture -> source rank -> severity -> event object."""

    def __init__(self):
        self.capture = EventCapture()
        self.ranker = SourceRankerModule()
        self.severity = SeverityEstimator()
        self.objectifier = EventObjectifier()

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        c = self.capture.run(payload)
        r = self.ranker.run({"source_url": payload["source"], "headline": payload.get("headline", "")})
        s = self.severity.run(payload)
        o = self.objectifier.run(
            {
                "headline": payload.get("headline", ""),
                "source_url": payload.get("source", ""),
                "timestamp": payload.get("timestamp"),
                "category": c.data.get("category_hint", "E"),
                "source_rank": r.data.get("rank", "C"),
                "severity": s.data.get("severity", "E1"),
                "sequence": payload.get("sequence", 1),
                "confidence": payload.get("confidence", 75),
            }
        )
        return {"capture": c.data, "source_rank": r.data, "severity": s.data, "event_object": o.data}


if __name__ == "__main__":
    out = IntelPipeline().run(
        {
            "headline": "Fed announces emergency liquidity action after tariff shock",
            "source": "https://www.reuters.com/markets/us/example",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "vix": 31,
            "vix_change_pct": 32,
            "spx_move_pct": 2.1,
            "sector_move_pct": 4.0,
            "sequence": 1,
        }
    )
    import json

    print(json.dumps(out, indent=2, ensure_ascii=False))
