---
title: Consumer Contract Mapping Table
title_zh: 消费者合同映射表
version: v1.0
status: appendix_normative
parent_doc: 主题板块催化持续性引擎 v1.0
---

# Consumer Contract Mapping Table｜消费者合同映射表

## 1. 目的

明确：
- 每个字段来自哪里
- 谁消费
- 是否可空
- 缺失时下游默认行为

## 2. 映射表

| 字段 | 来源模块 | 消费模块 | 可空 | 用途 | 缺失时默认行为 |
|---|---|---|---|---|---|
| primary_theme | theme_mapper | 盘前 / 个股 / 统一裁决 | 否 | 主题识别 | 拒绝高置信消费 |
| current_state | continuation_engine | 盘中 / 过夜 / 统一裁决 | 否 | 状态判断 | 降级为观察 |
| continuation_probability | continuation_engine | 盘前 / 盘中 | 是 | 延续概率 | 不参与排序 |
| trade_grade | trade_adapter | 盘前 / 个股 / 统一裁决 | 否 | 交易评级 | 视为 D |
| candidate_audit_pool | trade_adapter | 个股审计 | 是 | 审计优先池 | 空列表 |
| conflict_flag | routing merge | 统一裁决 / 盘前 | 否 | 冲突判断 | 视为 true 并拦截 |
| conflict_type | routing merge | 统一裁决 / 盘前 | 是 | 冲突分类 | 记录为 unknown_conflict |
| final_decision_source | routing merge | 统一裁决 | 否 | 最终裁决来源 | 视为 mainchain_only |
| macro_regime | main chain | 统一裁决 / 盘前 | 否 | 宏观风险环境 | 视为 MIXED 并保守处理 |
| theme_capped_by_macro | routing merge | 统一裁决 | 否 | 是否触发主链封顶 | 默认 false；仅在宏观回避 / 冲突明确命中时置 true |
| macro_override_reason | main chain | 统一裁决 | 是 | 主链覆盖原因 | 记录 unknown_override_reason |
| final_trade_cap | routing merge | 统一裁决 / 执行前审查 | 否 | 评级/周期封顶结果 | 默认 INTRADAY |
| fallback_reason | all modules | 全部消费端 | 是 | 降级解释 | 记录 unknown_fallback |
| safe_to_consume | all modules | 全部消费端 | 否 | 安全消费开关 | 默认 false |
| contract_name | output envelope | 全部消费端 | 否 | 契约识别 | 拒绝消费 |
| contract_version | output envelope | 全部消费端 | 否 | 版本兼容判定 | 拒绝消费 |
| producer_module | output envelope | 全部消费端 | 否 | 生产方追踪 | 拒绝消费 |

## 3. 一句话裁决

> 字段不是谁想读就读，必须先定义来源、消费者、可空规则与缺省行为。
