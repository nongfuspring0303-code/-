# 阶段4（成员C）Provider/抓价/性能层 实施计划

目标：完成阶段4主责交付（MarketDataAdapter、batch抓价、cache、failover、queue顺序语义、幂等语义、附加门禁测试）。

规则基线：`/Users/workmac/.openclaw/workspace/pr-review-template-v2.1.md`

## R-S4-001 统一 Provider 适配层
- 新增 `scripts/market_data_adapter.py`
- 提供 active/fallback/deprecated provider 链
- 运行时配置来源：`runtime.price_fetch.providers.*`

## R-S4-002 Batch 抓价 + Cache
- 在 `MarketDataAdapter.quote_many` 中支持批量抓价
- 支持 `cache_ttl_seconds` 与 `max_batch_size`
- 在 `scripts/opportunity_score.py` 引入批量预取 `_batch_prefetch_prices`

## R-S4-003 Provider Failover
- active provider 失败时自动切换 fallback
- 记录 `last_meta`（attempted/succeeded/unresolved_symbols/from_cache）

## R-S4-004 Config-Runtime Alignment
- 更新 `configs/edt-modules-config.yaml`
- 增加：`max_batch_size`、`timeout_seconds`、`providers.active/fallback/deprecated`

## R-S4-005 阶段4附加门禁测试
- `tests/test_member_c_stage4_provider_perf.py`
  - `test_dual_write_backward_compat_test`
  - `test_priority_queue_order_semantics_test`
  - `test_idempotent_replay_write_test`
- `tests/test_market_data_adapter.py`
  - batch+cache+failover 单元测试

## 验证命令
```bash
python3 -m pytest -q \
  tests/test_market_data_adapter.py \
  tests/test_member_c_stage4_provider_perf.py \
  tests/test_opportunity_score.py::test_entry_zone_uses_realtime_price_first \
  tests/test_opportunity_score.py::test_missing_realtime_price_forces_watch_with_risk_flag
```
