# 阶段6：信号质量提升与统计分析体系执行方案 v2.1（整合版）

> 基于设计文档 v0.1、执行方案 v1.1 与深度评审建议整合  
> 版本：v2.1  
> 状态：Aligned with PR97 Contract Freeze / Ready for PR-7b planning  
> 适用范围：Stage6 PR-7 Outcome Attribution 实施  
> 前置依赖：Stage5 主体合并；Residual Evidence Logging PR 合并  
> 核心原则：效率与准确率双优先；最小可用闭环；不重写主链路；不伪造 outcome；配置单一真源

> 说明：`docs/stage6/STAGE6_SCOPE_CANONICAL.md` 是 Stage6 PR-7 的最高优先级范围文件；若 v2.1 执行方案与 canonical 文件冲突，以 canonical 文件为准。

---

## 0. 最终定位

### 0.1 Stage6 定义

```
Stage6 = Signal Quality / Outcome Attribution Layer
阶段6 = 信号质量验证与结果归因层
```

它只回答一个核心问题：

> 系统推荐、评分、WATCH / BLOCK / EXECUTE 是否被后续客观结果证明有效？

### 0.2 Stage6 应该回答的问题

1. 系统推荐之后，标的是否真的上涨 / 下跌；
2. 高分机会是否真的比低分机会更好；
3. EXECUTE 是否产生收益或 alpha；
4. WATCH 是正确观望，还是漏掉机会；
5. BLOCK 是避免亏损，还是过度错杀；
6. 当前评分体系是否具备统计意义上的单调性；
7. 哪些失败来自 mapping、行情、provider、风控过严/过松、score 不可预测；
8. 哪些规则或评分体系需要后续人工审核优化。

### 0.3 Stage6 不应该回答的问题

```
怎么下单？
怎么接 broker？
怎么做 live mode？
怎么做组合级 PnL？
怎么做 kill switch？
怎么做完整 Paper execution？
怎么做完整 PIT backtest？
怎么改 Gate？
怎么改 Stage5 日志结构？
怎么自动调参？
怎么自动修改 playbook？
```

这些属于 Stage7 或独立专项，不应进入当前 Stage6 PR-7。

---

## 0.4 只读消费原则

**Stage6 不生产、不修改、不扩展上游证据；Stage6 只读消费 Stage5 / PR94 / Residual Evidence 已落盘证据；Stage6 基于这些证据生成 outcome、summary、report 和 decision suggestions。**

### 禁止

```
Stage6 修改 market_data_provenance 生产结构
Stage6 修改 decision_gate 结构
Stage6 修改 execution_emit 逻辑
Stage6 新增 provider trust gate
Stage6 修改 Gate / final_action
Stage6 修改 workflow_runner.py
```

### 允许

```
Stage6 只读消费 market_data_provenance
Stage6 只读消费 provider/data_quality 字段
Stage6 输出 outcome_by_provider
Stage6 将 provider / market data 问题归入 data_quality / failure_reason
```

---

## 0.5 四方一致性硬门禁（P0 必须）

PR-7 合并前必须同时满足：

- schemas/opportunity_outcome.schema.json 存在并可加载
- schemas/outcome_by_score_bucket.schema.json 存在并可加载
- configs/outcome_scoring_policy.yaml 为唯一阈值真源
- module-registry.yaml 声明 Stage6 outcome 模块
- module-registry.yaml 引用 opportunity_outcome.schema.json
- configs/metric_dictionary.yaml 注册 Stage6 指标
- docs/stage6/STAGE6_SCOPE_CANONICAL.md 存在且被 PR 描述显式引用
- docs/tasks/stage6-pr7-outcome-attribution.md 存在
- docs/review/pr7_rules_test_mapping.md 存在

缺任一项 → **PR 不得合并（BLOCKER）**

PR97 taskbook / registry 已将 `schemas/outcome_by_score_bucket.schema.json` 纳入 PR-7a contract artifacts。

---

## 0.6 成员任务速览表

| 成员 | 核心定位 | 主要负责内容 | 主要文件 | 不负责 / 禁止越界 | 最终交付物 |
|---|---|---|---|---|---|
| A 成员 | 契约 / Schema / 门禁规则负责人 | 定义 outcome 标准字段、schema、状态机、枚举、data_quality gate、DoD、硬门禁；审核 policy 合规性 | `schemas/opportunity_outcome.schema.json`；`schemas/outcome_by_score_bucket.schema.json`；`module-registry.yaml`；`configs/metric_dictionary.yaml` | 不写 outcome engine 主逻辑；不改交易主链路；不维护收益阈值细项 | schema、状态机、DoD、review checklist、policy 合规签字 |
| B 成员 | 归因规则 / 统计口径负责人 | 定义 hit/miss、WATCH/BLOCK 标签、score bucket、benchmark、alpha、failure_reason、score_monotonicity | `configs/outcome_scoring_policy.yaml` | 不写主执行引擎；不改 Stage5 日志；不改 gate 执行语义 | 归因规则、分组统计口径、score monotonicity 规则、failure_reason 分类 |
| C 成员 | 工程实现 / 测试 / 报告负责人 | 实现 outcome_attribution_engine，读取日志、join 证据链、生成 outcome、summary、report、测试 | `scripts/outcome_attribution_engine.py`；`tests/test_outcome_attribution_engine.py` | 不修改阈值语义；不硬编码配置；不重写 Stage5 evaluator；不提交真实 logs | 可运行 engine、测试、fixture、报告输出 |

---

## 0.7 每个成员一句话任务

**A 成员**: 把 Stage6 的 **字段、状态、schema、门禁、DoD** 定死，确保后续所有 outcome 记录都有统一契约，不能伪造、不能错连、不能把 pending 当 resolved。

**B 成员**: 定义 **怎么算对、怎么算错、怎么算错杀、怎么算漏报、高分是否真的更好**，确保 outcome attribution 的统计口径合理、可解释、可复盘。

**C 成员**: 把 A/B 定义好的规则做成可运行代码：读取现有 Stage5/PR94 日志，生成 `opportunity_outcome.jsonl`、`outcome_summary.json`、`outcome_report.md`，并用测试证明逻辑正确。

---

## 0.8 成员交付物清单

### A 成员交付物

- [ ] schemas/opportunity_outcome.schema.json
- [ ] schemas/outcome_by_score_bucket.schema.json
- [ ] schemas/log_trust.schema.json
- [ ] schemas/mapping_attribution.schema.json
- [ ] outcome_status 枚举
- [ ] outcome_label 枚举
- [ ] data_quality 枚举
- [ ] failure_reason 枚举
- [ ] Stage6 DoD
- [ ] invalid / degraded / pending / valid 判定边界
- [ ] PR review checklist 中的硬门禁条款
- [ ] module-registry.yaml 声明 Stage6 outcome 模块
- [ ] configs/metric_dictionary.yaml 注册 Stage6 指标

