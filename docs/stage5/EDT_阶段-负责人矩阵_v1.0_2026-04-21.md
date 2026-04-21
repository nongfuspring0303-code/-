# EDT 阶段-负责人矩阵 v1.0
**版本**：v1.0  
**日期**：2026-04-21  
**用途**：把《施工顺序表》中的阶段 0—5，明确映射到 A / B / C 三成员任务包，解决“知道先做什么，但不知道谁主责、谁配合、哪些必须串行、哪些可以并行”的问题。  
**适用范围**：EDT 交易系统全链路修复、日志增强、输出治理、Provider/性能优化。  

---

# 一、矩阵目的

当前团队文档已经有两层内容：

1. **项目级顺序**
   - 阶段 0 → 阶段 5

2. **成员级职责**
   - A：契约 / Schema / Gate / 状态机 / 兼容层
   - B：sector / ticker / theme / A0/A1 映射一致性
   - C：replay / join / 原始采样 / 队列 / 性能 / 观测

但还缺第三层：

> **阶段 → 负责人 → 配合人 → 串并行规则 → 交付物**

本矩阵就是为了解决这一层缺口。

---

# 二、使用规则

## 规则 1：先看阶段，再看主责
施工时，先确认当前处于阶段 0—5 的哪一段，再按本矩阵确认由谁牵头。

## 规则 2：主责不等于独占
主责人负责：
- 组织
- 主改
- 合并前自检
- 推动验收

配合人负责：
- 提供字段
- 提供消费口径
- 提供兼容性确认
- 提供联审签字

## 规则 3：触点改动必须 Joint Review
凡涉及：
- contract_version
- replay 主键
- market data provenance
- provider 活跃路径
- Gate 输入 / 输出字段
- sector / ticker / A1 关键字段

即使某阶段已有主责，也必须走 Joint Review。

## 规则 4：未满足阶段完成标志，不得进入下一阶段
阶段顺序不允许颠倒。

---

# 三、阶段-负责人矩阵总表

| 阶段 | 阶段名称 | 主责 | 配合 | 是否必须先单独完成 | 是否允许并行 | 核心交付物 |
|---|---|---|---|---|---|---|
| 阶段 0 | 施工准备 | A 全负责执行 | B、C 仅 review / sign-off | 是 | 否 | 基线、样本、flags、rollback、真源锁定 |
| 阶段 1 | 最小可用证据日志 | C 主责 | A、B | 否 | 可与阶段 2 并行 | 4 类关键日志（5 文件） |
| 阶段 2 | P0 blocker | A 主责 | C、B | 否 | 可与阶段 1 并行 | A1 默认值伪装切断、Gate 红线 |
| 阶段 3A | replay / join / 越权修复 | C 主责 | A | 否 | 可与 3B 并行 | replay 主键、join、越权堵死 |
| 阶段 3B | sector / ticker / 伪兜底修复 | B 主责 | A | 否 | 可与 3A 并行 | sector 白名单、ticker_pool、伪兜底清理 |
| 阶段 4 | Provider / 抓价 / 性能层 | C 主责 | A、B | 否 | 原则上串行推进 | adapter、batch、cache、failover、顺序/幂等语义 |
| 阶段 5 | 完整日志 + 评分体系 + 看板 | C 实现主责 | A、B 共同签字 | 否 | 可分模块并行 | stage log、scorecard、health daily、看板 |

---

# 四、阶段 0：施工准备

## 4.1 主责
**A 全负责执行**

## 4.2 为什么由 A 全负责执行
因为阶段 0 涉及的核心事项包括：
- `contract_version`
- dual-write
- feature flags
- rollback
- schema / config / registry 真源锁定
- Joint Review 触点清单

这些都属于 A 的契约 / Gate / 兼容层执行范围，因此阶段 0 由 A 统一负责落地，B/C 只做审核与 sign-off。

## 4.3 B 的 review / sign-off 任务
- review sector 白名单唯一真源
- sign-off 映射类黄金样本
- Joint Review `semantic_event_type / sector_candidates / ticker_candidates` 的消费侧需求
- 审核 `theme_tags / A0 / A1` 不会被后续 blocker 修复破坏
- 审核执行结果与门禁是否满足

## 4.4 C 的 review / sign-off 任务
- review replay / join / orphan 样本
- sign-off raw ingest / quarantine 相关样本
- Joint Review 压测基线与观测位
- 审核 rejected / quarantine 流是否满足阶段 0 门禁
- 审核执行结果与门禁是否满足

## 4.5 本阶段必须单独先做
**是。**  
阶段 0 是所有正式编码前的前置准备阶段，必须先单独完成。

## 4.6 核心交付物
- 普通基线快照
- 压测基线快照
- 黄金样本
- feature flags
- rollback 条件
- rollback sanitization 脚本清单
- schema/config 真源锁定清单
- Joint Review 触点清单

## 4.7 完成标志
- [ ] A 已完成阶段0全部交付物
- [ ] B 已完成审核
- [ ] C 已完成审核
- [ ] Go / No-Go 门禁满足

