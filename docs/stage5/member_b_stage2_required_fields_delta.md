# Member B Stage2 Required Fields Delta
**Version**: v1.0  
**Date**: 2026-04-22  
**Role**: Member B review / sign-off for Stage2 output-gate hardening  
**Scope**: Minimal field delta for B-side mapping protection and blocker review.

---

## Field Delta Table

| 字段名 | 来源日志 | 是否 B 必需 | 用途 | 为什么阶段2必须保留 |
| --- | --- | --- | --- | --- |
| `has_opportunity` | `decision_gate.jsonl` / execution input | 是 | 区分“无机会”与“有机会但被拦截” | Blocker 修复后必须保留机会语义，防止误把无机会和被拦截混成一类 |
| `market_data_present` | `market_data_provenance.jsonl` / `decision_gate.jsonl` | 是 | 判断市场数据是否真的可用 | Stage2 blocker 需要承接 provenance 结果，不能把缺数据伪装成有数据 |
| `market_data_source` | `market_data_provenance.jsonl` / `decision_gate.jsonl` | 是 | 识别来源是 direct / derived / default / fallback | 方便 B 判断拦截原因是否来自数据源降级 |
| `market_data_stale` | `market_data_provenance.jsonl` / `decision_gate.jsonl` | 是 | 识别 stale 拦截 | Stage2 的重点就是不让 stale 数据误放行 |
| `market_data_default_used` | `market_data_provenance.jsonl` / `decision_gate.jsonl` | 是 | 识别 default 兜底 | default 兜底必须可见，否则 B 无法复盘误杀或误放行 |
| `market_data_fallback_used` | `market_data_provenance.jsonl` / `decision_gate.jsonl` | 是 | 识别 fallback 兜底 | fallback 兜底必须单独记录，避免与 default 混淆 |
| `validation_state` | `market_data_provenance.jsonl` | 是 | 说明 provenance 校验状态 | B 需要知道 provenance 校验是通过、降级还是失败 |
| `final_action` | `decision_gate.jsonl` / replay / execution logs | 是 | 记录最终门禁动作 | B 侧 review 需要直接看到 gate 最终动作 |
| `final_reason` / blocker reason | `decision_gate.jsonl` | 是 | 记录为什么被拦 | blocker 解释必须可审计，否则无法做 mapping 验收 |

---

## Notes

- B 侧必须直接消费的字段，应优先从持久化日志读取，不应依赖临时 runtime 对象。
- 当前仓库可见的执行契约里没有单独的 `target_tracking` runtime 字段；如果未来要新增该字段，需先做 joint review，再更新本表。

