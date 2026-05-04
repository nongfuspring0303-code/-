# PR109 Follow-up Roadmap

> 文件定位：PR109 收口后的后续 PR 规划。不作为 PR109 的继续扩展说明，而是作为 PR110+ 的设计输入。

---

## PR109 Scope

PR109 已完成并收口以下能力：

- Tier1 weighted mapping（10 事件类型权重映射）
- subtype recognition（子类型识别与权重修正）
- sector_weights（板块权重计算与 Top3 输出）
- ticker_pool（候选池 + truth pool 19→46）
- recommendation_guardrails（推荐桶分层：Tier1/watchlist/rejected）
- offline regression eval（离线对比评估 + benchmark 标签）
- benchmark label loading and validation tests

## Explicitly Out of Scope

以下能力故意延后到 PR110+，不在 PR109 范围内：

- expectation_gap（预期差判断）
- market_validation evidence array（市场验证证据数组）
- dominant_driver（主导市场变量识别）
- relative / absolute direction contract（方向语义分层）
- fatigue_score（叙事疲劳）
- time_scale（交易时间尺度）
- execution_suggestion（交易建议）
- path quality eval（路径质量评估）
- consumer mapping（消费者映射表）
- schema version compatibility strategy（版本兼容策略）
- auto trading execution logic（自动交易执行）

## Artifact Boundary

运行产物、报告产物、日志产物禁止入仓。禁止路径：

```
reports/*
logs/*
runtime/*
tmp/*
cache/*
*.log
*_runtime.json
*_debug_dump.json
*_live_output.json
```

如确需保留样例，只允许进入 `tests/fixtures/` 或 `docs/examples/`，且必须脱敏、小样本、可复现。

## 后续 PR 规划

| PR | 内容 |
|:---|------|
| **PR109** | 基础映射层收口（当前） |
| **PR110** | 交易感知因果最小契约：expectation_gap、market_validation、dominant_driver、relative/absolute direction |
| **PR111** | 疲劳 + 生命周期 + 时间尺度：fatigue_score、lifecycle_state、time_scale、decay_profile |
| **PR112** | execution_suggestion only：trade_type / entry_condition / risk_level / overnight_allowed / invalidation_condition；仅供人工审查，不接自动交易执行链路 |
| **PR113** | 路径质量评估：path_accuracy、validation_accuracy、direction_accuracy |
