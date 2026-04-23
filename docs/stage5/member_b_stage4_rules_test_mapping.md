# 阶段 4：B 侧规则-测试映射骨架
**版本**：v0.1  
**日期**：2026-04-24  
**角色**：B 侧消费验证 / review / sign-off  
**阶段**：阶段 4（Provider / 抓价 / 性能层）

## 1. 规则映射总表

### R-B-S4-001
- **Rule Statement**：provider 优化不得破坏 `sector_candidates` 消费。
- **Test Anchor**：
  - `tests/fixtures/edt_goldens/member_b_stage4_consumption_cases.json`
  - 后续补充的阶段4消费验证测试

### R-B-S4-002
- **Rule Statement**：provider 优化不得破坏 `ticker_candidates` 消费。
- **Test Anchor**：
  - `tests/fixtures/edt_goldens/member_b_stage4_consumption_cases.json`
  - 后续补充的阶段4消费验证测试

### R-B-S4-003
- **Rule Statement**：provider 优化不得导致 `A1` / `theme_tags` 语义漂移。
- **Test Anchor**：
  - `tests/fixtures/edt_goldens/member_b_stage4_consumption_cases.json`
  - 后续补充的阶段4消费验证测试

### R-B-S4-004
- **Rule Statement**：batch/cache/failover/queue 优化不得造成消费侧质量显著恶化。
- **Test Anchor**：
  - `tests/fixtures/edt_goldens/member_b_stage4_consumption_cases.json`
  - 后续补充的阶段4消费验证测试

## 2. 联审边界

### A 联审触点

- queue / order / idempotency 契约边界
- dual-write backward compatibility
- 状态机 / Gate 语义是否被破坏

### C 联审触点

- provider / queue / perf 改动影响日志、trace、scorecard、压测指标时
- 观测字段或落盘结构发生变化时

### B 独立闭环

- 消费字段存在性检查
- 消费字段类型稳定性检查
- fallback / default_used / manual review 比例检查
- 输出质量是否劣化的观察与判断

## 3. 最低要求

1. 每条规则都必须可绑定到后续测试锚点。
2. 每条规则都必须能通过最小样本集复核。
3. 不提前评价 provider 主实现，只评消费侧影响。
4. 若后续 PR 引入新消费字段，必须回补映射表。

