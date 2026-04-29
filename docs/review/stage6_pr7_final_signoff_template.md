# Stage6 PR-7 Final Sign-off Template

> 文件类型：最终验收模板 / Final Acceptance Gate  
> 适用范围：Stage6 PR-7 Outcome Attribution / Signal Quality  
> 当前用途：在 PR-7b-1 / PR-7b-2 / PR-7b-3 全部完成后，用于 PR-7 Final 全量验收  
> 最高优先级：若本文与 `docs/stage6/STAGE6_SCOPE_CANONICAL.md` 冲突，以 `STAGE6_SCOPE_CANONICAL.md` 为准  
> 核心边界：只读消费上游证据；不改 Gate；不改 execution；不改 final_action；不改 Stage5 日志结构；不提交真实 runtime 产物

---

## 0. 一句话结论

Stage6 PR-7 Final 不是新的功能开发 PR，而是 Stage6 PR-7 当前范围的最终验收包。

它用于确认：

```text
PR-7a 契约冻结已完成；
PR98 v2.1 execution docs 已落地；
PR-7b-1 / PR-7b-2 / PR-7b-3 工程实现、归因规则、报告输出、幂等与回放一致性均已完成；
A / B / C 三方 review 通过；
Stage6 输出仅用于人工审核与后续规则优化，不进入生产自动执行链路。
```

---

## 1. Final Sign-off 基本信息

| 字段 | 内容 |
|---|---|
| 项目 | Stage6 Signal Quality / Outcome Attribution |
| Final Gate | PR-7 Final |
| 验收对象 | Outcome Engine / Summary / Report / Attribution / Replay / Idempotency |
| 基准分支 | `main` |
| 验收分支 | `<fill-pr7-final-branch>` |
| 对应 PR | `<fill-pr-number>` |
| 验收日期 | `<YYYY-MM-DD>` |
| 审查模板 | PR 正式审查模板 v2.1（强制版） |
| 最终结论 | `PASS / PASS WITH MINOR / REQUEST CHANGES / BLOCKED` |

---

## 2. 前置条件检查

PR-7 Final 开始前，必须满足以下前置条件。

| 前置条件 | 状态 | 证据 / 链接 | 备注 |
|---|---:|---|---|
| PR-7a / PR97 Contract Freeze 已合并 | ☐ PASS / ☐ FAIL | `<link>` | 冻结 schema / policy / registry / metric dictionary / tests |
| PR98 v2.1 Implementation Plan 已合并 | ☐ PASS / ☐ FAIL | `<link>` | docs-only plan 落地 |
| PR-7b-1 已合并 | ☐ PASS / ☐ FAIL | `<link>` | fixtures + 最小 engine |
| PR-7b-2 已合并 | ☐ PASS / ☐ FAIL | `<link>` | 标签与归因规则 |
| PR-7b-3 已合并 | ☐ PASS / ☐ FAIL | `<link>` | 报告、alpha、idempotency、replay |
| 最新 `main` 已同步 | ☐ PASS / ☐ FAIL | `git rev-parse HEAD` | 必须基于最新 main 验收 |
| CI / healthcheck 可运行 | ☐ PASS / ☐ FAIL | `<log>` | 不允许因 Stage6 变更导致 RED |

---

## 3. 范围声明

### 3.1 In Scope

PR-7 Final 验收以下内容：

```text
1. Stage6 schema / policy / registry / metric_dictionary 是否一致。
2. Outcome attribution engine 是否可运行。
3. fixtures 是否覆盖核心路径。
4. EXECUTE / WATCH / BLOCK / PENDING_CONFIRM / UNKNOWN 是否按规则归因。
5. pending / invalid / degraded / valid 是否正确进入或排除统计。
6. alpha / benchmark / score bucket / failure_reason 是否可追踪。
7. outcome_summary / outcome_report / score bucket / failure distribution / log trust 等报告是否可生成。
8. idempotency 是否通过。
9. replay consistency 是否通过。
10. decision_suggestions 是否只用于人工审核，不被生产执行自动消费。
```

