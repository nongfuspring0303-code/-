"""
EDT 风控校验模块
C-3: 高风险拦截逻辑 + PENDING_CONFIRM 状态机
"""

import yaml
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
from dataclasses import dataclass, field


class ActionType(Enum):
    EXECUTE = "EXECUTE"
    WATCH = "WATCH"
    BLOCK = "BLOCK"
    PENDING_CONFIRM = "PENDING_CONFIRM"


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class RiskFlag:
    type: str
    level: str
    description: str


@dataclass
class RiskCheckResult:
    passed: bool
    action: ActionType
    risk_flags: list[RiskFlag] = field(default_factory=list)
    reason: str = ""
    requires_confirm: bool = False
    confirm_id: str = ""


class RiskGatekeeper:
    """风控校验核心类"""
    
    def __init__(self, config_path: str = "configs/edt-modules-config.yaml"):
        self.config = self._load_config(config_path)
        self.pending_confirms: dict[str, dict] = {}
        self.confirm_timeout_minutes = 5
        
    def _load_config(self, config_path: str) -> dict:
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except:
            return self._default_config()
            
    def _default_config(self) -> dict:
        return {
            "risk_rules": {
                "max_volatility": 0.8,
                "min_liquidity": 0.3,
                "min_market_cap": 500_000_000_000,
                "block_on_high_risk": True,
            }
        }
    
    def check_opportunity(self, opportunity: dict) -> RiskCheckResult:
        """
        检查机会卡，返回校验结果
        """
        if str(opportunity.get("final_action", "")).upper() == ActionType.WATCH.value or str(opportunity.get("signal", "")).upper() == "WATCH":
            return RiskCheckResult(
                passed=True,
                action=ActionType.WATCH,
                risk_flags=[],
                reason="观望信号",
                requires_confirm=False,
            )

        risk_flags = self._extract_risk_flags(opportunity)
        risk_level = self._calculate_risk_level(risk_flags)
        
        if self._should_block(risk_level, risk_flags):
            return RiskCheckResult(
                passed=False,
                action=ActionType.BLOCK,
                risk_flags=risk_flags,
                reason="高风险自动拦截",
                requires_confirm=False
            )
        
        if self._should_pending(risk_level, risk_flags):
            pending_id = self._create_pending_confirmation(opportunity)
            return RiskCheckResult(
                passed=False,
                action=ActionType.PENDING_CONFIRM,
                risk_flags=risk_flags,
                reason="需要人工确认",
                requires_confirm=True,
                confirm_id=pending_id,
            )
        
        return RiskCheckResult(
            passed=True,
            action=ActionType.EXECUTE,
            risk_flags=risk_flags,
            reason="校验通过",
            requires_confirm=False
        )
    
    def _extract_risk_flags(self, opportunity: dict) -> list[RiskFlag]:
        """提取风险旗标"""
        flags = []
        for flag_data in opportunity.get('risk_flags', []):
            flags.append(RiskFlag(
                type=flag_data.get('type', 'unknown'),
                level=flag_data.get('level', 'low'),
                description=flag_data.get('description', '')
            ))
        return flags
    
    def _calculate_risk_level(self, risk_flags: list[RiskFlag]) -> RiskLevel:
        """计算综合风险等级"""
        if not risk_flags:
            return RiskLevel.LOW
            
        level_counts = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 0, RiskLevel.HIGH: 0}
        
        for flag in risk_flags:
            try:
                level = RiskLevel(flag.level)
                level_counts[level] += 1
            except ValueError:
                pass
        
        if level_counts[RiskLevel.HIGH] > 0:
            return RiskLevel.HIGH
        elif level_counts[RiskLevel.MEDIUM] > 1:
            return RiskLevel.HIGH
        elif level_counts[RiskLevel.MEDIUM] > 0:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW
    
    def _should_block(self, risk_level: RiskLevel, risk_flags: list[RiskFlag]) -> bool:
        """判断是否应直接拦截"""
        if not self.config.get("risk_rules", {}).get("block_on_high_risk", True):
            return False
            
        if risk_level == RiskLevel.HIGH:
            medium_count = 0
            for flag in risk_flags:
                if flag.type in ["volatility", "liquidity"]:
                    if flag.level == "high":
                        return True
                    if flag.level == "medium":
                        medium_count += 1
            if medium_count >= 2:
                return True
        return False
    
    def _should_pending(self, risk_level: RiskLevel, risk_flags: list[RiskFlag]) -> bool:
        """判断是否需要待确认"""
        if risk_level == RiskLevel.MEDIUM:
            return True
        if risk_level == RiskLevel.HIGH:
            return not self._should_block(risk_level, risk_flags)
        return False
    
    def _create_pending_confirmation(self, opportunity: dict) -> str:
        """创建待确认记录"""
        confirm_id = f"confirm_{opportunity.get('symbol', 'unk')}_{datetime.now().timestamp()}"
        self.pending_confirms[confirm_id] = {
            "opportunity": opportunity,
            "created_at": datetime.now(),
            "status": "pending"
        }
        return confirm_id
    
    def confirm_action(self, confirm_id: str, approved: bool) -> bool:
        """
        确认或拒绝待处理操作
        """
        if confirm_id not in self.pending_confirms:
            return False
            
        record = self.pending_confirms[confirm_id]
        
        if (datetime.now() - record["created_at"]) > timedelta(minutes=self.confirm_timeout_minutes):
            record["status"] = "timeout"
            return False
            
        record["status"] = "approved" if approved else "rejected"
        return True

    def get_confirmation(self, confirm_id: str) -> Optional[dict]:
        record = self.pending_confirms.get(confirm_id)
        if not record:
            return None
        return {
            "confirm_id": confirm_id,
            "status": record.get("status"),
            "symbol": record.get("opportunity", {}).get("symbol"),
            "created_at": record.get("created_at").isoformat() if record.get("created_at") else None,
        }
    
    def get_pending_confirmations(self) -> list[dict]:
        """获取所有待确认记录"""
        results = []
        for confirm_id, record in self.pending_confirms.items():
            if record["status"] == "pending":
                if (datetime.now() - record["created_at"]) <= timedelta(minutes=self.confirm_timeout_minutes):
                    results.append({
                        "confirm_id": confirm_id,
                        "symbol": record["opportunity"].get("symbol"),
                        "created_at": record["created_at"].isoformat(),
                        "risk_flags": [
                            {"type": f.type, "level": f.level, "description": f.description}
                            for f in self._extract_risk_flags(record["opportunity"])
                        ]
                    })
        return results
    
    def can_execute(self, opportunity: dict) -> tuple[bool, ActionType, str]:
        """
        判断是否可以执行，返回 (可执行, 动作, 原因)
        """
        result = self.check_opportunity(opportunity)
        return result.passed, result.action, result.reason


