<<<<<<< HEAD
# -
事件驱动交易系统
=======
# 事件驱动交易模块 - 开发指南

## 这是什么

将"重大事件驱动交易系统v2.8"改造成模块化工作流。

## AI接手入口

- `AI辅助工作流升级任务清单.md`：当前阶段唯一任务入口（先读）
- `EDT-AI协同开发与集成协议(Git版).md`：Git协作与门禁规则（强制约束）

## 项目结构

```
事件驱动交易模块阶段二/
├── AI辅助工作流升级任务清单.md
├── EDT-AI协同开发与集成协议(Git版).md
├── configs/               # 配置文件 (阈值、权重)
├── schemas/               # 模块接口定义
├── scripts/               # Python基类 + 示例
├── tests/                 # 测试用例
├── module-registry.yaml   # 模块注册
└── archive-阶段1传统实现/      # 旧阶段归档（只读）
```

## 快速开始

### 1. 安装依赖
```bash
pip install pyyaml pytest
```

### 2. 统一验收入口（推荐）
```bash
python3 -m pytest -q
PYTHONPYCACHEPREFIX=/tmp/pycache python3 scripts/system_healthcheck.py
bash scripts/verify_phase12.sh
bash scripts/verify_fullchain.sh
```

### 3. 运行示例（可选）
```bash
cd 事件驱动交易模块/scripts
python edt_module_base.py
python intel_modules.py
python analysis_modules.py
python workflow_runner.py
python full_workflow_runner.py
python multi_event_arbiter.py
python run_e2e_regression.py
python run_execution_scenarios.py
python verify_execution_no_pytest.py
```

### 4. 看懂接口
```bash
# 查看SignalScorer接口
cat ../schemas/signal_scorer.json | python -m json.tool
```

## 模块调用链

```
EventCapture → SourceRanker → SeverityEstimator → EventObjectifier
      ↓
LifecycleManager → FatigueCalculator
      ↓
ConductionMapper → MarketValidator
      ↓
SignalScorer → LiquidityChecker → RiskGatekeeper → PositionSizer → ExitManager
```

## 开发流程

1. **选一个模块** → 查看对应Schema
2. **按接口写代码** → 参考scripts/示例
3. **写测试** → 放在tests/目录
4. **提交** → 每日至少1次

## 模块清单（当前状态）

| 模块 | 状态 | 说明 |
|------|------|------|
| EventCapture | ✅ 已实现 | 事件截获 |
| SourceRanker | ✅ 已实现 | 来源分级 |
| SeverityEstimator | ✅ 已实现 | 严重度判定 |
| EventObjectifier | ✅ 已实现 | 事件对象化 |
| LifecycleManager | ✅ 已实现 | 生命周期管理 |
| FatigueCalculator | ✅ 已实现 | 疲劳度计算 |
| ConductionMapper | ✅ 已实现 | 传导映射 |
| MarketValidator | ✅ 已实现 | 市场验证 |
| SignalScorer | ✅ 已实现 | 信号评分 |
| LiquidityChecker | ✅ 已实现 | 流动性检测 |
| RiskGatekeeper | ✅ 已实现 | 风控闸门 |
| PositionSizer | ✅ 已实现 | 仓位计算 |
| ExitManager | ✅ 已实现 | 退出策略 |

## 配置修改

修改 `configs/edt-modules-config.yaml`：
- 权重调整
- 阈值修改
- 超时设置

## 遇到问题

1. 看Schema中的 `examples` 字段
2. 看scripts/中的示例代码
3. 问架构师

## 当前阶段口径（AI升级）

1. 执行入口：`AI辅助工作流升级任务清单.md`
2. 协作入口：`EDT-AI协同开发与集成协议(Git版).md`
3. 交付门禁：
   - `python3 -m pytest -q`
   - `PYTHONPYCACHEPREFIX=/tmp/pycache python3 scripts/system_healthcheck.py`
4. 旧阶段文件已归档到 `archive-阶段1传统实现/`，不再作为执行口径。

---

**开始吧！先按 AI 升级任务清单执行 Sprint 0（契约冻结）**
>>>>>>> 15dfe9a (chore: Initialize project with AI-Co-Dev Protocol & Environment Ready)