### 3.2 Out of Scope

PR-7 Final 不允许新增或修改以下内容：

```text
1. workflow_runner.py
2. full_workflow_runner.py
3. Gate 规则
4. final_action 语义
5. decision_gate 生产结构
6. execution_emit 生产逻辑
7. Stage5 日志生产结构
8. broker / live trading
9. portfolio PnL
10. kill switch
11. 自动调参
12. 自动修改 playbook
13. 提交真实 logs/*
14. 提交真实 reports/outcome/* runtime 产物
```

---

## 4. 契约真源检查

以下文件必须存在，且不得与 PR97 / PR98 合并后的 contract 发生漂移。

| 文件 | 检查项 | 状态 | 备注 |
|---|---|---:|---|
| `docs/stage6/STAGE6_SCOPE_CANONICAL.md` | 最高范围文件存在且未被弱化 | ☐ PASS / ☐ FAIL | 最高优先级 |
| `schemas/opportunity_outcome.schema.json` | required / enum / nullable / audit-only 规则一致 | ☐ PASS / ☐ FAIL | 主 outcome schema |
| `schemas/mapping_attribution.schema.json` | mapping_status / failure_reason enum 一致 | ☐ PASS / ☐ FAIL | mapping 归因 |
| `schemas/log_trust.schema.json` | log trust 输出契约存在 | ☐ PASS / ☐ FAIL | 日志可信度 |
| `schemas/outcome_by_score_bucket.schema.json` | strong schema，`additionalProperties:false` | ☐ PASS / ☐ FAIL | score bucket 输出 |
| `configs/outcome_scoring_policy.yaml` | 阈值单一真源 | ☐ PASS / ☐ FAIL | 禁止 Python 硬编码 |
| `configs/metric_dictionary.yaml` | Stage6 metrics + legacy compatibility 保留 | ☐ PASS / ☐ FAIL | 指标字典 |
| `module-registry.yaml` | Stage6 module / contract_artifacts 绑定完整 | ☐ PASS / ☐ FAIL | registry 一致性 |
| `docs/tasks/stage6-pr7-outcome-attribution.md` | PR-7a / PR-7b / Final 口径一致 | ☐ PASS / ☐ FAIL | taskbook |
| `docs/review/pr7_rules_test_mapping.md` | PR-7a complete / PR-7b planned 表述清晰 | ☐ PASS / ☐ FAIL | rule ↔ test traceability |

---

## 5. Engine 可运行验收

### 5.1 运行命令

PR-7 Final 必须验证以下命令可运行：

```bash
python3 scripts/outcome_attribution_engine.py \
  --logs-dir tests/fixtures/stage6/outcome_logs \
  --out-dir /tmp/stage6_outcome_test
```

### 5.2 期望输出

engine 应在 `/tmp/stage6_outcome_test` 或 pytest `tmp_path` 中生成以下文件：

| 输出文件 | 必须生成 | schema / 校验 | 备注 |
|---|---:|---|---|
| `opportunity_outcome.jsonl` | ☐ YES / ☐ NO | `schemas/opportunity_outcome.schema.json` | 核心 outcome records |
| `outcome_summary.json` | ☐ YES / ☐ NO | metric dictionary 对齐 | 汇总指标 |
| `outcome_report.md` | ☐ YES / ☐ NO | 人工可读 | 不进入执行链路 |
| `outcome_by_score_bucket.json` | ☐ YES / ☐ NO | `schemas/outcome_by_score_bucket.schema.json` | score bucket |
| `score_monotonicity_report.json` | ☐ YES / ☐ NO | policy 阈值 | 单调性 |
| `failure_reason_distribution.json` | ☐ YES / ☐ NO | failure enum | 失败原因分布 |
| `alpha_report.json` | ☐ YES / ☐ NO | alpha / benchmark 规则 | 超额收益报告 |
| `log_trust_report.json` | ☐ YES / ☐ NO | log trust schema | 日志可信度 |
| `mapping_attribution.jsonl` | ☐ YES / ☐ NO | mapping schema | 映射归因 |
| `decision_suggestions.json` | ☐ YES / ☐ NO | human review only | 禁止生产自动消费 |