---

# 五、阶段 1：最小可用证据日志

## 5.1 主责
**C 主责**

## 5.2 为什么由 C 主责
阶段 1 的 4 类关键日志，核心都落在：
- raw ingest
- replay / execution
- observability
- 日志落盘
- 运行证据

这些是 C 的明确主责区。

## 5.3 A 的配合任务
- 定义日志 schema / contract 字段
- 定义 provenance 相关字段命名
- 定义 Gate reject reason code
- 审核日志字段是否与 contract_version / dual-write 兼容

## 5.4 B 的配合任务
- 指定 B 侧必须消费的日志字段
- 明确 sector / ticker / A1 / theme_tags 相关日志摘要需求
- 确保后续评分和映射验收可直接使用这些日志

## 5.5 核心交付物
**4 类关键日志（5 个落盘文件）**
1. `raw_news_ingest.jsonl`
2. `market_data_provenance.jsonl`
3. `decision_gate.jsonl`
4. Replay / Execution 分离日志：
   - `replay_write.jsonl`
   - `execution_emit.jsonl`

## 5.6 串并行规则
- 可与阶段 2 **并行**
- 不必等阶段 2 全部修完
- 但必须保证阶段 2 的 provenance / Gate 修复字段可被本阶段日志承接

## 5.7 完成标志
- [ ] C 已完成 5 个落盘文件
- [ ] A 已完成字段与 schema 审核
- [ ] B 已确认这些日志可支撑后续映射验收
- [ ] trace_id 可贯穿串联

---

# 六、阶段 2：P0 blocker

## 6.1 主责
**A 主责**

## 6.2 为什么由 A 主责
阶段 2 的核心动作是：
1. 切掉 A1 默认值伪装
2. 给 MarketValidator 加 provenance 防线
3. 把 `missing opportunity / stale / default / fallback -> no EXECUTE` 放进 Gate

这些本质上属于：
- 契约
- 执行边界
- Gate
- 状态机
- provenance 规则

所以 A 必须主责。

## 6.3 C 的配合任务
- 把 provenance 字段真正落盘
- 为 `decision_gate.jsonl` 提供阻断证据
- 验证 replay / execution 不会绕过 blocker
- 生成相关 blocker test 的运行证据

## 6.4 B 的配合任务
- 确认 A1 / target_tracking 不被误伤
- 检查 blocker 修复不会误杀 sector/ticker 映射链路
- 识别是否有 B 侧必须透传的新字段

## 6.5 核心交付物
- A1 默认值伪装切断
- MarketValidator provenance 防线
- Gate 红线：
  - `missing opportunity -> no EXECUTE`
  - `market_data_stale -> no EXECUTE`
  - `market_data_default_used -> no EXECUTE`
  - `market_data_fallback_used -> no EXECUTE`

## 6.6 串并行规则
- 可与阶段 1 **并行**
- 但合并前必须和阶段 1 的日志字段对齐
- 阶段 2 未完成，不得进入阶段 3

## 6.7 完成标志
- [ ] A 已切断默认值伪装
- [ ] C 已提供阻断证据日志
- [ ] B 已确认映射链未被误伤
- [ ] blocker 测试通过

---

# 七、阶段 3A：replay / join / 越权修复

## 7.1 主责
**C 主责**

## 7.2 为什么由 C 主责
这部分核心是：
- replay 主键
- join
- writer / validator
- execution 越权
- orphan replay

这都属于 C 的主责区。

## 7.3 A 的配合任务
- 定义 replay 主键字段
- 定义 `idempotency_key`
- 审核 `tradeable=false > final_action`
- 审核 replay / execution 与 Gate 的契约一致性

## 7.4 B 的配合任务
- 原则上仅旁观
- 若 replay 字段影响 B 侧映射消费，再参加联审

## 7.5 核心交付物
- `event_trace_id / request_id / batch_id / event_hash`
- replay 主键完整率提升
- orphan replay 清零
- 无 opportunity 仍 EXECUTE 的路径堵死

## 7.6 串并行规则
- 可与阶段 3B **并行**
- 合并前统一由 A 做 Gate / 契约收口

## 7.7 完成标志
- [ ] C 已实现 writer / join / validator
- [ ] A 已完成字段定义与收口
- [ ] replay 主键完整率 = 100%
- [ ] orphan replay = 0

---

# 八、阶段 3B：sector / ticker / 伪兜底修复

## 8.1 主责
**B 主责**

## 8.2 为什么由 B 主责
这部分核心是：
- sector 白名单
- ticker_pool
- broad sector / sub-sector 一致性
- 删除金融/JPM 伪兜底
- 清 placeholder / template collapse

这些都明显属于 B 的映射主责区。

## 8.3 A 的配合任务
- 确认 sector / ticker / theme_tags 相关字段契约
- 确认 fallback 不再伪装为正式结果
- 审核输出进入 Gate 前的结构完整性

