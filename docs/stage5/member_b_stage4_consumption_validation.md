# 阶段 4：B 侧消费验证骨架
**版本**：v0.1  
**日期**：2026-04-24  
**角色**：B 侧消费验证 / review / sign-off  
**阶段**：阶段 4（Provider / 抓价 / 性能层）

## 1. 目的与边界

本文件仅用于准备 B 侧对阶段 4 的消费验证补件框架。

### 1.1 B 侧职责边界

B 只验证 provider / queue / perf 改造后，消费侧是否仍然可用、可解释、可追溯。

### 1.2 B 不负责的内容

- `MarketDataAdapter`
- batch price fetch
- cache
- provider failover
- queue / idempotency 主逻辑
- perf 压测主改造

## 2. 验证对象

- `sector_candidates`
- `ticker_candidates`
- `A1`
- `theme_tags`

## 3. 验证维度

### 3.1 字段存在性

- 关键字段是否仍然出现在最终消费面
- 是否存在字段被移除、改名或降级为不可消费结构

### 3.2 字段类型稳定性

- 字段类型是否保持稳定
- 列表 / 标量 / 字典的结构是否仍可被下游稳定读取

### 3.3 空值率

- `null` / 空字符串 / 占位值是否显著增多
- 是否出现因为 provider 改造导致的消费侧空值泄漏

### 3.4 fallback / default_used 比例

- fallback / default_used 是否上升
- 是否存在“为了让数据看起来可用”而掩盖真实缺失的情况

### 3.5 manual review 比例

- 是否出现更多需要人工复核的消费结果
- 是否存在输出质量变化导致的 review 面扩大

### 3.6 输出质量是否劣化

- sector / ticker / A1 / theme_tags 的消费质量是否下降
- 是否影响 B 侧对输出的复核效率和映射判断

## 4. 最终结论模板

> B-side sign-off: PASS / PASS WITH NOTE / FAIL  
> 结论日期：YYYY-MM-DD  
> 对应 PR：#<number>  
> 证据：消费字段清单 + 验证样本 + 统计结果 + 风险说明