### 5.3 Git 入仓规则

```text
真实 reports/outcome/* 不得提交到 git。
真实 logs/* 不得提交到 git。
测试输出只能写入 /tmp 或 pytest tmp_path。
```

---

## 6. Fixtures 覆盖验收

`tests/fixtures/stage6/outcome_logs/` 至少应覆盖以下场景。

| 场景 | fixture 存在 | expected outcome 存在 | 备注 |
|---|---:|---:|---|
| EXECUTE LONG hit | ☐ YES / ☐ NO | ☐ YES / ☐ NO | valid resolved outcome |
| EXECUTE LONG miss | ☐ YES / ☐ NO | ☐ YES / ☐ NO | valid resolved outcome |
| EXECUTE SHORT hit | ☐ YES / ☐ NO | ☐ YES / ☐ NO | short 方向正确 |
| EXECUTE SHORT miss | ☐ YES / ☐ NO | ☐ YES / ☐ NO | short 方向正确 |
| WATCH correct_watch | ☐ YES / ☐ NO | ☐ YES / ☐ NO | 未错过机会 |
| WATCH missed_opportunity | ☐ YES / ☐ NO | ☐ YES / ☐ NO | 错过机会 |
| WATCH neutral_watch | ☐ YES / ☐ NO | ☐ YES / ☐ NO | 低证据 / 不足样本 |
| BLOCK correct_block | ☐ YES / ☐ NO | ☐ YES / ☐ NO | 正确阻断 |
| BLOCK overblocked | ☐ YES / ☐ NO | ☐ YES / ☐ NO | 过度阻断 |
| BLOCK neutral_block | ☐ YES / ☐ NO | ☐ YES / ☐ NO | 无优势 / 不足样本 |
| PENDING_CONFIRM audit-only | ☐ YES / ☐ NO | ☐ YES / ☐ NO | 不进入 primary stats |
| UNKNOWN audit-only | ☐ YES / ☐ NO | ☐ YES / ☐ NO | 不进入 primary stats |
| invalid_join_key | ☐ YES / ☐ NO | ☐ YES / ☐ NO | invalid，不进入 primary stats |
| benchmark_missing | ☐ YES / ☐ NO | ☐ YES / ☐ NO | 不进入 alpha 主统计 |
| market_data_missing | ☐ YES / ☐ NO | ☐ YES / ☐ NO | degraded / invalid |
| insufficient_sample | ☐ YES / ☐ NO | ☐ YES / ☐ NO | monotonicity 不得 passed |
| mock/test source | ☐ YES / ☐ NO | ☐ YES / ☐ NO | 不进入 primary stats |

---

## 7. 归因规则验收

### 7.1 EXECUTE 规则

| 规则 | 状态 | 备注 |
|---|---:|---|
| EXECUTE LONG hit / miss 判定正确 | ☐ PASS / ☐ FAIL | 按 policy / expected_outcomes |
| EXECUTE SHORT hit / miss 判定正确 | ☐ PASS / ☐ FAIL | short 方向必须反向计算 |
| neutral 不得误标 hit / miss | ☐ PASS / ☐ FAIL | 低证据 / 不足样本 |
| pending 不得提前 hit / miss | ☐ PASS / ☐ FAIL | pending_t1 / t5 / t20 |
| invalid 不进入 primary stats | ☐ PASS / ☐ FAIL | invalid_join_key 等 |

### 7.2 WATCH 规则

| 规则 | 状态 | 备注 |
|---|---:|---|
| correct_watch 判定正确 | ☐ PASS / ☐ FAIL | WATCH 后无有效机会 |
| missed_opportunity 判定正确 | ☐ PASS / ☐ FAIL | WATCH 后出现显著机会 |
| neutral_watch 判定正确 | ☐ PASS / ☐ FAIL | 低证据 / 样本不足 |
| WATCH 低证据不得强行归因 | ☐ PASS / ☐ FAIL | neutral_watch |

