# AI Mapping Regression Formal Review（v2.1 / v2.1-A）

## 1. 最终决定

Decision: COMMENT  
内容状态: Partial  
流程状态: Pass  
是否建议合并: 否  
是否需要再次复审: 是

## 2. 最新同步信息

- PR number: N/A（本地分支实施阶段）
- PR title: N/A
- PR URL: N/A
- base branch: `main`
- base sha: `<to_fill>`
- head branch: `fix/ai-mapping-regression-eval`
- head sha: `<to_fill>`
- merge commit sha: N/A
- changed files: `<to_fill>`
- commits: `<to_fill>`
- CI run id: `<to_fill>`
- CI status: `<to_fill>`
- CI conclusion: `<to_fill>`
- 本地测试: `<to_fill>`
- Review 状态: in-progress
- mergeable: N/A
- draft: N/A

## 3. 契约倒推打表

| 目标契约 / 缺口 | PR 是否覆盖 | 证据文件/函数/测试 | 结论 |
|---|---:|---|---|
| 固定 Benchmark171 作为回归基线 | 是 | `configs/ai_mapping_regression_policy.yaml` | Pass |
| 指标分层（语义/传导/推荐） | 是 | `docs/review/ai_mapping_regression_eval_implementation_v1.md` | Pass |
| Tier1/Tier2/Tier3 分层评估 | 是 | `configs/ai_mapping_regression_policy.yaml` | Pass |
| v_prev vs v_new 对比规则 | 是 | `configs/ai_mapping_regression_policy.yaml` | Pass |
| CI 自动门禁执行 | 否 | N/A | Follow-up |
| Benchmark/Validation 标签文件落地 | 否 | N/A | Follow-up |

## 4. 问题关闭矩阵

| 上轮问题 | 修复位置 | 测试证据 | 是否关闭 | 是否引入新风险 |
|---|---|---|---:|---:|
| event_type 已识别但 sectors 空 | 规划中 | N/A | 否 | 否 |
| Healthcare 误映射偏置 | 规划中 | N/A | 否 | 否 |
| 推荐率低导致个股质量低 | 规划中 | N/A | 否 | 否 |

## 5. 已确认通过项

| 项目 | 证据 | 结论 |
|---|---|---|
| 回归策略配置独立化 | `configs/ai_mapping_regression_policy.yaml` | Pass |
| 审查口径文档化 | `docs/review/ai_mapping_regression_eval_implementation_v1.md` | Pass |
| 正式审查记录骨架 | 本文件 | Pass |

## 6. 仍存在的问题

### MAJOR

1. 未完成自动 runner 与 CI 门禁接入，暂不能形成机器可执行的回归阻断。

## 7. 测试与 CI 审查

- CI 是否最新: N/A（尚未接入）
- CI 是否覆盖新增测试: N/A
- 本地测试是否可复现: 待补
- 测试是否覆盖真实链路: 待补
- 测试是否存在 flaky 风险: 待评估

## 8. 反例与边界场景

| 反例 | 当前是否覆盖 | 证据 | 结论 |
|---|---:|---|---|
| 空映射（event_type 有值但 sectors 空） | 否 | N/A | Follow-up |
| Healthcare 误映射 | 否 | N/A | Follow-up |
| 推荐率提升但 ticker 误报上升 | 否 | N/A | Follow-up |

## 9. 最终裁决

是否建议合并: 否  
是否可以 approve: 否  
是否需要 request changes: 否（当前为实施准备阶段）  
一句话结论: 评估规范已落地，执行链路（runner + CI gate + 基准标签）待实现。

