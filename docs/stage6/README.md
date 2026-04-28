# Stage6 项目驾驶舱  
# Signal Quality / Outcome Attribution

> 当前阶段：PR-7b 准备阶段  
> 当前状态：PR-7a Contract Freeze 已完成；v2.1 Implementation Plan 正在落地；下一步进入 Outcome Engine / Summary / Report 实现  
> 最高原则：只读消费上游证据；不改 Gate；不改 execution；不伪造 outcome；配置单一真源；输出仅用于人工审核与后续规则优化

---

## 1. 一句话说明

Stage6 是信号质量验证与结果归因层，用来回答：

> 系统推荐、评分、WATCH / BLOCK / EXECUTE 是否被后续客观结果证明有效？

Stage6 不负责下单、不接 broker、不做 live、不做组合 PnL、不改 Gate、不改 final_action、不改 Stage5 日志结构。

---

## 2. 当前项目进展

| 阶段 | PR | 状态 | 说明 |
|---|---|---|---|
| PR-7a | PR97 | 已合并 | Contract Freeze，冻结 schema / policy / registry / metric_dictionary / tests |
| PR-7a docs | PR98 | 进行中 / 待合并 | 落地 v2.1 implementation plan，并对齐 PR97 口径 |
| PR-7b | 待新开 | 下一步 | 实现 Outcome Engine / Summary / Report |
| PR-7 Final | 待后续 | 未开始 | 全量验收，包含 engine、idempotency、replay、报告输出 |

---

## 3. 当前最高优先级文件

### 3.1 契约真源

以下文件来自 PR97，是 Stage6 contract 真源：

```text
docs/stage6/STAGE6_SCOPE_CANONICAL.md
schemas/opportunity_outcome.schema.json
schemas/mapping_attribution.schema.json
schemas/log_trust.schema.json
schemas/outcome_by_score_bucket.schema.json
configs/outcome_scoring_policy.yaml
configs/metric_dictionary.yaml
module-registry.yaml
tests/test_opportunity_outcome_schema.py
tests/test_stage6_metric_dictionary.py
```

使用规则：

字段 / enum / required / schema / policy / metric 以 PR97 合并后的 main 为准。

### 3.2 执行计划真源

```text
docs/stage6/stage6_signal_quality_implementation_plan_v2.1.md
```

用途：

说明 Stage6 为什么这样做、PR-7a / PR-7b / PR-7 Final 如何拆分、A/B/C 成员如何协作。

若该文件与 `STAGE6_SCOPE_CANONICAL.md` 冲突：

以 `STAGE6_SCOPE_CANONICAL.md` 为准。

### 3.3 团队施工 SOP

```text
docs/stage6/stage6_pr7b_team_execution_plan.md
```

用途：

给 A/B/C 成员日常执行使用，说明下一步具体做什么、怎么拆 PR、怎么验收。

如果该文件尚未入仓，应在 PR98 或后续 docs PR 中补入。

---

## 4. 文件阅读顺序

新成员阅读顺序：

1. `docs/stage6/README.md`
2. `docs/stage6/STAGE6_SCOPE_CANONICAL.md`
3. `docs/stage6/stage6_signal_quality_implementation_plan_v2.1.md`
4. `docs/tasks/stage6-pr7-outcome-attribution.md`
5. `docs/review/pr7_rules_test_mapping.md`
6. `configs/outcome_scoring_policy.yaml`
7. `configs/metric_dictionary.yaml`
8. `schemas/opportunity_outcome.schema.json`
9. `schemas/mapping_attribution.schema.json`
10. `schemas/log_trust.schema.json`
11. `schemas/outcome_by_score_bucket.schema.json`

---

## 5. 成员分工总览