### 7.3 BLOCK 规则

| 规则 | 状态 | 备注 |
|---|---:|---|
| correct_block 判定正确 | ☐ PASS / ☐ FAIL | BLOCK 后无机会或避免损失 |
| overblocked 判定正确 | ☐ PASS / ☐ FAIL | BLOCK 后机会显著 |
| neutral_block 判定正确 | ☐ PASS / ☐ FAIL | 无优势 / 样本不足 |
| BLOCK no-advantage 不能算 overblocked | ☐ PASS / ☐ FAIL | neutral_block |

### 7.4 Failure Reason 规则

| failure_reason | 状态 | 备注 |
|---|---:|---|
| `mapping_wrong` | ☐ PASS / ☐ FAIL | 映射错误 |
| `timing_wrong` | ☐ PASS / ☐ FAIL | 时间窗口错误 |
| `market_rejected` | ☐ PASS / ☐ FAIL | 市场拒绝 |
| `source_bad` | ☐ PASS / ☐ FAIL | 来源质量差 |
| `risk_too_strict` | ☐ PASS / ☐ FAIL | 风控过严 |
| `risk_too_loose` | ☐ PASS / ☐ FAIL | 风控过松 |
| `provider_bad` | ☐ PASS / ☐ FAIL | provider 异常 |
| `market_data_bad` | ☐ PASS / ☐ FAIL | 市场数据异常 |
| `score_not_predictive` | ☐ PASS / ☐ FAIL | 评分无预测性 |
| `gate_rule_wrong` | ☐ PASS / ☐ FAIL | Gate 规则错误 |
| `execution_missing` | ☐ PASS / ☐ FAIL | 执行缺失 |
| `join_key_missing` | ☐ PASS / ☐ FAIL | join key 缺失 |
| `benchmark_missing` | ☐ PASS / ☐ FAIL | benchmark 缺失 |
| `insufficient_sample` | ☐ PASS / ☐ FAIL | 样本不足 |

---

## 8. Primary Stats 排除规则验收

以下记录不得进入 primary stats。

| 排除项 | 状态 | 备注 |
|---|---:|---|
| `data_quality=invalid` | ☐ PASS / ☐ FAIL | 必须排除 |
| `data_quality=pending` | ☐ PASS / ☐ FAIL | 必须排除 |
| `PENDING_CONFIRM` | ☐ PASS / ☐ FAIL | audit-only |
| `UNKNOWN` | ☐ PASS / ☐ FAIL | audit-only |
| pending outcome | ☐ PASS / ☐ FAIL | 不得 hit/miss |
| mock/test source | ☐ PASS / ☐ FAIL | 不得污染主统计 |
| `benchmark_missing` | ☐ PASS / ☐ FAIL | 不进入 alpha 主统计 |
| insufficient sample | ☐ PASS / ☐ FAIL | monotonicity 不得 passed |

---

## 9. Metric Dictionary / Policy 单一真源验收

| 检查项 | 状态 | 备注 |
|---|---:|---|
| 所有阈值来自 `configs/outcome_scoring_policy.yaml` | ☐ PASS / ☐ FAIL | 禁止 Python 硬编码 |
| 所有 summary 指标已注册在 `configs/metric_dictionary.yaml` | ☐ PASS / ☐ FAIL | Stage6 metrics |
| legacy Stage4/5 metrics 未被破坏 | ☐ PASS / ☐ FAIL | `ai_confidence` 等保留 |
| failure reason enum 与 schema 一致 | ☐ PASS / ☐ FAIL | 三方一致 |
| output file 字段与 metric_dictionary 可追踪 | ☐ PASS / ☐ FAIL | summary/report |

---

## 10. Idempotency 验收

必须通过：

```bash
python3 -m pytest -q tests/test_outcome_idempotency.py
```

验收要求：

