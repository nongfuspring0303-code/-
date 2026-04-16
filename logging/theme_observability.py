import json
import logging
from typing import Dict, Any

# 核心SLI指标（按文档原文）
SLO_SPEC = {
    "theme_mapping_success_rate": ">= 95%",
    "degraded_output_rate": "<= 10%",
    "replay_consistency_rate": ">= 99%",
    "e2e_latency_ms": "由部署环境定义",
    "safe_to_consume_false_rate": "持续监控"
}

class ThemeObservabilityLogger:
    @staticmethod
    def log_observability_event(theme_output: Dict[str, Any], trace_id: str, route_result: str, latency_ms: int = 0):
        """
        Record standard Observability & SLO metrics for theme engine (A2.5).
        """
        obs = {
            "event_id": theme_output.get("event_id", trace_id),
            "contract_version": theme_output.get("contract_version", "v1.0"),
            "config_version": "v1.0",
            "route_result": route_result,
            "mapping_result": "success" if theme_output.get("primary_theme", "unknown") != "unknown" else "failed",
            "validation_result": "passed" if theme_output.get("safe_to_consume", False) else "failed",
            "state_result": theme_output.get("current_state", "DEAD"),
            "trade_grade": theme_output.get("trade_grade", "D"),
            "fallback_reason": theme_output.get("fallback_reason", "none"),
            "safe_to_consume": theme_output.get("safe_to_consume", False),
            "e2e_latency_ms": latency_ms
        }
        
        logger = logging.getLogger("theme_observability")
        logger.info("THEME_OBSERVABILITY_LOG: %s", json.dumps(obs))
        
        # P3: Observability anomaly (latency too high or missing fields)
        if latency_ms >= 5000:
            logger.warning("SLO ALERT [P3]: Observability anomaly - High latency detected (%sms)", latency_ms)

        # SLI & SLO monitoring rules (P1/P2)
        if not obs["safe_to_consume"]:
            # Critical contract issue or routing missing
            if obs["fallback_reason"] in ["CONFIG_MISSING", "MAINCHAIN_MISSING", "THEME_MAPPING_FAILED"]:
                logger.error("SLO ALERT [P1]: Critical failure to consume theme. Reason: %s", obs["fallback_reason"])
            else:
                logger.warning("SLO ALERT [P2]: Degraded theme output. Reason: %s", obs["fallback_reason"])
                
        return obs