class ExecutionGuard:
    """
    执行守卫：确保未确认的请求不得进入执行
    """
    
    def __init__(self, gatekeeper: RiskGatekeeper):
        self.gatekeeper = gatekeeper
        self.execution_log: list[dict] = []
        
    def before_execute(self, opportunity: dict) -> tuple[bool, str]:
        """
        执行前校验，返回 (允许执行, 拒绝原因)
        """
        can_exec, action, reason = self.gatekeeper.can_execute(opportunity)
        
        if not can_exec:
            self._log_execution(opportunity, action, False, reason)
            return False, reason
            
        if action == ActionType.PENDING_CONFIRM:
            symbol = opportunity.get("symbol", "unknown")
            pending = self._find_pending(symbol)
            if not pending:
                self._log_execution(opportunity, action, False, "未找到待确认记录")
                return False, "需要人工确认"
                
            if pending["status"] != "approved":
                self._log_execution(opportunity, action, False, "未获得人工确认")
                return False, "等待人工确认"
        
        self._log_execution(opportunity, action, True, reason)
        return True, reason
    
    def _find_pending(self, symbol: str) -> Optional[dict]:
        """查找待确认记录"""
        for record in self.gatekeeper.pending_confirms.values():
            if record["opportunity"].get("symbol") == symbol and record["status"] == "pending":
                return record
        return None
    
    def _log_execution(self, opportunity: dict, action: ActionType, success: bool, reason: str):
        """记录执行日志"""
        self.execution_log.append({
            "symbol": opportunity.get("symbol"),
            "action": action.value,
            "success": success,
            "reason": reason,
            "timestamp": datetime.now().isoformat()
        })
    
    def get_execution_log(self, limit: int = 100) -> list[dict]:
        """获取执行日志"""
        return self.execution_log[-limit:]


def create_risk_system(config_path: str = "configs/edt-modules-config.yaml") -> tuple[RiskGatekeeper, ExecutionGuard]:
    """创建风控系统"""
    gatekeeper = RiskGatekeeper(config_path)
    guard = ExecutionGuard(gatekeeper)
    return gatekeeper, guard


if __name__ == "__main__":
    gatekeeper, guard = create_risk_system()
    
    test_opportunity = {
        "symbol": "NVDA",
        "name": "英伟达",
        "sector": "科技",
        "signal": "LONG",
        "risk_flags": [
            {"type": "volatility", "level": "medium", "description": "波动较大"}
        ],
        "final_action": "EXECUTE"
    }
    
    can_exec, action, reason = gatekeeper.can_execute(test_opportunity)
    print(f"Can execute: {can_exec}")
    print(f"Action: {action}")
    print(f"Reason: {reason}")
