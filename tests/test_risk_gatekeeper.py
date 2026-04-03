"""
EDT 风控模块测试
验证 C-3: 高风险拦截逻辑 + PENDING_CONFIRM 状态机
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.risk_gatekeeper import (
    RiskGatekeeper, ExecutionGuard, ActionType, RiskLevel, RiskFlag, RiskCheckResult
)


class TestRiskGatekeeper:
    """测试风控校验"""
    
    def setup_method(self):
        self.gatekeeper = RiskGatekeeper()
    
    def test_low_risk_allows_execute(self):
        """低风险应允许执行"""
        opportunity = {
            "symbol": "AAPL",
            "name": "苹果",
            "risk_flags": [],
            "final_action": "EXECUTE"
        }
        
        can_exec, action, reason = self.gatekeeper.can_execute(opportunity)
        
        assert can_exec is True
        assert action == ActionType.EXECUTE
    
    def test_high_volatility_blocks(self):
        """高波动率应拦截"""
        opportunity = {
            "symbol": "NVDA",
            "name": "英伟达",
            "risk_flags": [
                {"type": "volatility", "level": "high", "description": "波动极大"}
            ],
            "final_action": "EXECUTE"
        }
        
        can_exec, action, reason = self.gatekeeper.can_execute(opportunity)
        
        assert can_exec is False
        assert action == ActionType.BLOCK
        assert "高风险" in reason
    
    def test_medium_risk_pending_confirm(self):
        """中等风险应待确认"""
        opportunity = {
            "symbol": "TSLA",
            "name": "特斯拉",
            "risk_flags": [
                {"type": "volatility", "level": "medium", "description": "波动较大"}
            ],
            "final_action": "EXECUTE"
        }
        
        can_exec, action, reason = self.gatekeeper.can_execute(opportunity)
        
        assert can_exec is False
        assert action == ActionType.PENDING_CONFIRM
    
    def test_multiple_medium_risk_blocks(self):
        """多个中等风险应拦截"""
        opportunity = {
            "symbol": "AMD",
            "name": "超威半导体",
            "risk_flags": [
                {"type": "volatility", "level": "medium", "description": "波动较大"},
                {"type": "liquidity", "level": "medium", "description": "流动性一般"}
            ],
            "final_action": "EXECUTE"
        }
        
        can_exec, action, reason = self.gatekeeper.can_execute(opportunity)
        
        assert can_exec is False
        assert action == ActionType.BLOCK
    
    def test_liquidity_high_risk_blocks(self):
        """高流动性风险应拦截"""
        opportunity = {
            "symbol": "SMALL",
            "name": "小盘股",
            "risk_flags": [
                {"type": "liquidity", "level": "high", "description": "流动性差"}
            ],
            "final_action": "EXECUTE"
        }
        
        can_exec, action, reason = self.gatekeeper.can_execute(opportunity)
        
        assert can_exec is False
        assert action == ActionType.BLOCK
    
    def test_watch_signal_always_allowed(self):
        """WATCH信号应始终允许"""
        opportunity = {
            "symbol": "GOOG",
            "name": "谷歌",
            "signal": "WATCH",
            "risk_flags": [],
            "final_action": "WATCH"
        }
        
        can_exec, action, reason = self.gatekeeper.can_execute(opportunity)
        
        assert can_exec is True
        assert action == ActionType.WATCH


class TestExecutionGuard:
    """测试执行守卫"""
    
    def setup_method(self):
        self.gatekeeper = RiskGatekeeper()
        self.guard = ExecutionGuard(self.gatekeeper)
    
    def test_execute_without_pending_allowed(self):
        """无待确认可直接执行"""
        opportunity = {
            "symbol": "AAPL",
            "risk_flags": []
        }
        
        allowed, reason = self.guard.before_execute(opportunity)
        
        assert allowed is True
    
    def test_execute_blocked_by_risk(self):
        """风险过高被拦截"""
        opportunity = {
            "symbol": "NVDA",
            "risk_flags": [
                {"type": "volatility", "level": "high"}
            ]
        }
        
        allowed, reason = self.guard.before_execute(opportunity)
        
        assert allowed is False
        assert "高风险" in reason
    
    def test_pending_must_be_approved(self):
        """待确认必须批准"""
        opportunity = {
            "symbol": "TSLA",
            "risk_flags": [
                {"type": "volatility", "level": "medium"}
            ]
        }
        
        result = self.gatekeeper.check_opportunity(opportunity)
        confirm_id = self.gatekeeper.pending_confirms.popitem()[0]
        
        allowed, reason = self.guard.before_execute(opportunity)
        
        assert allowed is False
        assert "需要人工确认" in reason
    
    def test_execution_log(self):
        """执行日志记录"""
        opportunity = {"symbol": "AAPL", "risk_flags": []}
        
        self.guard.before_execute(opportunity)
        
        log = self.guard.get_execution_log()
        
        assert len(log) > 0
        assert log[-1]["symbol"] == "AAPL"


class TestRiskLevel:
    """测试风险等级计算"""
    
    def setup_method(self):
        self.gatekeeper = RiskGatekeeper()
    
    def test_no_flags_low_risk(self):
        """无风险旗标为低风险"""
        flags = []
        level = self.gatekeeper._calculate_risk_level(flags)
        
        assert level == RiskLevel.LOW
    
    def test_single_high_risk(self):
        """单个高风险为高风险"""
        flags = [RiskFlag("volatility", "high", "")]
        level = self.gatekeeper._calculate_risk_level(flags)
        
        assert level == RiskLevel.HIGH
    
    def test_single_medium_risk(self):
        """单个中风险为中风险"""
        flags = [RiskFlag("volatility", "medium", "")]
        level = self.gatekeeper._calculate_risk_level(flags)
        
        assert level == RiskLevel.MEDIUM
    
    def test_multiple_medium_risk(self):
        """多个中风险为高风险"""
        flags = [
            RiskFlag("volatility", "medium", ""),
            RiskFlag("liquidity", "medium", "")
        ]
        level = self.gatekeeper._calculate_risk_level(flags)
        
        assert level == RiskLevel.HIGH


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
