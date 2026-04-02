#!/usr/bin/env python3
"""
Intel modules for EDT (T2.1 - T2.4).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from edt_module_base import EDTModule, ModuleInput, ModuleOutput, ModuleStatus


def _default_config_path() -> str:
    return str(Path(__file__).resolve().parent.parent / "configs" / "edt-modules-config.yaml")


def _host_matches_domain(host: str, domain: str) -> bool:
    """Strict domain matching to avoid substring spoofing."""
    normalized_host = host.lower().strip(".")
    normalized_domain = domain.lower().strip(".")
    return normalized_host == normalized_domain or normalized_host.endswith(f".{normalized_domain}")


class EventCapture(EDTModule):
    """Capture raw event and provide first-pass category."""

    def __init__(self, config_path: Optional[str] = None):
        super().__init__("EventCapture", "1.0.0", config_path or _default_config_path())

    def validate_input(self, input_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        required = ["headline", "source", "timestamp"]
        for key in required:
            if key not in input_data:
                return False, f"Missing required field: {key}"
        return True, None

    def execute(self, input_data: ModuleInput) -> ModuleOutput:
        raw = input_data.raw_data
        headline = str(raw["headline"]).lower()
        keywords = [k.lower() for k in self._get_config("modules.EventCapture.params.keywords", [])]
        captured = any(k in headline for k in keywords) or float(raw.get("vix", 0)) >= float(
            self._get_config("modules.EventCapture.params.vix_trigger", 20)
        )

        # Minimal category inference for skeleton.
        category = "E"
        if any(k in headline for k in ("tariff", "trade", "关税")):
            category = "C"
        elif any(k in headline for k in ("war", "sanction", "地缘")):
            category = "D"
        elif any(k in headline for k in ("virus", "疫情")):
            category = "B"
        elif any(k in headline for k in ("fed", "rate", "policy", "fomc")):
            category = "E"

        return ModuleOutput(
            status=ModuleStatus.SUCCESS,
            data={
                "captured": captured,
                "headline": raw["headline"],
                "source": raw["source"],
                "timestamp": raw["timestamp"],
                "category_hint": category,
                "matched_keywords": [k for k in keywords if k in headline],
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
        vix = float(raw.get("vix", 0))
        vix_change_pct = float(raw.get("vix_change_pct", 0))
        spx_move_pct = float(raw.get("spx_move_pct", 0))
        sector_move_pct = float(raw.get("sector_move_pct", 0))

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

