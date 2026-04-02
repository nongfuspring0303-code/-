# 事件驱动交易模块 - 开发指引

## 项目定位

将“重大事件驱动交易系统”升级为可审计、可回放、可并行协作的模块化工作流。

核心原则：AI 可建议，规则可执行，风控可否决。

## 必读入口

- `阶段三-指挥中心全链条联动蓝图.md`（阶段三唯一任务入口）
- `EDT-AI协同开发与集成协议(Git版).md`

说明：若与历史阶段文档冲突，以阶段三蓝图与协同协议为准。

## 目录结构

```text
事件驱动交易模块阶段二/
├── configs/                 # 参数配置中心
├── schemas/                 # 输入输出契约
├── scripts/                 # 模块实现与运行入口
├── tests/                   # 回归与集成测试
├── docs/                    # 协议、映射、健康检查文档
├── module-registry.yaml     # 模块注册中心
└── logs/                    # 审计与健康检查报告
```

## 核心链路

```text
EventCapture -> SourceRanker -> SeverityEstimator -> EventObjectifier
EventObjectifier -> LifecycleManager -> FatigueCalculator
EventObjectifier -> ConductionMapper -> MarketValidator
AIEventIntelOutput -> NarrativeStateRecognizer -> AISignalAdapter
SignalScorer + AISignalAdapter -> LiquidityChecker -> RiskGatekeeper -> PositionSizer -> ExitManager
```

## B 层新增模块

- `NarrativeStateRecognizer`（B4）
  - 输出：`initial/continuation/decay/invalid`
  - 仅做叙事识别，不直接改执行状态机
- `AISignalAdapter`（B1）
  - 将 AI 输出映射为 `A0/A-1/A1/A1.5/A0.5`
  - 映射表配置化，支持版本回滚
- `RiskGatekeeper` 增强（B2/B3）
  - 增加 G7（AI 复核/降级闸门）
  - 决策输出新增 `decision_summary` 与 `reasoning`

## 快速验收

```bash
python3 -m pytest -q
PYTHONPYCACHEPREFIX=/tmp/pycache python3 scripts/system_healthcheck.py
bash scripts/verify_phase12.sh
bash scripts/verify_fullchain.sh
```

若环境中 `pytest` 与 Python 版本不兼容，至少保留：

```bash
python3 scripts/system_healthcheck.py
python3 scripts/verify_execution_no_pytest.py
```

## 协作硬规则

1. 先读 schema，再改代码。
2. 字段变更遵循四联动：`schemas` + `tests` + `module-registry.yaml` + 文档。
3. PR 前必须附门禁结果与健康检查报告。
