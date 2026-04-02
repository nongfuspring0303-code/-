#!/usr/bin/env python3
"""
EDT Module Base Class
重大事件驱动交易系统 - 模块基类

提供标准化的模块接口:
- 统一输入输出格式
- 配置驱动
- 日志审计
- 错误处理
"""

import json
import yaml
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from enum import Enum


class ModuleStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class ModuleInput:
    """模块输入基类"""
    raw_data: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModuleOutput:
    """模块输出基类"""
    status: ModuleStatus
    data: Dict[str, Any]
    errors: List[Dict[str, str]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class EDTModule(ABC):
    """EDT模块基类"""
    
    def __init__(self, name: str, version: str, config_path: Optional[str] = None):
        self.name = name
        self.version = version
        self.config = self._load_config(config_path)
        self.status = ModuleStatus.PENDING
        self.start_time = None
        self.end_time = None
        
    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        """加载配置文件"""
        if config_path is None:
            return {}
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception:
            return {}
    
    def _get_config(self, path: str, default: Any = None) -> Any:
        """获取配置项"""
        keys = path.split('.')
        value = self.config
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key, default)
            else:
                return default
        return value
    
    def _log(self, level: str, message: str, **kwargs):
        """标准化日志"""
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "module": self.name,
            "version": self.version,
            "level": level,
            "message": message,
            **kwargs
        }
        print(f"[{level}] {self.name}: {message}")
        # 实际项目中写入审计日志
        
    def validate_input(self, input_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """验证输入数据"""
        return True, None
    
    @abstractmethod
    def execute(self, input_data: ModuleInput) -> ModuleOutput:
        """执行模块逻辑 - 子类必须实现"""
        pass
    
    def run(self, input_data: Dict[str, Any]) -> ModuleOutput:
        """运行模块（带错误处理）"""
        self.start_time = datetime.now(timezone.utc)
        self.status = ModuleStatus.RUNNING
        
        # 验证输入
        valid, error_msg = self.validate_input(input_data)
        if not valid:
            self.status = ModuleStatus.FAILED
            return ModuleOutput(
                status=ModuleStatus.FAILED,
                data={},
                errors=[{"code": "INVALID_INPUT", "message": error_msg}]
            )
        
        try:
            # 执行
            module_input = ModuleInput(raw_data=input_data)
            result = self.execute(module_input)
            self.status = ModuleStatus.SUCCESS
            return result
            
        except TimeoutError:
            self.status = ModuleStatus.TIMEOUT
            self._log("ERROR", "Module timeout")
            return ModuleOutput(
                status=ModuleStatus.TIMEOUT,
                data={},
                errors=[{"code": "TIMEOUT", "message": "Execution timeout"}]
            )
            
        except Exception as e:
            self.status = ModuleStatus.FAILED
            self._log("ERROR", f"Module error: {str(e)}")
            return ModuleOutput(
                status=ModuleStatus.FAILED,
                data={},
                errors=[{"code": "EXECUTION_ERROR", "message": str(e)}]
            )
            
        finally:
            self.end_time = datetime.now(timezone.utc)
            self._log("INFO", f"Module completed in {(self.end_time - self.start_time).total_seconds():.2f}s")


# ========== 示例模块实现 ==========

class SignalScorer(EDTModule):
    """综合信号评分模块 - 示例实现"""
    
    def __init__(self, config_path: Optional[str] = None):
        super().__init__("SignalScorer", "1.0.0", config_path)
        self.weights = {
            "A0": 0.25,
            "A-1": 0.20,
            "A1": 0.25,
            "A1.5": 0.20,
            "A0.5": 0.10
        }
        
    def validate_input(self, input_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        required = ["A0", "A-1", "A1", "A1.5", "A0.5"]
        for key in required:
            if key not in input_data:
                return False, f"Missing required field: {key}"
        return True, None
    
    def execute(self, input_data: ModuleInput) -> ModuleOutput:
        raw = input_data.raw_data
        
        A0 = raw.get("A0", 0)
        A_1 = raw.get("A-1", 0)
        A1 = raw.get("A1", 0)
        A1_5 = raw.get("A1.5", 0)
        A0_5 = raw.get("A0.5", 0)
        
        # E4权重调整
        severity = raw.get("severity", "E3")
        if severity == "E4":
            # E4时预期差权重降低，验证权重增加
            effective_w = {
                "A0": self.weights["A0"],
                "A-1": self.weights["A-1"] - 0.10,
                "A1": self.weights["A1"] + 0.10,
                "A1.5": self.weights["A1.5"],
                "A0.5": self.weights["A0.5"] + 0.10
            }
        else:
            effective_w = self.weights
            
        # 疲劳度修正
        fatigue = raw.get("fatigue_index", 0)
        if fatigue > 70:
            A_1 = A_1 * (1 - fatigue / 200)
            
        # 计算Score
        score_raw = (
            effective_w["A0"] * A0 +
            effective_w["A-1"] * A_1 +
            effective_w["A1"] * A1 +
            effective_w["A1.5"] * A1_5 -
            effective_w["A0.5"] * A0_5
        )
        
        # 裁剪
        score = max(-100, min(100, score_raw))
        
        # 执行等级
        if score >= 80:
            tier = "G1"
            position = 0.80
        elif score >= 60:
            tier = "G2"
            position = 0.50
        elif score >= 40:
            tier = "G3"
            position = 0.20
        else:
            tier = "G5"
            position = 0
            
        return ModuleOutput(
            status=ModuleStatus.SUCCESS,
            data={
                "score": score,
                "score_tier": tier,
                "position_pct": position,
                "direction": "long" if score > 40 else "neutral",
                "adjustments": [
                    item for item in [
                        "E4调整" if severity == "E4" else None,
                        "疲劳度修正" if fatigue > 70 else None
                    ] if item is not None
                ]
            },
            metadata={
                "weights_used": effective_w,
                "fatigue_applied": fatigue > 70
            }
        )


class RiskGatekeeper(EDTModule):
    """风控闸门模块 - 示例实现"""

    def __init__(self, config_path: Optional[str] = None):
        super().__init__("RiskGatekeeper", "1.0.0", config_path)
    
    def execute(self, input_data: ModuleInput) -> ModuleOutput:
        raw = input_data.raw_data
        
        gate_decisions = []
        
        # G1: 流动性黑洞
        spread = raw.get("spread_multiplier", 0)
        liquidity = raw.get("liquidity_state", "GREEN")
        if spread > 5 or liquidity == "RED":
            gate_decisions.append({
                "gate": "G1",
                "triggered": True,
                "action": "BLOCK",
                "reason": "流动性黑洞" if spread > 5 else "Red状态"
            })
            return ModuleOutput(
                status=ModuleStatus.SUCCESS,
                data={
                    "gate_decisions": gate_decisions,
                    "final_action": "BLOCK",
                    "position_multiplier": 0,
                    "first_triggered_gate": "G1"
                }
            )
        else:
            gate_decisions.append({"gate": "G1", "triggered": False, "action": "PASS"})
            
        # G2: Dead事件
        state = raw.get("event_state", "Active")
        if state in ["Dead", "Archived"]:
            gate_decisions.append({
                "gate": "G2", 
                "triggered": True,
                "action": "FORCE_CLOSE"
            })
            return ModuleOutput(
                status=ModuleStatus.SUCCESS,
                data={
                    "gate_decisions": gate_decisions,
                    "final_action": "FORCE_CLOSE",
                    "position_multiplier": 0,
                    "first_triggered_gate": "G2"
                }
            )
            
        # G3: 疲劳度
        fatigue = raw.get("fatigue_index", 0)
        if fatigue > 85:
            gate_decisions.append({
                "gate": "G3",
                "triggered": True,
                "action": "BLOCK_NEW"
            })
            return ModuleOutput(
                status=ModuleStatus.SUCCESS,
                data={
                    "gate_decisions": gate_decisions,
                    "final_action": "WATCH",
                    "position_multiplier": 0,
                    "first_triggered_gate": "G3"
                }
            )
            
        # G5: Score评分
        score = raw.get("score", 0)
        position = 1.0 if score >= 60 else (0.5 if score >= 40 else 0)
        
        return ModuleOutput(
            status=ModuleStatus.SUCCESS,
            data={
                "gate_decisions": gate_decisions,
                "final_action": "EXECUTE" if position > 0 else "WATCH",
                "position_multiplier": position,
                "first_triggered_gate": None
            }
        )


# ========== 模块调用示例 ==========

if __name__ == "__main__":
    # 示例：SignalScorer调用
    scorer = SignalScorer()
    
    test_input = {
        "A0": 30,
        "A-1": 70,
        "A1": 78,
        "A1.5": 60,
        "A0.5": 0,
        "severity": "E3",
        "fatigue_index": 45
    }
    
    result = scorer.run(test_input)
    print(f"\n=== SignalScorer Result ===")
    print(f"Status: {result.status.value}")
    print(f"Data: {json.dumps(result.data, indent=2)}")
    
    # 示例：RiskGatekeeper调用
    gatekeeper = RiskGatekeeper()
    
    test_input_2 = {
        "event_state": "Active",
        "fatigue_index": 45,
        "liquidity_state": "GREEN",
        "correlation": 0.5,
        "score": 72,
        "spread_multiplier": 1.2
    }
    
    result_2 = gatekeeper.run(test_input_2)
    print(f"\n=== RiskGatekeeper Result ===")
    print(f"Status: {result_2.status.value}")
    print(f"Data: {json.dumps(result_2.data, indent=2)}")
