# PR88 阶段4统一验收清单（A/B/C 联审）

版本：v1.0  
日期：2026-04-24  
适用范围：PR #88（Stage4: Provider / 抓价 / 性能层）

## 0. 验收目标
基于阶段4标准（9.3~9.9），将 C 实现、A 契约校验、B 消费验证收敛为同一份可审计验收闭环，确保“性能提升不破坏语义”。

## 1. 统一门禁（必须同时满足）
- [ ] G1: C 侧交付完成：adapter / batch / cache / failover / queue / idempotency
- [x] G2: A 侧完成兼容与契约校验（含结论与问题ID）
- [ ] G3: B 侧完成消费侧验证（含结论与证据路径）
- [ ] G4: 新旧压测对比有明确改善且无语义回归
- [x] G5: 强制测试 7/8/9 全通过
- [ ] G6: failover 与 cache 行为有可复核证据

任一门禁未满足 => 结论只能是“需修改后再审”。

## 2. C 侧（实现与证据）
### 2.1 实现项
- [ ] MarketDataAdapter 统一入口（active/fallback/deprecated）
- [ ] 单票路径已改 batch 抓价主路径
- [ ] cache 策略（TTL/命中/失效）已落地
- [ ] failover 触发/回切逻辑可观察
- [ ] queue 顺序语义与 ingest_seq/process_seq 校验可追踪
- [ ] idempotency_key 在写入/消费两侧生效

### 2.2 证据项
- [ ] provider 链路元信息（attempted/succeeded/unresolved）
- [ ] cache 命中/未命中证据
- [ ] failover 触发原因、切换链路、恢复时间
- [ ] replay/execution 去重证据（重复请求不重复执行）

## 3. A 侧（兼容与契约签字）
### 3.1 必核项
- [ ] dual-write backward compatibility
- [ ] queue/order/idempotency 契约边界
- [ ] 不破坏状态机/Gate 语义
- [ ] provider 字段与 reject_reason_code/final_reason 契约稳定性

### 3.2 交付模板
- 审核结论：PASS / PASS WITH NOTE / FAIL
- 问题清单：问题ID + 严重级别 + 处置状态
- 证据路径：代码锚点 + 测试锚点 + diff 锚点

### 3.3 A 侧当前签字结论（2026-04-24）
- [x] dual-write backward compatibility
- [x] queue/order/idempotency 契约边界
- [x] 不破坏状态机/Gate 语义
- [x] provider 字段与 reject_reason_code/final_reason 契约稳定性
- 结论：**PASS WITH NOTE**
- 问题ID：无新增 BLOCKER（延续关注项为 C 侧压测对比与三方 formal review 闭环）
- 证据文档：`docs/stage5/member_a_stage4_contract_gate_signoff.md`

## 4. B 侧（消费验证签字）
### 4.1 必核项
- [ ] provider 优化后 sector/ticker/A1/theme_tags 消费不破坏
- [ ] batch/cache 改造后消费稳定性可接受
- [ ] 输出质量与映射逻辑无恶化

### 4.2 B 侧已落地资产（本 PR）
- docs/stage5/member_b_stage4_consumption_validation.md
- docs/stage5/member_b_stage4_rules_test_mapping.md
- tests/fixtures/edt_goldens/member_b_stage4_consumption_cases.json
- tests/test_member_b_stage4_consumption_validation.py

### 4.3 B 侧待补“真实运行数据”口径
- [ ] null/empty rate（按字段维度）
- [ ] fallback/default_used ratio
- [ ] manual review ratio（WATCH/PENDING_CONFIRM/BLOCK）
- [ ] 质量劣化阈值实测结论（相对基线）

## 5. 强制测试（Stage4 Gate 7/8/9）
- [x] 7. dual_write_backward_compat_test
- [x] 8. priority_queue_order_semantics_test
- [x] 9. idempotent_replay_write_test

建议附加（非替代）：
- [ ] batch_price_fetch_consistency_test
- [ ] provider_failover_recovery_test
- [ ] cache_ttl_and_stale_guard_test

## 6. 压测对比（新旧基线）
### 6.1 指标
- [ ] 吞吐（TPS/QPS）
- [ ] P95/P99 延迟
- [ ] 失败率
- [ ] 超时率

### 6.2 语义安全护栏
- [ ] 无新增契约穿透
- [ ] 无新增不可解释 fallback
- [ ] 无 replay/execution 重复触发

## 7. 最终结论（联审签字）
- C 结论：PASS / PASS WITH NOTE / FAIL
- A 结论：PASS / PASS WITH NOTE / FAIL
- B 结论：PASS / PASS WITH NOTE / FAIL

合并条件：A/B/C 三方至少 PASS WITH NOTE，且无 BLOCKER。
