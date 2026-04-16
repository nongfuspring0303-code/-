# PR61 成员C 任务实施计划 (PLAN)

## 0. 类型标签
- 路径层

## 1. 任务目标
实现 PR61 中关于 **《主题板块催化持续性引擎 v1.0》** 的成员 C (Runtime Owner) 的工程落地责任，包括：
1. **Chain Routing Policy:** 在运行时（`workflow_runner`）中插入 A2.5 副链判断，按照主从链关系（macro_regime 优先）完整覆盖 C1(RISK_OFF)、C2(MIXED)、C3(RISK_ON) 及主链缺失状况，裁决 `conflict_flag`、`conflict_type`、`theme_capped_by_macro` 及强制封顶交易评级。
2. **Observability & SLO Spec:** 定义和下发规范化的 11 个追踪字段的结构化日志，计算并输出 5 大 SLI 指标（地图映射率、降级输出率、回放一致率等），并支持打上 P1/P2/P3 的 SLO 告警。
3. **主链完整集成:** runner 必须输出完整的 `contract字段`（包含所有的业务核心字段、输出信封包裹以及主副链融合结果）。

## 2. 所属模块
- 模块 C (下游执行：`workflow_runner.py`)

## 3. 修改文件列表
- `scripts/workflow_runner.py`：注入主副链的路由决策树，处理宏观层环境、调整最终的输出信包逻辑，阻止越过主链进行的强制交易行为，并增加标准化观察日志输出（Observability）。

## 4. 不修改文件列表 (Out of Scope)
- ❌ 获取 `schemas/` 下的契约设计 (由 Member A 负责)
- ❌ 修改 `healthcheck` 测试与报错规则 (由 Member B 负责)
- ❌ 修改 `full_workflow_runner.py` 的顶层编排逻辑（本次只在 `workflow_runner.py` 内实现主副链融合策略）

## 5. 配置读取路径
- 本次变更是纯代码路由逻辑构建，需要按约束直接将策略内嵌于 `workflow_runner.py` 运行时，不修改任何 configs。

## 6. 影响模块及其因果关系
- 输入处理处依赖由 `payload` 透传过来的 `macro_regime`, `trade_grade`, `safe_to_consume`。
- 修改处在 `RiskGatekeeper` / 判定执行动作 (`final_action`) 的路径段，动态修正 `trade_grade` 和最终的 `safe_to_consume` 及动作输出。
- 因果链向下影响后续真实的执行行为拦截和报警输出系统。

## 7. 执行步骤
1. 修改 `workflow_runner.py` 的执行路口处，获取 `payload` 中的宏观状态和副链反馈（`macro_regime` 等）。
2. 根据 `macro_regime` (RISK_OFF / MIXED / RISK_ON / None) 执行 4 分支的路由裁决，重新分配和覆盖 `conflict_flag`, `final_trade_cap`, `trade_grade` 以及产生对应的 `conflict_type` 标签。
3. 如果裁决给出 `safe_to_consume == False` 或者 `RISK_OFF` 的阻塞模式，则阻拦后续执行链调用接口，最终返回带有完整 `fallback_reason` 和信封 `contract_name/contract_version/producer_module` 的 `result["final"]` 结果。
4. 配置特定的 SLO 告警逻辑：若安全消费标识为不可用将触碰 P1 或 P2 告警，并计算 SLI（主题降级率与成功率）；最终拼接出规定格式的追踪日志进行规范记录。
5. 在 `workflow_runner.py` 的返回装配区，严格把 业务字段、Contract 信封 和 所有的主链融合标记 统一注入 `result["theme_output"]`/`result["final"]`，确保下游看到一字不差的完整契约下发。

## 8. 风险点与回滚策略
- **风险点**：`workflow_runner.py` 是下游统一出口。在插入这种新的多维度强裁决逻辑时，如果处理普通非主题事件的 `payload` 没有包含这些副链字段，可能会报 `KeyError`。解决方案为在处理前必须加入平滑默认处理机制及 `theme_signal` 有效性判定，确保只有在具有这些字段时才会走路由裁决拦截。
- **验证手段**：后续跑通 `pytest -v tests/test_execution_workflow.py` 或者 `system_healthcheck.py` 以进行无损防呆验证。
- **回滚策略**：若是引起 CI 执行全部崩溃，撤销 `workflow_runner.py` 本次的全部变更。