| 检查项 | 状态 | 备注 |
|---|---:|---|
| 同一输入重复运行输出一致 | ☐ PASS / ☐ FAIL | hash / json 比较 |
| 同一 key 不重复写入冲突记录 | ☐ PASS / ☐ FAIL | opportunity_id / trace_id |
| 输出顺序确定性 | ☐ PASS / ☐ FAIL | deterministic ordering |
| 无时间戳随机污染测试输出 | ☐ PASS / ☐ FAIL | created_at 除外需可控 |

---

## 11. Replay Consistency 验收

必须通过：

```bash
python3 -m pytest -q tests/test_outcome_replay_consistency.py
```

验收要求：

| 检查项 | 状态 | 备注 |
|---|---:|---|
| replay 后 outcome 一致 | ☐ PASS / ☐ FAIL | 同输入同输出 |
| join key 稳定 | ☐ PASS / ☐ FAIL | opportunity_id / trace_id |
| orphan replay 不进入 primary stats | ☐ PASS / ☐ FAIL | orphan_replay |
| replay missing decision 可审计 | ☐ PASS / ☐ FAIL | log_trust_report |

---

## 12. Score Monotonicity 验收

| 检查项 | 状态 | 备注 |
|---|---:|---|
| `outcome_by_score_bucket.json` 生成 | ☐ PASS / ☐ FAIL | bucket 输出 |
| `score_monotonicity_report.json` 生成 | ☐ PASS / ☐ FAIL | 单调性报告 |
| 样本不足时 status = `insufficient_sample` | ☐ PASS / ☐ FAIL | 不得 passed |
| bucket 顺序固定 | ☐ PASS / ☐ FAIL | 80_PLUS / 60_79 / 40_59 / LT_40 |
| score bucket schema validate 通过 | ☐ PASS / ☐ FAIL | additionalProperties:false |

---

## 13. Alpha / Benchmark 验收

| 检查项 | 状态 | 备注 |
|---|---:|---|
| benchmark_return_t5 可计算 | ☐ PASS / ☐ FAIL | benchmark 存在时 |
| sector_relative_alpha_t5 可计算 | ☐ PASS / ☐ FAIL | sector benchmark 存在时 |
| benchmark_missing 不进入 alpha 主统计 | ☐ PASS / ☐ FAIL | must exclude |
| alpha_report.json 可生成 | ☐ PASS / ☐ FAIL | 报告输出 |
| LONG / SHORT alpha 方向正确 | ☐ PASS / ☐ FAIL | short 方向需特别检查 |

---

## 14. Log Trust / Mapping Attribution 验收

| 检查项 | 状态 | 备注 |
|---|---:|---|
| `log_trust_report.json` 可生成 | ☐ PASS / ☐ FAIL | 日志可信度 |
| `mapping_attribution.jsonl` 可生成 | ☐ PASS / ☐ FAIL | 映射归因 |
| `join_key_missing` 可落盘 | ☐ PASS / ☐ FAIL | trace_id nullable |
| mapping_failure_reason enum 有效 | ☐ PASS / ☐ FAIL | schema validate |
| provider failure 不伪造数据 | ☐ PASS / ☐ FAIL | provider_bad / market_data_bad |

---

## 15. Decision Suggestions 验收

| 检查项 | 状态 | 备注 |
|---|---:|---|
| `decision_suggestions.json` 可生成 | ☐ PASS / ☐ FAIL | human review only |
| 不被 production execution 自动消费 | ☐ PASS / ☐ FAIL | 硬约束 |
| 不改 final_action | ☐ PASS / ☐ FAIL | 禁止语义漂移 |
| 建议项可追踪到 outcome evidence | ☐ PASS / ☐ FAIL | audit trail |

---

## 16. 必跑测试命令

PR-7 Final 必须贴出以下命令结果。

```bash
python3 -m pytest -q tests/test_opportunity_outcome_schema.py
python3 -m pytest -q tests/test_stage6_metric_dictionary.py
python3 -m pytest -q tests/test_outcome_attribution_engine.py
python3 -m pytest -q tests/test_outcome_idempotency.py
python3 -m pytest -q tests/test_outcome_replay_consistency.py
python3 scripts/system_healthcheck.py --mode dev
```

