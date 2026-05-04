# AI 映射回归评估实施规范 v1（基于 PR 审查模板 v2.1 / v2.1-A）

## 1. 当前问题诊断

结论：当前瓶颈不在 AI 语义识别，而在传导映射闭环。

- 已观测：`event_type` 能识别，但 `sectors` 常为空，导致个股推荐触发率低。
- 已观测：存在错误板块归因（典型是误落到 `Healthcare`）。
- 已观测：`ticker` 误报率低，但这是在推荐率很低前提下成立，不能单看该指标。
- 风险：若仅追求推荐率提升，可能引入误报并破坏交易可用性。

审查判定口径（v2.1-A）：

- 必须按 `Producer -> Intermediate Artifact -> Consumer -> Policy/Gate -> Test Evidence` 审查闭环。
- 必须证明：语义输出被传导层真实消费，传导输出被选股层真实消费，且失败路径可审计。

## 2. 固定回归集要求（Benchmark Freeze）

`Benchmark` 固定为 171 条标准新闻样本，作为版本回归唯一基线。

- 禁止在版本对比中替换或删改 Benchmark 样本。
- 允许新增样本，但只能进入 `Validation` 或 `Live` 数据集。
- 若确需调整 Benchmark 标签，必须走单独变更流程并产出“基线迁移报告”。

## 3. 数据集分层设计

### 3.1 Benchmark（固定）

- 规模：171 条（冻结集）。
- 用途：`v_prev vs v_new` 版本回归与门禁。
- 要求：每条样本具备稳定 `sample_id` 与目标标签（event_type、期望板块、期望 ticker）。

### 3.2 Validation（增量）

- 用途：防过拟合，验证规则泛化能力。
- 要求：新增样本不得回写 Benchmark，且覆盖最近新增场景与历史误判场景。

### 3.3 Live（实时）

- 用途：线上观测，不直接作为合并门禁。
- 要求：按日/周滚动汇总，重点监控分布漂移与误映射簇。

## 4. 指标体系（强制）

必须分层采集，不允许只给最终综合分。

### 4.1 语义层（AI）

- `ai_semantic_accuracy`：语义事件类型准确率。
- `ai_confidence_mean`：AI 平均置信度。

### 4.2 传导层（核心）

- `conduction_mapping_accuracy`：传导层映射准确率。
- `sector_recall`：板块识别率。
- `sector_quality_mean`：板块质量均分。
- `empty_mapping_rate`：空映射率（event_type 有值但 sectors 为空）。
- `wrong_mapping_rate`：错误映射率。
- `healthcare_misroute_count`：误映射到 Healthcare 次数（单独硬监控）。
- `mapping_acceptance_mean`：映射接受度均分。

### 4.3 推荐层（输出）

- `stock_recommendation_rate`：个股推荐率。
- `stock_quality_mean`：个股质量均分。
- `ticker_hit_rate`：ticker 命中率。
- `ticker_false_positive_rate`：ticker 误报率。

## 5. Tier 分层评估

### Tier 1（核心交易场景）

- `geo_political`, `energy`, `commodity`, `monetary`

### Tier 2（中频业务场景）

- `earnings`, `merger`, `regulatory`, `tech`, `industrial`

### Tier 3（低频/边缘场景）

- `other`, `natural_disaster`, `shipping`, `healthcare` 等

规则：

- 所有核心指标必须按 `overall + tier1 + tier2 + tier3` 同步输出。
- Tier 1 为主门禁，Tier 2/3 为风险补充视图。

## 6. 版本对比机制（v_prev vs v_new）

每次变更 `conduction_chain.yaml`、语义规则、传导逻辑、个股推荐逻辑后，必须输出对比报告。

对比表最低字段：

- `metric_name`
- `v_prev`
- `v_new`
- `delta`
- `status`（improved / flat / regressed）
- `gate`（pass / fail）

判定规则：

- “提升”：超过最小改进阈值（由策略配置定义）。
- “持平”：在噪声容忍区间内。
- “回退”：低于容忍区间下界或触发硬门禁。

## 7. 验收门槛（当前阶段）

目标门槛：

- 整体板块识别率：`>= 60%`
- Tier 1 板块识别率：`>= 60%`
- 空映射率：`< 5%`
- Healthcare 误映射：`= 0`
- 个股推荐率：`>= 30%`
- 个股质量均分：`>= 40`

硬约束：

- ticker 误报率不得显著恶化（不得以误报换推荐率）。
- 任一硬门禁失败则结论必须为 `REQUEST_CHANGES`。

## 8. 风险点与防护

- 过拟合风险：Benchmark 升、Validation 降。
- 规则误伤：空映射下降但错误映射上升。
- 指标欺骗：推荐率提升但 ticker 误报率恶化。
- 类型偏置：不确定样本被集中归入某固定板块（如 Healthcare）。

防护措施：

- 强制输出错误桶（空映射 TopN、误映射 TopN、Healthcare 误映射样本）。
- 强制输出 Tier1 差异明细样本。
- 强制执行 Benchmark + Validation 双集门禁。

## 9. 与 v2.1 / v2.1-A 的映射

| 模板硬要求 | 本实施规范对应 |
|---|---|
| 契约倒推打表 | 指标分层 + 数据集分层 + 门禁定义 |
| 四方一致性 | Code / Config / Docs / Tests 必须同步 |
| 测试零信任 | Benchmark 冻结 + Validation 防过拟合 + CI 门禁 |
| 生命周期不变量 | 语义 -> 传导 -> 推荐 -> scorecard 全链路审计 |
| 多实体绑定 | 按 trace_id/event_hash/sample_id 做样本级对比 |
| 反例驱动 | 空映射、误映射、Healthcare 偏置、ticker 误报反例 |

## 10. 下一步实施建议

1. 固化 Benchmark171 样本清单与标签文件，建立只读管理规则。
2. 产出统一评估输出 schema（json + markdown）。
3. 实现评估 runner：同批样本同时跑 `v_prev` 与 `v_new`，自动生成 delta 报告。
4. 将硬门禁接入 CI，失败即阻断合并。