| 成员 | 当前角色 | 当前重点 | 不允许做 |
|---|---|---|---|
| A 成员 | 契约守门 / 审查负责人 | 审查 schema、policy、registry、metric_dictionary 是否漂移 | 不写 engine 主逻辑；不改 Gate / execution |
| B 成员 | 归因规则 / 统计口径负责人 | 定义 hit/miss、WATCH/BLOCK、alpha、benchmark、score monotonicity、failure_reason | 不硬编码 Python；不改 Stage5 日志 |
| C 成员 | 工程实现 / 测试 / 报告负责人 | 实现 outcome_attribution_engine、fixtures、tests、summary/report | 不改阈值语义；不提交真实 logs / reports |

---

## 6. A 成员任务清单

A 负责守住 PR97 / PR98 已冻结契约。

### A 必做

- 审查 PR-7b 是否符合 schema
- 审查 `configs/outcome_scoring_policy.yaml` 是否为唯一阈值来源
- 审查 `configs/metric_dictionary.yaml` 与 summary/report 指标是否一致
- 审查 `module-registry.yaml` 是否没有漂移
- 审查是否没有修改 `workflow_runner.py`、Gate、execution、final_action
- 按《PR 正式审查模板 v2.1》输出正式审查意见

### A 交付物

`docs/review/stage6_pr7b_contract_review.md`

---

## 7. B 成员任务清单

B 负责定义“怎么算对、怎么算错”。

### B 必做

- 定义 EXECUTE LONG / SHORT hit、miss、neutral
- 定义 WATCH correct_watch、missed_opportunity、neutral_watch
- 定义 BLOCK correct_block、overblocked、neutral_block
- 定义 alpha / benchmark 计算口径
- 定义 score bucket 单调性规则
- 定义 failure_reason 归因规则
- 定义 primary stats / degraded stats / invalid / pending 纳入规则

### B 交付物

`docs/review/stage6_pr7b_attribution_rules.md`  
`tests/fixtures/stage6/expected_outcomes.yaml`

---

## 8. C 成员任务清单

C 负责实现 PR-7b 工程闭环。

### C 必做

新增：

- `scripts/outcome_attribution_engine.py`
- `tests/fixtures/stage6/outcome_logs/`
- `tests/test_outcome_attribution_engine.py`
- `tests/test_outcome_idempotency.py`
- `tests/test_outcome_replay_consistency.py`

engine 最小 CLI：

```bash
python3 scripts/outcome_attribution_engine.py \
  --logs-dir tests/fixtures/stage6/outcome_logs \
  --out-dir /tmp/stage6_outcome_test
```

### C 输出

engine 应生成：

- `opportunity_outcome.jsonl`
- `outcome_summary.json`
- `outcome_report.md`
- `outcome_by_score_bucket.json`
- `score_monotonicity_report.json`
- `failure_reason_distribution.json`
- `alpha_report.json`
- `log_trust_report.json`
- `mapping_attribution.jsonl`
- `decision_suggestions.json`

注意：

- 真实 `reports/outcome/*` 不提交 git
- 测试输出写到 `/tmp` 或 `pytest tmp_path`

---

## 9. 下一步执行顺序

### Step 1：PR98 合并

确认：

- PR98 CI 通过
- docs-only review 通过
- PR98 merged

### Step 2：从最新 main 新开 PR-7b 分支

```bash
git checkout main
git pull --ff-only origin main
git checkout -b stage6-pr7b-outcome-engine
```

### Step 3：B 先给 expected rules

新增：

- `docs/review/stage6_pr7b_attribution_rules.md`
- `tests/fixtures/stage6/expected_outcomes.yaml`

### Step 4：C 做 fixtures

新增：

- `tests/fixtures/stage6/outcome_logs/*`

### Step 5：C 写最小 engine

新增：

- `scripts/outcome_attribution_engine.py`
- `tests/test_outcome_attribution_engine.py`

### Step 6：C 补 idempotency / replay

新增：

- `tests/test_outcome_idempotency.py`
- `tests/test_outcome_replay_consistency.py`