| 命令 | 结果 | 证据 |
|---|---:|---|
| `test_opportunity_outcome_schema.py` | ☐ PASS / ☐ FAIL | `<paste>` |
| `test_stage6_metric_dictionary.py` | ☐ PASS / ☐ FAIL | `<paste>` |
| `test_outcome_attribution_engine.py` | ☐ PASS / ☐ FAIL | `<paste>` |
| `test_outcome_idempotency.py` | ☐ PASS / ☐ FAIL | `<paste>` |
| `test_outcome_replay_consistency.py` | ☐ PASS / ☐ FAIL | `<paste>` |
| `system_healthcheck.py --mode dev` | ☐ PASS / ☐ FAIL | `<paste>` |

---

## 17. 最低验收指标

| 指标 | 最低要求 | 实际值 | 状态 |
|---|---:|---:|---:|
| outcome coverage | `>= 95%` | `<fill>` | ☐ PASS / ☐ FAIL |
| execute coverage | `100%` | `<fill>` | ☐ PASS / ☐ FAIL |
| schema validate | `PASS` | `<fill>` | ☐ PASS / ☐ FAIL |
| idempotency | `PASS` | `<fill>` | ☐ PASS / ☐ FAIL |
| replay consistency | `PASS` | `<fill>` | ☐ PASS / ☐ FAIL |
| failure reason coverage | `>= 95%` | `<fill>` | ☐ PASS / ☐ FAIL |
| score monotonicity | `PASS or insufficient_sample when applicable` | `<fill>` | ☐ PASS / ☐ FAIL |
| healthcheck | `PASS or unrelated known issue documented` | `<fill>` | ☐ PASS / ☐ FAIL |

---

## 18. 风险复核

| 风险 | 是否发生 | 处理 |
|---|---:|---|
| Python 中硬编码阈值 | ☐ NO / ☐ YES | 若 YES，必须 Request Changes |
| invalid 进入 primary stats | ☐ NO / ☐ YES | 若 YES，必须 BLOCK |
| pending 提前 hit/miss | ☐ NO / ☐ YES | 若 YES，必须 BLOCK |
| mock/test 进入 primary stats | ☐ NO / ☐ YES | 若 YES，必须 BLOCK |
| PENDING_CONFIRM / UNKNOWN 进入 primary stats | ☐ NO / ☐ YES | 若 YES，必须 BLOCK |
| benchmark_missing 进入 alpha 主统计 | ☐ NO / ☐ YES | 若 YES，必须 BLOCK |
| score monotonicity 样本不足仍 passed | ☐ NO / ☐ YES | 若 YES，必须 BLOCK |
| 真实 reports/outcome 入仓 | ☐ NO / ☐ YES | 若 YES，必须 BLOCK |
| 真实 logs 入仓 | ☐ NO / ☐ YES | 若 YES，必须 BLOCK |
| 改 Gate / execution / workflow_runner / final_action | ☐ NO / ☐ YES | 若 YES，必须 BLOCK |

---

## 19. A / B / C 三方 Review

### 19.1 A Review — Contract / Schema / Boundary

| 检查项 | 状态 | 备注 |
|---|---:|---|
| Schema drift | ☐ PASS / ☐ FAIL |  |
| Policy single source | ☐ PASS / ☐ FAIL |  |
| Registry consistency | ☐ PASS / ☐ FAIL |  |
| Metric dictionary consistency | ☐ PASS / ☐ FAIL |  |
| No runtime boundary violation | ☐ PASS / ☐ FAIL |  |
| PR 正式审查模板 v2.1 已执行 | ☐ PASS / ☐ FAIL |  |

Reviewer: `<name>`  
Date: `<YYYY-MM-DD>`  
Decision: `APPROVE / REQUEST CHANGES / BLOCK`

---

### 19.2 B Review — Attribution / Metrics

