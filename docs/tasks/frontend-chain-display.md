# Task: 前端推导链展示（显示最多逻辑证据）

## 0. 类型标签
- 工具层 / 前端展示

## 1. 任务目标
在"板块热力图"区域显示新闻的完整推导链，包含所有逻辑证据。即使中间环节被拦截也显示候选股票、评分明细、风险标记、门禁原因。

## 2. 所属模块
- C 模块（下游/输出层）

## 3. 因果位置
- 输出/展示层

## 4. In Scope（允许）
- 修改 `canvas/app.js` 的渲染逻辑
- 在板块热力图区域显示完整推导链：

### 展示的逻辑证据（全部显示）
**AI 语义层**：
- headline（新闻标题）
- ai_verdict（hit/miss）
- ai_confidence（置信度 0-100）
- ai_reason（AI 分析理由）

**板块传导层**：
- sector.name（板块名称）
- sector.direction（LONG/SHORT/WATCH）
- sector.impact_score（影响分数）
- sector.confidence（置信度）
- conduction_chain（传导链路径）

**股票筛选层**（即使被拦截也显示）：
- symbol（股票代码）
- name（股票名称）
- signal（LONG/SHORT/WATCH）
- confidence（置信度）
- score_100（百分制分数）
- score_breakdown（评分明细：event_exposure/event_relevance/relative_strength/liquidity_score/risk_filter_score）

**风控拦截层**（关键证据）：
- final_action（最终决策：EXECUTE/WATCH/BLOCK）
- gate_reason_code（门禁原因代码）
- risk_flags（风险标记列表：type/level/description）
- state_machine_step（状态机步骤）
- reasoning（综合评语）

## 5. Out of Scope（禁止）
- 不修改 `transmission_engine/core/*` 任何逻辑
- 不修改 `scripts/` 后端逻辑
- 不修改 configs/ 配置

## 6. Allowed Files
- `canvas/app.js`

## 7. Forbidden Files
- `transmission_engine/core/*`
- `scripts/opportunity_score.py`
- `scripts/path_adjudicator.py`
- `configs/*`

## 8. 配置依赖
- 无

## 9. 状态机影响
- 不影响路径裁决逻辑

## 10. 验证逻辑
- 功能验证：刷新前端，确认显示所有逻辑证据

## 11. 风险分析
- 风险低：纯前端展示逻辑修改

## 12. 回滚策略
- 直接 git revert