### Step 7：A 正式审查

新增：

- `docs/review/stage6_pr7b_contract_review.md`

---

## 10. PR-7b 推荐拆分

不要做一个巨大 PR。建议拆成：

| 子 PR | 内容 | 目标 |
|---|---|---|
| PR-7b-1 | fixtures + 最小 engine | 读取日志、join、生成 opportunity_outcome / summary |
| PR-7b-2 | 标签与归因 | EXECUTE / WATCH / BLOCK / failure_reason |
| PR-7b-3 | 报告与一致性 | score bucket、alpha、report、idempotency、replay |

---

## 11. PR-7b 禁止项

PR-7b 禁止：

- 修改 `workflow_runner.py`
- 修改 `full_workflow_runner.py`
- 修改 Gate 规则
- 修改 final_action 语义
- 修改 `decision_gate` 生产结构
- 修改 `execution_emit` 生产逻辑
- 修改 Stage5 日志生产结构
- 接 broker / live trading
- 实现 portfolio PnL
- 实现 kill switch
- 自动调参
- 自动修改 playbook
- 提交真实 `logs/*`
- 提交真实 `reports/outcome/*`

---

## 12. PR-7b 必须覆盖的测试

```bash
python3 -m pytest -q tests/test_opportunity_outcome_schema.py
python3 -m pytest -q tests/test_stage6_metric_dictionary.py
python3 -m pytest -q tests/test_outcome_attribution_engine.py
python3 -m pytest -q tests/test_outcome_idempotency.py
python3 -m pytest -q tests/test_outcome_replay_consistency.py
python3 scripts/system_healthcheck.py --mode dev
```

---

## 13. PR-7b 合并门禁

不得合并，如果出现：

- 阈值硬编码在 Python
- invalid 进入 primary stats
- pending 提前 hit/miss
- mock/test 进入 primary stats
- `PENDING_CONFIRM` / `UNKNOWN` 进入 primary stats
- `benchmark_missing` 进入 alpha 主统计
- score monotonicity 样本不足仍 passed
- 真实 `reports/outcome` 入仓
- 真实 `logs` 入仓
- 改 Gate / execution / workflow_runner / final_action
- 缺 idempotency 测试
- 缺 replay consistency 测试

---

## 14. 当前风险清单

| 风险 | 等级 | 处理 |
|---|---|---|
| PR-7b 一次做太大 | 高 | 拆成 PR-7b-1 / 7b-2 / 7b-3 |
| C 在 Python 中硬编码阈值 | 高 | A 审查，必须从 policy 读取 |
| 真实 runtime report 被提交 | 高 | `.gitignore` / review gate 阻断 |
| pending / invalid 污染 primary stats | 高 | 必测 |
| decision_suggestions 被误接生产 | 高 | 只允许人工 review |
| 使用旧 zip 文档施工 | 中 | 只允许参考，不能覆盖 PR97/PR98 |

---

## 15. 每日同步格式

每天同步一次：

- 今日完成：
- 当前阻塞：
- 需要谁确认：
- 是否影响 PR-7b 边界：
- 是否需要修改 contract：

---

## 16. 最终验收定义

PR-7b 完成时，必须满足：

- engine 可运行
- fixtures 覆盖核心场景
- schema validate 通过
- outcome_summary.json 可生成
- outcome_by_score_bucket.json 可生成
- failure_reason_distribution.json 可生成
- idempotency 通过
- replay consistency 通过
- system_healthcheck 不因 Stage6 变更失败
- A/B/C 三方 review 通过

---

## 17. 一句话结论

当前 Stage6 已完成 PR-7a contract freeze，正在完成 v2.1 implementation plan docs 落地。下一步进入 PR-7b，团队按 A 守契约、B 定归因规则、C 写 engine 和测试的方式推进。所有开发以 PR97/PR98 合并后的 main 为准，不再以历史 zip 文件为施工依据。
