#!/usr/bin/env python3
"""
Member B transmission path router.

This module emits the canonical transmission_paths envelope and preserves a
complete impact_chain for downstream consumers without entering any state
machine or trade-admission logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from scripts.config_center import ConfigCenter
from scripts.edt_module_base import EDTModule, ModuleInput, ModuleOutput, ModuleStatus


class PathRouter(EDTModule):
    """Build the canonical transmission path envelope."""

    PATH_ORDER = ("fundamental", "asset_pricing", "narrative")
    PATH_DEFAULTS = {
        "fundamental": {"horizon": "1-5D", "persistence": "medium", "base_confidence": 68.0},
        "asset_pricing": {"horizon": "intraday", "persistence": "fast", "base_confidence": 64.0},
        "narrative": {"horizon": "multiweek", "persistence": "slow", "base_confidence": 60.0},
    }
    PATH_KEYWORDS = {
        "fundamental": {
            "positive": ("rates", "earnings", "policy", "growth", "macro", "guidance", "fundamental"),
            "negative": ("fraud", "default", "recession", "cuts", "weakness"),
        },
        "asset_pricing": {
            "positive": ("price", "liquidity", "spread", "volatility", "usd", "market", "flow"),
            "negative": ("gap", "slippage", "stress", "illiquid", "drawdown"),
        },
        "narrative": {
            "positive": ("headline", "sentiment", "buzz", "rumor", "story", "narrative"),
            "negative": ("denial", "backlash", "confusion", "noise"),
        },
    }

    def __init__(self, config_path: Optional[str] = None):
        super().__init__("PathRouter", "1.0.0", config_path)
        self.repo_root = Path(__file__).resolve().parents[2]
        self.metric_dictionary_path = self.repo_root / "configs" / "metric_dictionary.yaml"
        self.config_center = ConfigCenter(config_path=config_path)
        self.config_center.register("metric_dictionary", self.metric_dictionary_path)

    def validate_input(self, input_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        event_id = input_data.get("event_id")
        if not isinstance(event_id, str) or not event_id.strip():
            return False, "Missing required field: event_id"
        return True, None

    def _metric_dictionary(self) -> Dict[str, Any]:
        metrics = self.config_center.get_registered("metric_dictionary", {})
        return metrics if isinstance(metrics, dict) else {}

    @staticmethod
    def _round(value: Any, precision: int) -> float:
        try:
            return round(float(value), precision)
        except (TypeError, ValueError):
            return round(0.0, precision)

    @staticmethod
    def _clip(value: float, lower: float, upper: float) -> float:
        return max(lower, min(upper, value))

    @staticmethod
    def _normalize_sequence(items: Any) -> List[Dict[str, Any]]:
        if not isinstance(items, list):
            return []
        return [item for item in items if isinstance(item, dict)]

    @staticmethod
    def _text_blob(raw: Dict[str, Any]) -> str:
        parts: List[str] = []
        for key in ("headline", "summary", "event_text", "description"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
        return " ".join(parts).lower()

    @staticmethod
    def _asset_slug(raw: Dict[str, Any]) -> str:
        value = raw.get("event_id") or raw.get("headline") or raw.get("summary") or "event"
        slug = str(value).strip().lower().replace(" ", "_")
        return slug or "event"

    def _precision(self) -> int:
        standards = self._metric_dictionary().get("standards", {})
        return int(standards.get("default_rounding_decimals", 2))

    def _topic_hint(self, raw: Dict[str, Any]) -> str:
        text = self._text_blob(raw)
        if "rates" in text or "policy" in text:
            return "rates"
        if "liquidity" in text or "spread" in text:
            return "liquidity"
        if "headline" in text or "sentiment" in text or "narrative" in text:
            return "headline"
        if "growth" in text or "earnings" in text:
            return "growth"
        return self._asset_slug(raw)

    def _keyword_bias(self, raw: Dict[str, Any], path_type: str) -> float:
        text = self._text_blob(raw)
        keywords = self.PATH_KEYWORDS.get(path_type, {})
        positive = sum(text.count(token) for token in keywords.get("positive", ()))
        negative = sum(text.count(token) for token in keywords.get("negative", ()))
        return float(positive - negative)

    def _default_blueprint(self, raw: Dict[str, Any], path_type: str) -> Dict[str, Any]:
        topic = self._topic_hint(raw)
        event_id = str(raw.get("event_id", "event"))
        path_id = f"{event_id}:{path_type}"
        nodes = [
            event_id,
            f"{path_type}:anchor",
            topic,
        ]
        edges = [
            {"source": nodes[0], "target": nodes[1], "relation": "initiates"},
            {"source": nodes[1], "target": nodes[2], "relation": "translates"},
        ]
        defaults = self.PATH_DEFAULTS[path_type]
        return {
            "path_id": path_id,
            "path_name": f"{path_type}_transmission",
            "path_type": path_type,
            "horizon": defaults["horizon"],
            "persistence": defaults["persistence"],
            "nodes": nodes,
            "edges": edges,
        }

    @staticmethod
    def _edge_endpoints(edge: Dict[str, Any]) -> tuple[str, str]:
        return str(edge.get("source", "")), str(edge.get("target", ""))

    def _is_degraded(self, nodes: Sequence[Any], edges: Sequence[Any]) -> tuple[bool, List[str]]:
        reasons: List[str] = []
        if not isinstance(nodes, list) or len(nodes) < 2:
            reasons.append("missing_nodes")
        if not isinstance(edges, list) or len(edges) < 1:
            reasons.append("missing_edges")
        if not reasons:
            node_set = {str(node) for node in nodes if str(node).strip()}
            for edge in edges:
                if not isinstance(edge, dict):
                    reasons.append("invalid_edge")
                    break
                source, target = self._edge_endpoints(edge)
                if source not in node_set or target not in node_set:
                    reasons.append("edge_endpoint_mismatch")
                    break
        return bool(reasons), reasons

    def _direction(self, bias: float) -> str:
        if bias > 0:
            return "positive"
        if bias < 0:
            return "negative"
        return "neutral"

    def _confidence(self, path_type: str, bias: float, degraded: bool, precision: int) -> float:
        defaults = self.PATH_DEFAULTS[path_type]
        confidence = defaults["base_confidence"] + bias * 3.0
        if degraded:
            confidence -= 8.0
        return self._round(self._clip(confidence, 0.0, 100.0), precision)

    def _merge_blueprint(self, raw: Dict[str, Any], path_type: str, blueprint: Optional[Dict[str, Any]], precision: int) -> tuple[Dict[str, Any], Dict[str, Any]]:
        base = self._default_blueprint(raw, path_type)
        provided = blueprint if isinstance(blueprint, dict) else {}
        nodes = provided.get("nodes") if isinstance(provided.get("nodes"), list) else base["nodes"]
        edges = provided.get("edges") if isinstance(provided.get("edges"), list) else base["edges"]
        degraded, reasons = self._is_degraded(nodes, edges)
        bias = self._keyword_bias(raw, path_type)
        confidence = self._confidence(path_type, bias, degraded, precision)
        path = {
            "path_id": str(provided.get("path_id") or base["path_id"]),
            "path_name": str(provided.get("path_name") or provided.get("name") or base["path_name"]),
            "path_type": path_type,
            "horizon": str(provided.get("horizon") or base["horizon"]),
            "persistence": str(provided.get("persistence") or base["persistence"]),
            "confidence": confidence,
            "nodes": nodes,
            "edges": edges,
            "status": "degraded" if degraded else "active",
        }
        impact_chain_item = {
            "full_path": " -> ".join(str(node) for node in nodes) if isinstance(nodes, list) and nodes else path["path_id"],
            "score": confidence,
            "direction": self._direction(bias),
            "reason": "degraded:" + ",".join(reasons) if reasons else "complete",
        }
        return path, impact_chain_item

    def _blueprint_lookup(self, raw: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        blueprints = raw.get("path_blueprints")
        lookup: Dict[str, Dict[str, Any]] = {}
        if isinstance(blueprints, list):
            for item in blueprints:
                if isinstance(item, dict):
                    path_type = str(item.get("path_type", "")).strip()
                    if path_type and path_type not in lookup:
                        lookup[path_type] = item
        elif isinstance(blueprints, dict):
            for key, item in blueprints.items():
                if isinstance(item, dict):
                    path_type = str(item.get("path_type") or key).strip()
                    if path_type and path_type not in lookup:
                        lookup[path_type] = item
        return lookup

    def execute(self, input_data: ModuleInput) -> ModuleOutput:
        raw = input_data.raw_data
        precision = self._precision()
        blueprints = self._blueprint_lookup(raw)

        paths: List[Dict[str, Any]] = []
        impact_chain: List[Dict[str, Any]] = []
        degraded_count = 0
        for path_type in self.PATH_ORDER:
            path, impact = self._merge_blueprint(raw, path_type, blueprints.get(path_type), precision)
            paths.append(path)
            impact_chain.append(impact)
            if path["status"] == "degraded":
                degraded_count += 1

        return ModuleOutput(
            status=ModuleStatus.SUCCESS,
            data={
                "event_id": raw.get("event_id"),
                "schema_version": raw.get("schema_version", "v1.0"),
                "transmission_paths": paths,
                "impact_chain": impact_chain,
            },
            metadata={
                "path_count": len(paths),
                "degraded_count": degraded_count,
                "schema_version": raw.get("schema_version", "v1.0"),
            },
        )