| 检查项 | 状态 | 备注 |
|---|---:|---|
| EXECUTE hit/miss rules | ☐ PASS / ☐ FAIL |  |
| WATCH attribution | ☐ PASS / ☐ FAIL |  |
| BLOCK attribution | ☐ PASS / ☐ FAIL |  |
| Alpha / benchmark | ☐ PASS / ☐ FAIL |  |
| Failure reasons | ☐ PASS / ☐ FAIL |  |
| Primary/degraded/invalid/pending handling | ☐ PASS / ☐ FAIL |  |
| Score monotonicity | ☐ PASS / ☐ FAIL |  |

Reviewer: `<name>`  
Date: `<YYYY-MM-DD>`  
Decision: `APPROVE / REQUEST CHANGES / BLOCK`

---

### 19.3 C Review — Engine / Tests / Reports

| 检查项 | 状态 | 备注 |
|---|---:|---|
| Engine CLI | ☐ PASS / ☐ FAIL |  |
| Fixtures | ☐ PASS / ☐ FAIL |  |
| Reports generated | ☐ PASS / ☐ FAIL |  |
| Schema validation | ☐ PASS / ☐ FAIL |  |
| Idempotency | ☐ PASS / ☐ FAIL |  |
| Replay consistency | ☐ PASS / ☐ FAIL |  |
| No runtime artifacts committed | ☐ PASS / ☐ FAIL |  |

Reviewer: `<name>`  
Date: `<YYYY-MM-DD>`  
Decision: `APPROVE / REQUEST CHANGES / BLOCK`

---

## 20. 最终裁决

```text
Final Decision: PASS / PASS WITH MINOR / REQUEST CHANGES / BLOCKED
```

### PASS 条件

全部满足时，PR-7 Final 可判定为 PASS：

```text
1. PR-7a / PR98 / PR-7b-1 / PR-7b-2 / PR-7b-3 均已合并。
2. Engine 可运行。
3. 所有必需报告可生成。
4. 所有 schema validate 通过。
5. outcome coverage / execute coverage / failure reason coverage 达标。
6. idempotency 通过。
7. replay consistency 通过。
8. system_healthcheck 不因 Stage6 变更失败。
9. 无 runtime / Gate / execution / final_action 越界修改。
10. A / B / C 三方 review 均通过。
```

### REQUEST CHANGES 条件

出现以下任一情况，应 Request Changes：

```text
1. 报告文件缺失。
2. fixtures 覆盖不足。
3. 某些规则未映射测试。
4. schema validate 不完整。
5. metric_dictionary 与 summary/report 不一致。
6. healthcheck 因 Stage6 变更失败。
```

### BLOCK 条件

出现以下任一情况，应 BLOCK：

```text
1. 修改 Gate / execution / workflow_runner / final_action。
2. invalid / pending / PENDING_CONFIRM / UNKNOWN 进入 primary stats。
3. benchmark_missing 进入 alpha 主统计。
4. 真实 logs 或 reports/outcome runtime 产物入仓。
5. decision_suggestions 被生产执行自动消费。
6. Python 硬编码阈值，绕过 outcome_scoring_policy.yaml。
```

---

## 21. Final Sign-off 记录

| 角色 | 姓名 | 决定 | 日期 | 备注 |
|---|---|---|---|---|
| A / Contract Reviewer | `<name>` | `APPROVE / REQUEST CHANGES / BLOCK` | `<date>` |  |
| B / Attribution Reviewer | `<name>` | `APPROVE / REQUEST CHANGES / BLOCK` | `<date>` |  |
| C / Engineering Reviewer | `<name>` | `APPROVE / REQUEST CHANGES / BLOCK` | `<date>` |  |
| Final Owner | `<name>` | `PASS / BLOCKED` | `<date>` |  |

---

## 22. 最终一句话

```text
PR-7 Final 通过后，Stage6 Outcome Attribution / Signal Quality 当前范围正式完成。
后续若需要 dashboard、生产监控、评分反馈、release hardening，应另开增强 PR，不再混入 PR-7 Final。
```