## 8.4 C 的配合任务
- 若上述修复影响日志落盘、scorecard、join，参与联审
- 不作为主责

## 8.5 核心交付物
- `sectors[]` 白名单闭环
- ticker_pool 闭环
- 金融/JPM 伪兜底删除
- placeholder 泄漏下降
- template collapse 收敛

## 8.6 串并行规则
- 可与阶段 3A **并行**
- 但最终统一合并前，必须经过 A 的契约/Gate 收口
- 阶段 3A / 3B 任一未完成，不得进入阶段 4

## 8.7 完成标志
- [ ] B 已完成 sector / ticker 真源收口
- [ ] A 已完成契约与 Gate 收口
- [ ] `sectors[]` 非白名单占比 = 0
- [ ] placeholder 泄漏率 ≤ 1%

---

# 九、阶段 4：Provider / 抓价 / 性能层

## 9.1 主责
**C 主责**

## 9.2 为什么由 C 主责
阶段 4 的动作包括：
- `MarketDataAdapter`
- batch 抓价
- cache
- failover
- queue 顺序语义
- 幂等语义
- 压测对比

这些都属于 provider / queue / perf / observability 领域，是 C 的主责区。

## 9.3 A 的配合任务
- dual-write backward compatibility
- queue/order/idempotency 的契约边界
- 审核是否破坏状态机/Gate 语义

## 9.4 B 的配合任务
- 确认 provider 优化后不会破坏 sector / ticker / A1 / theme_tags 消费
- 验证输出质量与映射逻辑未因性能改造恶化

## 9.5 核心交付物
- `MarketDataAdapter`
- batch price fetch
- cache
- provider failover
- config-runtime alignment
- queue 顺序语义与幂等语义修复

## 9.6 强制测试
本阶段必须额外通过：
7. `dual_write_backward_compat_test`
8. `priority_queue_order_semantics_test`
9. `idempotent_replay_write_test`

## 9.7 串并行规则
- 本阶段原则上**串行推进**
- 因为 perf / provider / queue 改动面大，容易产生二次冲突
- 完成前不得进入阶段 5

## 9.8 完成标志
- [ ] C 已完成 adapter / batch / cache / failover
- [ ] A 已完成兼容与契约校验
- [ ] B 已完成消费侧验证
- [ ] 压测基线较旧基线有明确改善
- [ ] 第 7-9 项附加门禁测试全部通过

---

# 十、阶段 5：完整日志 + 评分体系 + 看板

## 10.1 主责
**C 实现主责，A/B 共同签字**

## 10.2 为什么这样分
阶段 5 要补的是：
- `pipeline_stage.jsonl`
- `rejected_events.jsonl`
- `quarantine_replay.jsonl`
- `provider_health_hourly.json`
- `trace_scorecard.jsonl`
- `system_health_daily.json`
- `system_log_evaluator.py`
- 看板 / 日报

这些落在实现上，显然是 C 主责。  
但评分口径里：
- Gate / 安全边界 → A 必须签字
- sector/ticker / 输出质量 → B 必须签字
- provider/freshness/traceability → C 主责定义

## 10.3 A 的配合任务
- 定义 Gate / Safety / Audit Completeness 相关评分口径
- 审核评分不会掩盖 blocker

## 10.4 B 的配合任务
- 定义 sector / ticker / 输出质量评分口径
- 审核 scorecard 是否能支撑映射验收

## 10.5 核心交付物
- stage log
- quarantine / rejected
- provider health
- trace scorecard
- daily health
- evaluator
- 看板

## 10.6 串并行规则
- 阶段 5 内部可分模块并行
- 但最后统一由 A/B/C 对评分口径联合签字

## 10.7 完成标志
- [ ] C 已完成日志扩展与评估器
- [ ] A 已签字安全 / Gate / 审计评分口径
- [ ] B 已签字输出质量 / 映射评分口径
- [ ] 每日评分自动产出
- [ ] 系统有统一健康总评

---

# 十一、最简阶段负责人摘要

## 阶段 0
- **A 全负责执行**
- B/C 仅 review / sign-off
- **必须先单独完成**

## 阶段 1
- **C 主责**
- A 定义字段
- B 提供消费字段需求

## 阶段 2
- **A 主责**
- C 配合落盘与阻断证据
- B 配合校验 A1 / 映射不失真

## 阶段 3A
- **C 主责**
- A 配合收口

## 阶段 3B
- **B 主责**
- A 配合收口

## 阶段 4
- **C 主责**
- A/B 配合验收

## 阶段 5
- **C 实现主责**
- A/B 共同签字评分口径

---

# 十二、一句话结论

当前 v1.0.2 已经写清了“阶段顺序”和“A/B/C 职责”，但真正开工前还需要这一张矩阵，把每个阶段明确映射到负责人。  
按这张矩阵执行后，团队才不会出现：

- 知道先做什么
- 但不知道谁先动手
- 谁配合
- 哪些要串行
- 哪些可以并行
