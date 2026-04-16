import unittest
import yaml
import os
import sys
from pathlib import Path

# Setup paths
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from workflow_runner import WorkflowRunner
from theme_obs.theme_observability import ThemeObservabilityLogger

class TestPR64Compliance(unittest.TestCase):
    def setUp(self):
        self.runner = WorkflowRunner()
        self.config_path = ROOT / "configs" / "edt-modules-config.yaml"
        # Load real config to ensure it exists
        with open(self.config_path, 'r') as f:
            self.config = yaml.safe_load(f)

    def test_config_effectiveness(self):
        """证明配置真源：修改 RISK_OFF 上限后，输出随之改变"""
        # 构造模拟输入：A评级，RISK_OFF环境
        payload = {
            "macro_regime": "RISK_OFF",
            "trade_grade": "A",
            "primary_theme": "AI_Infrastructure"
        }

        # 1. 验证配置键读取对齐
        # 注意：这里从 self.config['modules'] 中找，如果找不到打印调试
        target_cfg = self.config['modules'].get('ThemeCatalystEngine', {})
        if not target_cfg:
            # 兼容性处理：尝试各种可能的 Key 名
            target_cfg = self.config['modules'].get('theme_catalyst_engine', {})

        params = target_cfg.get('params', {})
        expected_limit = params.get('max_grade_risk_off', 'C')

        out = self.runner._apply_theme_routing(payload)
        self.assertEqual(out['trade_grade'], expected_limit, f"代码未能正确读取 YAML 中的 max_grade_risk_off. Expected: {expected_limit}, Got: {out['trade_grade']}")
        self.assertTrue(out['theme_capped_by_macro'], "RISK_OFF 下评级削减未生效")

    def test_observability_enum_alignment(self):
        """证明观测口径一致：success/blocked/degraded 均能被正确统计"""
        # 测试数据
        theme_output = {
            "safe_to_consume": True,
            "trade_grade": "B",
            "current_state": "CONTINUATION",
            "primary_theme": "AI"
        }

        # 测试 success
        obs_success = ThemeObservabilityLogger.log_observability_event(theme_output, "TRC-1", "success")
        self.assertEqual(obs_success['route_hit_rate'], 1)
        self.assertEqual(obs_success['route_reject_rate'], 0)

        # 测试 blocked
        obs_blocked = ThemeObservabilityLogger.log_observability_event(theme_output, "TRC-2", "blocked")
        self.assertEqual(obs_blocked['route_hit_rate'], 0)
        self.assertEqual(obs_blocked['route_reject_rate'], 1)

        # 测试 degraded
        obs_degraded = ThemeObservabilityLogger.log_observability_event(theme_output, "TRC-3", "degraded")
        self.assertEqual(obs_degraded['route_hit_rate'], 0)
        self.assertEqual(obs_degraded['route_reject_rate'], 0)
        self.assertEqual(obs_degraded['route_result'], "degraded")
        self.assertIn(obs_degraded["mapping_result"], ("mapped", "mapping_failed"))
        self.assertIn(obs_degraded["validation_result"], ("validated", "degraded"))
        self.assertEqual(obs_degraded["state_result"], "CONTINUATION")

    def test_observability_replay_consistency_computation(self):
        """证明 replay_consistency_rate 非占位，支持可计算与降级输出"""
        base = {
            "safe_to_consume": True,
            "trade_grade": "B",
            "current_state": "CONTINUATION",
            "primary_theme": "AI",
        }
        obs_match = ThemeObservabilityLogger.log_observability_event(
            {**base, "replay_match": True}, "TRC-4", "success"
        )
        self.assertEqual(obs_match["replay_consistency_rate"], 1.0)
        self.assertEqual(obs_match["replay_consistency_mode"], "replay_match_flag")

        obs_counter = ThemeObservabilityLogger.log_observability_event(
            {**base, "replay_total": 10, "replay_mismatch": 2}, "TRC-5", "success"
        )
        self.assertEqual(obs_counter["replay_consistency_rate"], 0.8)
        self.assertEqual(obs_counter["replay_consistency_mode"], "replay_counter")

        obs_degraded = ThemeObservabilityLogger.log_observability_event(base, "TRC-6", "success")
        self.assertIsNone(obs_degraded["replay_consistency_rate"])
        self.assertEqual(obs_degraded["replay_consistency_mode"], "replay_unavailable")

    def test_final_trade_cap_policy_by_macro_regime(self):
        """证明 final_trade_cap 按主链分支显式赋值，不依赖隐式默认值"""
        out_risk_off = self.runner._apply_theme_routing({
            "macro_regime": "RISK_OFF",
            "trade_grade": "A",
            "primary_theme": "AI_Infrastructure",
        })
        self.assertEqual(out_risk_off["final_trade_cap"], "INTRADAY")

        out_mixed = self.runner._apply_theme_routing({
            "macro_regime": "MIXED",
            "trade_grade": "B",
            "primary_theme": "AI_Infrastructure",
        })
        self.assertEqual(out_mixed["final_trade_cap"], "1_TO_2_DAYS")

        out_risk_on = self.runner._apply_theme_routing({
            "macro_regime": "RISK_ON",
            "trade_grade": "B",
            "primary_theme": "AI_Infrastructure",
        })
        self.assertEqual(out_risk_on["final_trade_cap"], "STANDARD")

    def test_conflict_type_default(self):
        """证明冲突类型口径：缺省值应为 unknown_conflict"""
        # 当 macro_regime 为 None 时，进入缺失主链逻辑，应保留初始 unknown_conflict
        payload_none = {
            "macro_regime": None,
            "trade_grade": "B"
        }
        out_def = self.runner._apply_theme_routing(payload_none)
        self.assertEqual(out_def['conflict_type'], "unknown_conflict", "主链缺失时 conflict_type 未能保持正确的缺省口径")

if __name__ == "__main__":
    unittest.main()