### B 成员交付物

- [ ] LONG / SHORT hit-miss 判定规则
- [ ] WATCH: correct_watch / missed_opportunity / neutral_watch
- [ ] BLOCK: correct_block / overblocked / neutral_block
- [ ] score_bucket 分桶
- [ ] alpha / benchmark 口径
- [ ] score_monotonicity 判定规则
- [ ] failure_reason 分类表
- [ ] mapping_status 枚举
- [ ] 分组统计维度

### C 成员交付物

- [ ] scripts/outcome_attribution_engine.py
- [ ] CLI 可运行
- [ ] opportunity_outcome.jsonl 输出
- [ ] outcome_summary.json 输出
- [ ] outcome_report.md 输出
- [ ] tests/test_outcome_attribution_engine.py
- [ ] tests/test_opportunity_outcome_schema.py
- [ ] tests/test_outcome_idempotency.py
- [ ] tests/test_outcome_replay_consistency.py
- [ ] 缺文件 / 缺字段 / pending / invalid / degraded 失败路径测试

---

## 0.9 成员边界硬规则

- A 可以定义契约，但不得写 outcome engine 主逻辑
- B 可以定义统计口径，但不得硬编码到 Python
- C 可以实现逻辑，但不得擅自修改阈值、标签、枚举、DoD
- 任何人不得重写 Stage5 / PR94 主链路
- 任何人不得提交真实 logs/*.jsonl / logs/*.json / logs/*.log
- 任何人不得在数据缺失时伪造价格、provider、benchmark

---

## 0.10 最小协作顺序

1. A 先冻结 schema + enum + data_quality gate + registry + metric_dictionary
2. B 补齐 thresholds + bucket + label + benchmark + failure_reason + mapping_status
3. C 按 A/B 的配置实现 engine
4. C 写测试，A/B 审核测试是否覆盖自己的规则
5. 三人共同跑全量测试
6. 按 PR review template v2.1 正式审查

---

## 0.11 成员责任一句话总表

- A = 定规则边界 + 四方一致性
- B = 定结果怎么算 + 归因口径
- C = 把它跑起来并用测试证明

---

## 1. 系统边界

**只做**：
- 信号有效性验证
- 统计可信性判断
- 失败归因
- 优化建议

**不做**：
- broker接入
- 实盘执行
- 组合PnL

---

## 2. 核心模块

代码主模块：

- scripts/outcome_attribution_engine.py

内部逻辑层：

- Log Trust
- Mapping Attribution
- Outcome Attribution
- Decision Suggestions

说明：
这些是 outcome_attribution_engine 内部逻辑层，不要求拆成多个独立 Python 文件。若后续拆分，必须保持同一 PR-7 边界，不得引入执行层逻辑。

---

## 3. 核心Schema

### 3.1 Outcome Schema

基于 `configs/outcome_scoring_policy.yaml` 配置文件驱动。

```json
{
  "schema_version": "stage6.outcome.v1",
  "opportunity_id": "OPP-...",
  "trace_id": "...",
  "event_trace_id": "...",
  "request_id": "...",
  "batch_id": "...",
  "event_hash": "...",
  "decision_id": "...",
  "execution_id": "...",
  "symbol": "NVDA",
  "direction": "LONG",
  "action_before_gate": "EXECUTE",
  "action_after_gate": "EXECUTE",
  "gate_result": "PASS",
  "triggered_rules": [],
  "reject_reason_code": null,
  "score": 82.0,
  "score_bucket": "80_PLUS",
  "grade": "B",
  "event_type": "policy",
  "sector": "Technology",
  "market_regime": "risk_on",
  "decision_ts": "2026-04-25T14:30:00Z",
  "decision_price": 100.0,
  "actual_entry_ts": null,
  "actual_entry_price": null,
  "entry_price_type": "decision_price",
  "benchmark_symbol": "QQQ",
  "sector_benchmark_symbol": "XLK",
  "t1_return": 0.012,
  "t5_return": 0.034,
  "t20_return": 0.071,
  "benchmark_return_t5": 0.016,
  "sector_relative_alpha_t5": 0.018,
  "max_drawdown_t5": -0.021,
  "max_upside_t5": 0.052,
  "outcome_status": "resolved_t5",
  "outcome_label": "hit",
  "primary_failure_reason": null,
  "failure_reasons": [],
  "data_quality": "valid",
  "data_quality_reasons": [],
  "provenance_field_missing": [],
  "created_at": "2026-04-26T00:00:00Z"
}
```

字段口径（P0）：

- `WATCH/BLOCK` 默认使用 `decision_price` 做 hypothetical outcome
- `EXECUTE` 若存在 paper/execution fill，可记录 `actual_entry_ts` 与 `actual_entry_price`
- 主统计默认基于 `decision_price`
- 执行质量分析可单独基于 `actual_entry_price`
- 若存在 `actual_entry_price` 但缺失 `actual_entry_ts` 或 `execution_id`，不得进入 execution quality stats
- `primary_failure_reason` 用于主统计；`failure_reasons[]` 用于复合归因
- 若仅一个失败原因，`primary_failure_reason` 必须与 `failure_reasons[0]` 一致
- `action_after_gate` 允许值为 `EXECUTE`、`WATCH`、`BLOCK`、`PENDING_CONFIRM`、`UNKNOWN`
- `PENDING_CONFIRM` / `UNKNOWN` 仅用于审计表达：可落盘但不进入 primary stats，不输出 hit / miss，不进入 alpha 主统计，不进入 score monotonicity 主统计，且必须按 policy 标记为 `data_quality=degraded` 或 `data_quality=invalid`
- `PENDING_CONFIRM` / `UNKNOWN` 不改变 Gate / execution / final_action 语义

### 3.2 Mapping Attribution Schema

```json
{
  "schema_version": "stage6.mapping_attribution.v1",
  "opportunity_id": "OPP-...",
  "trace_id": "...",
  "mapping_status": "mapping_success",
  "mapping_failure_reason": null,
  "mapped_sector": "Technology",
  "mapped_industry": "Semiconductors",
  "confidence_score": 0.85,
  "provenance_field_missing": [],
  "created_at": "2026-04-26T00:00:00Z"
}
```

### 3.3 Log Trust Schema

```json
{
  "schema_version": "stage6.log_trust.v1",
  "opportunity_id": "OPP-...",
  "log_source": "live",
  "join_key_valid": true,
  "timestamp_valid": true,
  "join_key_type": "trace_id + event_hash",
  "missing_join_fields": [],
  "data_quality": "valid",
  "data_quality_reasons": [],
  "created_at": "2026-04-26T00:00:00Z"
}
```

### 3.3.1 Log Source 枚举与处理（P1）

允许值：

- live
- replay
- fixture
- mock
- test
- unknown

处理规则：

- `mock/test` 不进入 primary stats
- `unknown` 至少标记 `degraded`，不得静默进入核心结论

### 3.4 Mapping Status 枚举（P1）

- mapping_success
- mapping_wrong
- mapping_missing
- mapping_ambiguous
- ai_over_trigger
- not_tradeable
- join_key_missing

规则：
- join_key_missing → invalid
- mapping_missing → degraded
- ai_over_trigger → `primary_failure_reason` / `failure_reasons`

### 3.5 Failure Reason 正式枚举（P0）

必须在 schema enum、metric_dictionary、`failure_reason_distribution.json` 三处一致：

- mapping_wrong
- timing_wrong
- market_rejected
- source_bad
- risk_too_strict
- risk_too_loose
- provider_bad
- market_data_bad
- score_not_predictive
- gate_rule_wrong
- execution_missing
- join_key_missing
- benchmark_missing
- insufficient_sample

规则：

- 主统计使用 `primary_failure_reason`
- 复合归因使用 `failure_reasons[]`
- 无失败原因时：`primary_failure_reason=null` 且 `failure_reasons=[]`

### 3.6 契约版本策略（P0）

- 文档版本（v2.1）与 schema/config 契约版本（v1）是两个维度
- Stage6 当前契约版本固定为：
  - `stage6.outcome.v1`
  - `stage6.mapping_attribution.v1`
  - `stage6.log_trust.v1`
  - `stage6.outcome_policy.v1`
  - `stage6.outcome_summary.v1`
- 新增字段使用 minor 规则；删除/重命名字段必须升级 major 并给兼容窗口
- PR 若变更契约版本，必须同步更新 schema、policy、task、review mapping 与测试锚点

### 3.7 Schema 强约束要求（P0）

必须满足：

- 所有字段必须定义 type（string / number / boolean / array / object / null）
- required 字段必须明确
- enum 字段必须全集定义
- 禁止未声明字段进入正式输出
- 禁止 fallback 自动填默认值
- 禁止 UNKNOWN / N/A / default 等未授权值进入 primary stats

最低 required 字段：

- schema_version
- opportunity_id
- action_after_gate
- outcome_status
- data_quality
- created_at

允许为 null（但必须可审计落盘）：

- trace_id
- symbol
- direction

规则：

- `trace_id/symbol/direction` 缺失时，不得丢弃样本；必须写入 `provenance_field_missing`
- 缺失导致的样本通常进入 `data_quality=invalid` 或 `degraded`，由规则决定

必须定义 enum：

- direction
- action_before_gate
- action_after_gate
- gate_result
- outcome_status
- outcome_label
- data_quality
- mapping_status
- primary_failure_reason
- log_source
- score_monotonicity.status（passed / passed_with_warning / failed / insufficient_sample）

Schema 文件必须包括：

- schemas/opportunity_outcome.schema.json
- schemas/outcome_by_score_bucket.schema.json
- schemas/log_trust.schema.json
- schemas/mapping_attribution.schema.json

说明：

- `opportunity_outcome.schema.json` 内的 `score_monotonicity` 字段仅作为摘要字段
- 正式分桶明细与强 schema 以 `schemas/outcome_by_score_bucket.schema.json` 为准

审查规则：

- Schema 不存在 → BLOCKER
- Schema 无 required → BLOCKER
- enum 不完整 → BLOCKER
- 未声明字段进入输出 → BLOCKER
- UNKNOWN 进入 primary stats → BLOCKER

---

## 4. Data Quality体系

- **valid**：可用于统计
- **degraded**：降级使用
- **invalid**：剔除
- **pending**：未完成

规则：
- invalid 不进入统计
- degraded 需标记
- pending 不参与结果判断

### 4.1 Data Quality 统计处理

| data_quality | 统计处理 |
|---|---|
| valid | 进入 primary stats |
| degraded | 默认不进 primary stats，只进 degraded_stats |
| invalid | 不进统计，只进 data quality report |
| pending | 不进统计，等待到期 |

### 4.2 禁止规则

```
缺价格时用 0
缺 provider 时填 yahoo
缺 benchmark 时默认 SPY 并进入 alpha 主统计
pending_t5 直接判 hit/miss
invalid 进入 hit_rate
mock/test 进入 primary stats
```

---

## 5. 核心流程

1. 读取日志
2. Log Trust过滤
3. 构建opportunity
4. Mapping Attribution
5. Outcome计算
6. 指标统计
7. Decision输出

---

## 6. 核心指标

核心指标以 `configs/metric_dictionary.yaml` 注册项为准，至少包括：

- hit_rate_t5
- avg_alpha_t5
- avg_return_t5
- score_monotonicity
- mapping_failure_rate
- overblock_rate
- missed_opportunity_rate
- correct_block_rate
- outcome_record_coverage_rate
- resolved_outcome_coverage_rate
- pending_outcome_rate
- execute_outcome_coverage_rate
- join_key_link_rate
- failure_reason_coverage_rate

---

## 7. 输入定义

Stage6 输入全部来自 Stage5 已落盘日志：

1. `decision_gate.jsonl`
2. `execution_emit.jsonl`
3. `replay_write.jsonl`
4. `trace_scorecard.jsonl`
5. `market_data_provenance.jsonl`

Stage6 只读消费这些输入，不修改其结构。

可选辅助输入：
- `pipeline_stage.jsonl`
- `raw_news_ingest.jsonl`
- `rejected_events.jsonl`
- `quarantine_replay.jsonl`

---

## 8. 输出定义

Stage6 新增输出统一写入：`reports/outcome/`

### 8.1 P0 核心输出（必须）

```
reports/outcome/opportunity_outcome.jsonl
reports/outcome/outcome_summary.json
reports/outcome/outcome_report.md
reports/outcome/score_monotonicity_report.json
reports/outcome/failure_reason_distribution.json
reports/outcome/alpha_report.json
reports/outcome/log_trust_report.json
reports/outcome/mapping_attribution.jsonl
reports/outcome/outcome_by_score_bucket.json
reports/outcome/decision_suggestions.json
```

### 8.2 P1 分组输出（可选）

```
reports/outcome/outcome_by_rule.json
reports/outcome/outcome_by_provider.json
reports/outcome/outcome_by_sector.json
reports/outcome/outcome_by_market_regime.json
```

### 8.3 运行产物入仓规则（P0）

- `reports/outcome/*` 属于运行时产物，默认 **不入 git**
- 仅允许提交：空目录占位（`.gitkeep`）、schema 样例（`tests/fixtures/`）、脱敏示例报告
- PR 如包含真实运行产物（jsonl/json/md dashboard）→ BLOCKER
- 复现实验证据应写入 `docs/review/*` 并附命令，不直接提交大体积运行结果

---

## 9. Log Trust 最小实现（P0）

必须输出：`reports/outcome/log_trust_report.json`

结构：

```json
{
  "total_rows": 0,
  "live_rows": 0,
  "mock_rows_rejected": 0,
  "test_rows_rejected": 0,
  "join_key_invalid_count": 0,
  "timestamp_invalid_count": 0,
  "fallback_marked_count": 0,
  "rejected_reason_distribution": {}
}
```

规则：
- mock/test 不进入统计
- join_key_invalid 不进入归因
- timestamp_invalid 至少 degraded

---

## 10. 测试矩阵

| Test ID | 场景 | 预期 |
|---|---|---|
| S6-001 | EXECUTE LONG T+5 > 2% | outcome_label = hit |
| S6-002 | EXECUTE LONG T+5 < -2% | outcome_label = miss |
| S6-003 | EXECUTE SHORT T+5 < -2% | outcome_label = hit |
| S6-004 | WATCH 后达到 hit | outcome_label = missed_opportunity |
| S6-005 | WATCH 后无机会且证据完整 | outcome_label = correct_watch |
| S6-005N | WATCH 后无机会但证据不足/样本不足 | outcome_label = neutral_watch |
| S6-006 | BLOCK 后亏损 | outcome_label = correct_block |
| S6-007 | BLOCK 后上涨 | outcome_label = overblocked |
| S6-007N | BLOCK 后未形成明确机会 | outcome_label = neutral_block |
| S6-008 | 缺 join key | invalid_join_key，不进统计 |
| S6-009 | market_data_default_used | invalid，不进统计 |
| S6-010 | market_data_stale | degraded |
| S6-011 | T+5 未到期 | pending_t5，不输出 hit/miss |
| S6-012 | score bucket 单调 | monotonicity passed |
| S6-013 | score bucket 样本不足 | insufficient_sample |
| S6-014 | 缺 benchmark | degraded 或 benchmark_missing |
| S6-015 | 缺 execution_emit | execution_missing / pending / invalid，视配置 |
| S6-016 | mock 数据 | 拒绝进入统计 |
| S6-017 | 同一主键重跑 | 幂等，不重复 append |
| S6-018 | 重放结果一致 | 同输入重跑，summary 一致 |
| S6-019 | provider 只用于归因 | 不生成 gate |
| S6-020 | 半日交易日 | 按 XNYS calendar 计算 T+N |
| S6-021 | 标的停牌 / 无价格 | pending 或 invalid，不得前值伪造 |
| S6-022 | 非交易日 | 顺延到下一个有效交易日 |

---

## 11. Rule ID ↔ Test ID 映射（P0 必须）

文件：`docs/review/pr7_rules_test_mapping.md`

PR-7a 只覆盖 contract/schema/metric dictionary 层测试；engine / idempotency / replay / calendar / outcome calculation 测试属于 PR-7b；PR-7 Final 才要求全部通过。

| Rule ID | 规则 | Phase | Test ID | 文件 |
|--------|------|-------|--------|------|
| S6-R001 | pending 不得 hit/miss | PR-7b engine | S6-011 | test_outcome_attribution_engine.py |
| S6-R002 | invalid 不进统计 | PR-7b engine | S6-008 | test_outcome_attribution_engine.py |
| S6-R003 | 样本不足不判 monotonicity | PR-7b engine | S6-013 | test_outcome_attribution_engine.py |
| S6-R004 | mock/test 不进统计 | PR-7b engine | S6-016 | test_outcome_attribution_engine.py |
| S6-R005 | 幂等不可重复写入 | PR-7b engine | S6-017 | test_outcome_idempotency.py |
| S6-R006 | 重放结果一致 | PR-7b engine | S6-018 | test_outcome_replay_consistency.py |
| S6-R007 | provider 只用于归因，不生成 gate | PR-7b engine | S6-019 | test_outcome_attribution_engine.py |
| S6-R008 | BLOCK 无明确优势时必须归类 neutral_block | PR-7b engine | S6-007N | test_outcome_attribution_engine.py |
| S6-R009 | 半日交易日按交易日历推进 | PR-7b engine | S6-020 | test_outcome_attribution_engine.py |
| S6-R010 | 停牌/无价格不得伪造前值 | PR-7b engine | S6-021 | test_outcome_attribution_engine.py |
| S6-R011 | 非交易日必须顺延到下个交易日 | PR-7b engine | S6-022 | test_outcome_attribution_engine.py |
| S6-R012 | score bucket 明细必须生成 outcome_by_score_bucket.json | PR-7b engine | S6-012/S6-013 | test_outcome_attribution_engine.py |
| S6-R013 | WATCH 在证据不足时必须归类 neutral_watch | PR-7b engine | S6-005N | test_outcome_attribution_engine.py |

规则：
- 每个 Rule 必须有 Test
- 每个 Test 必须能追溯 Rule

---

## 12. 幂等与重放一致性

### 12.1 主键

```
(trace_id, opportunity_id, symbol, direction, action_after_gate, horizon)
```

兼容规则：

- 若上游已保证 `opportunity_id` 唯一到 `symbol + direction` 级，允许在内部索引复用该约束
- 但对外 `outcome_idempotency_key` 必须包含 `symbol` 与 `direction`，避免多标的事件覆盖

### 12.2 重跑规则

```
同一主键重复运行：upsert / overwrite
禁止 append 重复行
同一输入重跑：summary 核心指标必须一致
允许 created_at 不同
```

### 12.3 必补测试

```
tests/test_outcome_idempotency.py
tests/test_outcome_replay_consistency.py
```

---

## 13. 时区与交易日历

### 13.1 固定口径

```
日志入库时区：UTC
交易窗口时区：America/New_York
交易日历：XNYS
T+1 / T+5 / T+20：按交易日，不按自然日
```

### 13.2 缺失处理

```
交易日历不可得：
  data_quality = degraded
  primary_failure_reason = market_data_bad

到期后仍缺价格：
  data_quality = invalid
  不进主统计

benchmark 缺失：
  可保留记录
  不得进入 alpha 主统计
```

### 13.3 价格口径与优先级（P0）

`decision_price` 来源优先级：

1. `trace_scorecard` 的决策时点价格快照
2. 同 trace 对齐的市场行情快照（同时间窗口）
3. 若缺失则标记 `decision_price_missing`（不得伪造）

`actual_entry_price` 来源优先级：

1. paper/execution fill（需同时具备 `execution_id` 与 fill 时间）
2. 无 fill 证据时保持 `null`，不得回填估算值

`exit_price` / `t1/t5/t20`：

- 使用对应交易日窗口的 close 价格（XNYS 日历）
- 非交易日顺延到下一个有效交易日
- 停牌/无价格按 pending 或 invalid 处理，不得使用前值伪造

公式：

- `return_tN = (exit_price_tN - decision_price) / decision_price`（LONG）
- `return_tN = (decision_price - exit_price_tN) / decision_price`（SHORT）
- `alpha_tN = return_tN - benchmark_return_tN`

benchmark 规则：

- benchmark 缺失可保留记录
- benchmark 缺失不得进入 alpha 主统计

---

## 14. 强制规则（红线）

- mock数据不得进入统计
- join_key_missing 不得进入归因
- 样本不足不得输出决策
- pending不得计算alpha

---

## 15. PR 拆分

### PR-7a（契约层）

包含：
- schema 文件（opportunity_outcome, outcome_by_score_bucket, log_trust, mapping_attribution）
- config 文件（outcome_scoring_policy.yaml, metric_dictionary.yaml）
- registry（module-registry.yaml）
- tasks（stage6-pr7-outcome-attribution.md）
- review mapping（pr7_rules_test_mapping.md）

### PR-7b（Outcome Engine / Summary / Report）

包含：
- outcome_attribution_engine.py
- tests（所有测试文件）
- fixtures（stage6/outcome_logs/）
- 输出契约与示例（`reports/outcome/` 结构说明 + `tests/fixtures` 脱敏样例，不提交真实 runtime 产物）

范围纯度补充（P0）：

- PR-7b 不提交 `reports/outcome/*.jsonl` 或真实运行报告文件
- 仅允许提交：输出结构说明文档、`.gitkeep`、脱敏 fixtures、可复现实验命令

### PR-7 Final

必须：
- PR-7a 冻结
- PR-7b 测试通过
- formal review 完成

---

## 16. 配置文件结构

路径：`configs/outcome_scoring_policy.yaml`

```yaml
schema_version: "stage6.outcome_policy.v1"

windows:
  t1_trading_days: 1
  t5_trading_days: 5
  t20_trading_days: 20

thresholds:
  long_hit_return_t5: 0.02
  long_hit_alpha_t5: 0.01
  long_miss_return_t5: -0.02
  long_miss_alpha_t5: -0.01
  short_hit_return_t5: -0.02
  short_hit_alpha_t5: -0.01
  short_miss_return_t5: 0.02
  short_miss_alpha_t5: 0.01

score_buckets:
  - name: "80_PLUS"
    min: 80
    max: null
  - name: "60_79"
    min: 60
    max: 80
  - name: "40_59"
    min: 40
    max: 60
  - name: "LT_40"
    min: null
    max: 40

benchmarks:
  default_market: "SPY"
  growth: "QQQ"
  small_cap: "IWM"
  sector_map:
    Technology: "XLK"
    Energy: "XLE"
    Financials: "XLF"
    Healthcare: "XLV"
    Industrials: "XLI"
    Consumer_Discretionary: "XLY"
    Consumer_Staples: "XLP"
    Utilities: "XLU"
    Materials: "XLB"
    Real_Estate: "XLRE"
    Communication_Services: "XLC"

# 语义约束：
# 1) default_market 仅用于补齐记录可读性与降级分组，不得直接进入 alpha 主统计
# 2) 若使用 default_market，必须写入 data_quality_reasons: [benchmark_missing]

data_quality:
  invalid_if:
    - join_key_missing
    - symbol_missing
    - direction_missing
    - decision_price_missing
    - exit_price_missing_after_due
    - market_data_default_used
    - invalid_price_series
  degraded_if:
    - market_data_stale
    - market_data_fallback_used
    - provider_untrusted
    - provenance_field_missing
    - benchmark_missing

stats:
  include_degraded_in_primary_stats: false
  min_bucket_sample_size: 10
  min_total_sample_size: 30

outputs:
  base_dir: "reports/outcome"
  opportunity_outcome_jsonl: "opportunity_outcome.jsonl"
  outcome_summary_json: "outcome_summary.json"
  outcome_report_md: "outcome_report.md"
  outcome_by_score_bucket_json: "outcome_by_score_bucket.json"
  score_monotonicity_report_json: "score_monotonicity_report.json"
  failure_reason_distribution_json: "failure_reason_distribution.json"
  alpha_report_json: "alpha_report.json"
  log_trust_report_json: "log_trust_report.json"
  mapping_attribution_jsonl: "mapping_attribution.jsonl"
  decision_suggestions_json: "decision_suggestions.json"
```

## 16.1 metric_dictionary.yaml 指标注册要求（P0）

路径：configs/metric_dictionary.yaml

Stage6 新增指标必须在 metric_dictionary.yaml 中注册，不得只写在 Python 或报告里。

必须注册的指标：

- hit_rate_t5
- avg_alpha_t5
- avg_return_t5
- score_monotonicity
- mapping_failure_rate
- overblock_rate
- missed_opportunity_rate
- correct_block_rate
- outcome_record_coverage_rate
- resolved_outcome_coverage_rate
- pending_outcome_rate
- join_key_link_rate
- failure_reason_coverage_rate
- valid_outcome_count
- degraded_outcome_count
- invalid_outcome_count
- pending_outcome_count

每个指标必须包含：

- metric key as name
- definition
- formula
- data_source
- output_file
- owner
- quality_rule

说明：

- `metric_dictionary.yaml` 使用 YAML key 作为 metric name，不要求每个 metric 内部重复写 `name` 字段
- 指标定义不得硬编码在 Python 中
- 指标口径必须与 configs/outcome_scoring_policy.yaml 一致

要求：

- 指标定义不得硬编码在 Python 中
- 指标口径必须与 configs/outcome_scoring_policy.yaml 一致
- 指标输出必须能追溯到 reports/outcome/*
- metric_dictionary.yaml 未注册的指标不得进入正式 report
- metric_dictionary.yaml 与 outcome_summary.json / outcome_report.md 不一致 → MAJOR
- 关键指标缺失 → BLOCKER

### 16.2 关键指标公式（P0）

以下公式必须在 `metric_dictionary.yaml` 与 `outcome_summary.json` 保持一致：

- `outcome_record_coverage_rate = (valid_outcome_count + degraded_outcome_count + invalid_outcome_count + pending_outcome_count) / total_opportunities`
- `resolved_outcome_coverage_rate = (valid_outcome_count + degraded_outcome_count + invalid_outcome_count) / eligible_matured_opportunities`
- `pending_outcome_rate = pending_outcome_count / total_opportunities`
- `execute_outcome_coverage_rate = execute_with_outcome_count / total_execute_decisions`
- `join_key_link_rate = linked_outcome_count / total_opportunities`
- `mapping_failure_rate = mapping_failure_count / total_opportunities`
- `failure_reason_coverage_rate = records_with_primary_failure_reason / records_requiring_failure_reason`
- `fallback_rate = market_data_fallback_used_count / total_opportunities`
- `provider_failed_count = count(provider_call_status in ["failed", "timeout", "auth_error"])`
- `orphan_replay = replay_rows_without_decision_match`
- `missing_opportunity_but_execute_count = count(action_after_gate="EXECUTE" and opportunity_id is null)`
- `market_data_default_used_in_execute_count = count(action_after_gate="EXECUTE" and market_data_default_used=true)`

硬约束：

- 分母为 0 时指标必须输出 `null` 且写入 `insufficient_sample`，不得输出 0 伪装通过
- 所有比例类指标必须同时输出分子/分母原值，便于审计复算
- 所有 primary 指标默认仅使用 `data_quality=valid`
- `eligible_matured_opportunities` = 已到对应观测窗口（T+1/T+5/T+20）且可参与结算判定的机会数

示例：

```yaml
stage6_metrics:
  hit_rate_t5:
    definition: "valid resolved_t5 outcomes with outcome_label=hit divided by valid resolved_t5 outcomes"
    formula: "hit_count_t5 / valid_resolved_t5_count"
    data_source:
      - reports/outcome/opportunity_outcome.jsonl
    output_file:
      - reports/outcome/outcome_summary.json
      - reports/outcome/outcome_report.md
    owner: "B"
    quality_rule: "valid only; exclude degraded, invalid, pending"
```

---

## 17. 状态机与 outcome_label 判定规则

### 17.1 状态枚举

| 状态 | 说明 |
|---|---|
| pending_t1 | T+1 未到期 |
| resolved_t1 | T+1 已结算 |
| pending_t5 | T+5 未到期 |
| resolved_t5 | T+5 已结算 |
| pending_t20 | T+20 未到期 |
| resolved_t20 | T+20 已结算 |
| invalid_join_key | join key 无法关联 |
| insufficient_market_data | 市场数据不足 |
| symbol_untradeable | 标的不可交易 |
| invalid_price_series | 价格序列无效 |
| excluded_from_stats | 已排除统计 |

补充：

- `provider_untrusted` 不作为 `outcome_status`，而是进入 `data_quality_reasons` / `failure_reasons`
- `direction` 仅允许 `LONG` / `SHORT`；缺失或未授权值（含 `UNKNOWN`）→ `data_quality=invalid`，不得进入 primary stats

### 17.2 outcome_label 判定规则

#### LONG/SHORT/WATCH/BLOCK 各自判定规则

| 方向 | 条件 | label |
|---|---|---|
| LONG | t5_return >= +2% OR alpha >= +1% | hit |
| LONG | t5_return <= -2% OR alpha <= -1% | miss |
| LONG | 介于之间 | neutral |
| SHORT | t5_return <= -2% OR alpha <= -1% | hit |
| SHORT | t5_return >= +2% OR alpha >= +1% | miss |
| WATCH | 达到 hit 标准 | missed_opportunity |
| WATCH | 未形成机会 | correct_watch |
| WATCH | 市场数据不足/样本不足无法形成明确结论 | neutral_watch |
| BLOCK | 证明避免亏损 | correct_block |
| BLOCK | 达到 hit 标准 | overblocked |
| BLOCK | 未形成明确可交易优势 | neutral_block |

---

## 18. Score Monotonicity 详细定义

### 18.1 核心定义

评分系统必须满足：`score 80+ > score 60-79 > score 40-59 > score <40`

### 18.2 默认分桶

| Bucket | 范围 |
|---|---|
| 80_PLUS | score >= 80 |
| 60_79 | 60 <= score < 80 |
| 40_59 | 40 <= score < 60 |
| LT_40 | score < 40 |

### 18.3 样本不足处理

若任一核心桶样本数低于 `min_bucket_sample_size: 10`：

```
score_monotonicity.status = "insufficient_sample"
```

### 18.4 判定细则（P1）

- 主判定指标：`avg_alpha_t5`
- 辅助判定指标：`hit_rate_t5`

规则：

- 主指标满足单调，辅指标满足单调 → `passed`
- 主指标满足单调，辅指标不满足单调 → `passed_with_warning`
- 主指标不满足单调（无论辅指标如何） → `failed`
- 任一关键分桶样本不足 → `insufficient_sample`

---

## 19. outcome_summary.json 结构

```json
{
  "schema_version": "stage6.outcome_summary.v1",
  "generated_at": "2026-04-26T00:00:00Z",
  "sample_window": {
    "start": "2026-04-01T00:00:00Z",
    "end": "2026-04-26T00:00:00Z"
  },
  "coverage": {
    "total_opportunities": 100,
    "eligible_matured_opportunities": 95,
    "total_execute_decisions": 28,
    "execute_with_outcome_count": 28,
    "valid_outcomes": 82,
    "degraded_outcomes": 10,
    "invalid_outcomes": 3,
    "pending_outcomes": 5,
    "outcome_record_coverage_rate": 1.00,
    "resolved_outcome_coverage_rate": 1.00,
    "pending_outcome_rate": 0.05,
    "execute_outcome_coverage_rate": 1.00,
    "join_key_link_rate": 0.97
  },
  "performance": {
    "hit_rate_t5": 0.57,
    "avg_return_t5": 0.014,
    "avg_alpha_t5": 0.012,
    "mapping_failure_rate": 0.08,
    "false_positive_rate": 0.18,
    "missed_opportunity_rate": 0.11,
    "overblock_rate": 0.09,
    "correct_block_rate": 0.63
  },
  "data_quality_breakdown": {
    "valid": 82,
    "degraded": 10,
    "invalid": 3,
    "pending": 5
  },
  "failure_reason_coverage": {
    "with_primary_failure_reason": 0.94,
    "with_failure_reasons_array": 1.00
  },
  "alpha_quality": {
    "alpha_eligible_count": 76,
    "alpha_excluded_count": 19,
    "alpha_excluded_reasons": {
      "benchmark_missing": 11,
      "invalid_market_data": 8
    }
  },
  "score_monotonicity": {
    "status": "passed",
    "metric": "avg_alpha_t5"
  }
}
```

---

## 20. Decision Layer 限制（P1）

### 允许输出

- suggestion
- evidence
- priority
- requires_human_review

### 禁止

- 自动修改 threshold
- 自动修改 gate
- 自动调整执行逻辑
- 自动更改 final_action
- 任何生产 / 执行 / Gate 模块自动消费 `decision_suggestions.json`

说明：

- `decision_suggestions.json` 只能进入人工 review 流程，作为后续专项 PR 输入
- 未经人工签字的 suggestions 不得进入 runtime 配置或执行链路

### 示例

```json
{
  "generated_at": "2026-04-26T00:00:00Z",
  "decisions": [
    {
      "type": "score_calibration",
      "suggestion": "Review score >= 80 bucket because avg_alpha_t5 underperformed 60_79 bucket.",
      "evidence": "80_PLUS bucket avg_alpha_t5 < 60_79 bucket avg_alpha_t5",
      "priority": "high",
      "requires_human_review": true
    }
  ]
}
```

---

## 21. DoD（完成标准）

本 DoD 中涉及 `reports/outcome/*` 运行产物、outcome engine、idempotency、replay consistency、engine tests 的项目，属于 PR-7b / PR-7 Final 范围，不属于 PR-7a Contract Freeze 的交付要求。

PR-7a = contract freeze
PR-7b = engine / outputs / fixtures / idempotency / replay tests
PR-7 Final = 全量验收

### 必须满足

| 指标 | 阈值 | 证据路径 |
|---|---|---|
| resolved_outcome_coverage_rate | >= 95% | `reports/outcome/outcome_summary.json` |
| outcome_record_coverage_rate | 必须输出 | `reports/outcome/outcome_summary.json` |
| pending_outcome_rate | 必须输出 | `reports/outcome/outcome_summary.json` |
| EXECUTE outcome 覆盖率 | 100% | `reports/outcome/outcome_summary.json` |
| join key 可关联率 | >= 95% | `reports/outcome/log_trust_report.json` |
| valid / degraded / invalid 分类 | 必须 | `reports/outcome/opportunity_outcome.jsonl` |
| score 分布报告 | 必须 | `reports/outcome/outcome_by_score_bucket.json` |
| alpha 报告 | 必须 | `reports/outcome/alpha_report.json` |
| WATCH / BLOCK 归因 | 必须 | `reports/outcome/failure_reason_distribution.json` |
| failure_reason 覆盖率 | 必须输出 | `reports/outcome/outcome_summary.json` |
| score monotonicity 报告 | 必须 | `reports/outcome/score_monotonicity_report.json` |
| outcome_report.md | 必须 | `reports/outcome/outcome_report.md` |
| 10 个输出文件全部生成 | 必须 | `reports/outcome/` |
| registry 已声明 | 必须 | `module-registry.yaml` |
| metric_dictionary 已注册 | 必须 | `configs/metric_dictionary.yaml` |
| mapping / log_trust 报告存在 | 必须 | `reports/outcome/mapping_attribution.jsonl`, `reports/outcome/log_trust_report.json` |
| decision_suggestions 不自动执行 | 必须 | `reports/outcome/decision_suggestions.json` |
| replay 一致性通过 | 必须 | `tests/test_outcome_replay_consistency.py` |
| idempotency 通过 | 必须 | `tests/test_outcome_idempotency.py` |

### 硬性失败条件

- 伪造价格数据
- 伪造 provider 字段
- pending outcome 被当成 resolved
- invalid outcome 进入正式统计
- 缺 join key 仍进入正式统计
- score monotonicity 无样本却强行 passed
- BLOCK / WATCH 没有独立归因
- 测试没有覆盖失败路径

---

## 22. Review Checklist

PR 审核必须检查：

- [ ] 是否没有重写 Stage5 / PR94 主链路
- [ ] 是否没有修改 workflow_runner.py
- [ ] 是否没有修改 decision_gate.jsonl 结构
- [ ] 是否没有修改 execution_emit 逻辑
- [ ] 是否没有修改 Gate 规则
- [ ] 是否没有改变 final_action 语义
- [ ] 是否新增 outcome engine 而不是侵入现有交易执行逻辑
- [ ] 是否所有阈值来自 configs/outcome_scoring_policy.yaml
- [ ] 是否新增 opportunity_outcome.schema.json
- [ ] 是否 pending outcome 不提前归因
- [ ] 是否 invalid outcome 不进入正式统计
- [ ] 是否 data_quality 分类完整
- [ ] 是否 WATCH / BLOCK 独立归因
- [ ] 是否 score monotonicity 有样本不足保护
- [ ] 是否缺失字段不伪造
- [ ] 是否测试覆盖失败路径
- [ ] 是否没有提交真实 logs
- [ ] 是否幂等测试通过
- [ ] 是否重放一致性测试通过
- [ ] 是否 module-registry.yaml 已引用 schema
- [ ] 是否 metric_dictionary.yaml 已注册指标
- [ ] 是否生成 10 个 P0 输出文件
- [ ] 是否 outcome_by_score_bucket.json 已注册到 outputs 配置
- [ ] 是否 resolved_outcome_coverage_rate 与 outcome_record_coverage_rate 分开计算

---

## 23. PR 定位

### 23.1 PR 名称建议

```
feat(stage6): add opportunity outcome attribution engine
```

### 23.2 PR 类型

```
Stage6 / New Feature / Evaluation Layer
```

### 23.3 明确不做

- 不重写 full_workflow_runner.py
- 不重写 workflow_runner.py
- 不修改交易策略语义
- 不自动调参
- 不提交真实 runtime logs
- 不伪造价格 / provider / benchmark 字段
- 不接入 broker 实盘
- 不启动 live mode
- 不实现组合级 PnL

---

## 24. 前置条件

进入 Stage6 PR-7 前必须满足：

- [ ] Stage5 主体已合并
- [ ] Stage5 final acceptance 已完成
- [ ] Residual Evidence Logging PR 已合并
- [ ] decision_gate.jsonl 具备 before/after gate 字段
- [ ] replay_write.jsonl 可用
- [ ] execution_emit.jsonl 可用
- [ ] market_data_provenance.jsonl 具备 provider-call 字段

---

## 25. 成员分工详细展开

### 25.1 A 成员：契约、schema、状态机、门禁规则

**主责范围**：schemas/opportunity_outcome.schema.json, schemas/outcome_by_score_bucket.schema.json, DoD, module-registry.yaml, metric_dictionary.yaml, policy 合规审核

**具体任务**：
- 定义 outcome schema
- 定义 outcome_by_score_bucket 强 schema
- 定义枚举（direction, action, gate_result, outcome_status, outcome_label, data_quality）
- 定义 data_quality gate
- 定义 DoD
- 更新 module-registry.yaml
- 更新 metric_dictionary.yaml
- 审核 outcome_scoring_policy.yaml 的字段/枚举/阈值是否符合契约

**验收标准**：
- [ ] schema 可被测试加载
- [ ] 所有 enum 明确定义
- [ ] invalid/degraded/pending/valid 规则清晰
- [ ] 缺 join key 不得通过正式统计
- [ ] module-registry.yaml 已声明 outcome 模块
- [ ] metric_dictionary.yaml 已注册指标
- [ ] outcome_by_score_bucket.schema.json 已纳入 PR-7a contract artifacts

---

### 25.2 B 成员：归因逻辑、分组口径、score monotonicity

**主责范围**：score bucket, benchmark / alpha 口径, WATCH / BLOCK 标签, failure_reason 分类, mapping_status 枚举

**具体任务**：
- 定义 score bucket（80_PLUS, 60_79, 40_59, LT_40）
- 定义 outcome label 逻辑
- 定义 failure_reason（14类）
- 定义 mapping_status 枚举
- 定义 score monotonicity
- 定义分组统计

**验收标准**：
- [ ] LONG/SHORT hit/miss 规则明确
- [ ] WATCH/BLOCK 标签独立
- [ ] score monotonicity 有样本不足保护
- [ ] alpha benchmark 口径明确
- [ ] mapping_status 枚举完整

---

### 25.3 C 成员：工程实现、报告生成、测试

**主责范围**：scripts/outcome_attribution_engine.py, 输出文件, 测试

**具体任务**：
- 新增 outcome engine
- Engine 最小接口
- 输入读取
- 输出文件
- 价格数据处理

**验收标准**：
- [ ] CLI 可运行
- [ ] 缺输入文件不崩溃
- [ ] 可生成 10 个输出文件
- [ ] invalid / degraded / pending 分类正确
- [ ] 测试覆盖失败路径
- [ ] 幂等测试通过
- [ ] 重放一致性测试通过

---

## 26. 文件整理规则

### 正式文件

```
docs/stage6/
  STAGE6_SCOPE_CANONICAL.md
  stage6_signal_quality_design_v2.1.md
  stage6_signal_quality_implementation_plan_v2.1.md

docs/tasks/
  stage6-pr7-outcome-attribution.md

docs/review/
  pr7_rules_test_mapping.md
```

### 历史资料

```
docs/stage6/archive/
```

### 归档规则

当前 Stage6 唯一执行口径以 v2.1 design + v2.1 implementation plan 为准。archive 目录仅作为历史资料，不作为施工依据。

### 26.1 唯一范围文件（P0）

Stage6 当前 PR-7 的唯一执行口径文件为：

docs/stage6/STAGE6_SCOPE_CANONICAL.md

规则：

- 所有开发、测试、review 以 STAGE6_SCOPE_CANONICAL.md 为准
- 其他设计文档、执行方案、历史材料不得覆盖 canonical 文件定义
- 若 v2.1 文档、任务文件、review mapping、代码实现与 canonical 文件冲突，以 canonical 文件为准
- archive 目录仅作为历史资料，不作为施工依据
- Stage6 新增范围必须先更新 canonical 文件，再更新 task / review mapping / tests
- 未引用 canonical 文件的 PR 不得 formal approve

canonical 文件必须明确：

- Stage6 只读消费 Stage5 已落盘日志
- Stage6 不修改 Gate / final_action / execution / Stage5 日志结构
- Stage6 只输出 reports/outcome/*
- Stage6 不接 broker/live
- Stage6 不做组合 PnL / Paper execution / 完整 PIT backtest
- Stage6 不自动调参
- Stage6 输出仅用于人工审核与后续规则优化

审查规则：

- STAGE6_SCOPE_CANONICAL.md 缺失 → BLOCKER
- PR 描述未引用 canonical 文件 → MAJOR
- 实现与 canonical 文件冲突 → BLOCKER
- archive 文件被当作施工依据 → MAJOR

---

## 27. 测试命令与验证

### 27.1 Schema 测试

```bash
python3 -m pytest -q tests/test_opportunity_outcome_schema.py
```

### 27.2 Engine 测试

```bash
python3 -m pytest -q tests/test_outcome_attribution_engine.py
```

### 27.3 幂等与重放一致性

```bash
python3 -m pytest -q \
  tests/test_outcome_idempotency.py \
  tests/test_outcome_replay_consistency.py
```

### 27.4 全量 Stage6 PR-7 测试

```bash
python3 -m pytest -q \
  tests/test_opportunity_outcome_schema.py \
  tests/test_outcome_attribution_engine.py \
  tests/test_outcome_idempotency.py \
  tests/test_outcome_replay_consistency.py
```

### 27.5 全链路兼容回归

```bash
python3 -m pytest -q \
  tests/test_stage5_log_outputs.py \
  tests/test_system_log_evaluator.py \
  tests/test_residual_evidence_logging_gaps.py \
  tests/test_opportunity_outcome_schema.py \
  tests/test_outcome_attribution_engine.py
```

---

## 28. 合并前硬门禁（完整版）

- [BLOCKER] Stage6 修改 workflow_runner.py
- [BLOCKER] Stage6 修改 decision_gate.jsonl 结构
- [BLOCKER] Stage6 修改 execution_emit 逻辑
- [BLOCKER] Stage6 修改 Gate 规则
- [BLOCKER] Stage6 改变 final_action 语义
- [BLOCKER] outcome engine 依赖真实 logs 才能通过测试
- [BLOCKER] 缺失字段被默认填成假数据
- [BLOCKER] invalid outcome 进入正式统计
- [BLOCKER] pending outcome 被提前 hit/miss
- [BLOCKER] score monotonicity 样本不足仍 passed
- [BLOCKER] WATCH / BLOCK 没有独立归因
- [BLOCKER] 阈值硬编码在 Python 文件中
- [BLOCKER] PR 修改交易主链路语义
- [BLOCKER] 真实 runtime logs 被提交
- [BLOCKER] mock/test 数据进入统计
- [BLOCKER] Log Trust 层未实现
- [BLOCKER] Mapping Attribution 层未实现
- [BLOCKER] Decision Layer 自动改规则
- [BLOCKER] 没有 formal review / approval 闭环
- [BLOCKER] 缺失 docs/stage6/STAGE6_SCOPE_CANONICAL.md 或 PR 未引用 canonical
- [BLOCKER] module-registry.yaml 未声明 outcome 模块
- [BLOCKER] metric_dictionary.yaml 未注册指标

---

## 29. 建议删除/后置清单

当前 Stage6 PR-7 应删除或后置：

1. broker 接入
2. live mode
3. kill switch
4. 组合级 PnL
5. Paper execution v2
6. 完整 PIT backtest engine
7. execution path control
8. workflow_runner.py 修改
9. decision_gate 结构调整
10. execution_emit 逻辑修改
11. provider trust gate 新增
12. market_data_provenance 生产结构扩展
13. Gate 规则新增或修改
14. 自动调参
15. 自动修改评分阈值
16. 自动修改 playbook
17. Dashboard cockpit
18. 回写 Stage5 trace_scorecard
19. 修改 final_action 语义
20. 提高 EXECUTE 覆盖率类 PR

---

## 30. 最终定义

**Stage6 是信号质量验证与结果归因层，用于评估系统推荐是否有效，其输出仅用于人工审核与后续规则优化，不得直接驱动交易执行。**

---

## 31. 一句话总结

Stage6 从现在起按"只读消费上游证据、独立生成 outcome、统计验证信号质量、人工审核后再优化规则"的路线推进；任何修改 Gate、执行、broker、live、组合风控、完整回测、Stage5 日志结构的内容，一律移出当前 PR-7。

**Stage6 输出不得直接驱动交易执行，只能作为人工审核、规则复盘和后续专项 PR 的输入。**
