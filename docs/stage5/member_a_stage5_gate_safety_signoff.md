# 阶段 5：A 侧 Gate / Safety / Audit 评分口径签字稿
**版本**：v1.0  
**日期**：2026-04-24  
**角色**：A（评分口径签字）/ C（实现主责）/ B（消费评分签字）  
**适用范围**：阶段 5（完整日志 + 评分体系 + 看板）

## 1. 目的与边界

本文件用于闭环阶段 5 的 A 侧职责（负责人矩阵 10.3）：

1. 明确 Gate / Safety / Audit Completeness 评分口径。
2. 明确“评分不得掩盖 blocker”的硬约束。
3. 给出可复跑的规则-测试锚点，作为 A 侧签字依据。

本文件不替代 C 侧实现文档，也不替代 B 侧输出质量评分文档。

## 2. A 侧评分口径（冻结）

### 2.1 A_gate_safety

- 基础分：100
- 扣分项：
  - `market_data_stale=true`：-25
  - `market_data_default_used=true`：-35
  - `market_data_fallback_used=true`：-20
  - 若 `final_action=EXECUTE` 且出现 `stale/default_used`：额外 -20

### 2.2 A_audit_completeness

- 基础分：0，按审计关键键累加：
  - `trace_id` 存在：+30
  - `event_hash` 存在：+30
  - `request_id` 存在：+20
  - `batch_id` 存在：+20

### 2.3 Blocker 可见性与抑制规则（A 侧硬门禁）

若出现任一 Gate blocker：

- `MISSING_OPPORTUNITY`
- `MARKET_DATA_STALE`
- `MARKET_DATA_DEFAULT_USED`
- `MARKET_DATA_FALLBACK_USED`

则必须满足：

1. 在 scorecard 中显式输出：
   - `a_gate_blocker_codes`
   - `a_gate_blocker_count`
   - `a_gate_blocker_present`
2. 对总分执行上限保护：
   - `total_score <= 54`（避免 blocker 路径被高分伪装）
   - 输出 `a_score_cap_applied=true`
3. `a_gate_signoff_ready` 必须为 `false`。

## 3. 规则到测试锚点（A 侧签字依据）

| Rule ID | Rule Statement | Test Anchor |
| --- | --- | --- |
| R-A-S5-001 | Scorecard 必须包含 A 侧 blocker 显式字段。 | `tests/test_stage5_log_outputs.py::test_stage5_pipeline_stage_and_scorecard_written` |
| R-A-S5-002 | 非 EXECUTE 路径（default/stale）必须体现 Gate blocker 且总分被 cap。 | `tests/test_stage5_log_outputs.py::test_stage5_rejected_and_quarantine_written_for_non_execute` |
| R-A-S5-003 | 出现 blocker 时，`a_gate_blocker_*` 与 cap 行为必须稳定成立。 | `tests/test_member_a_stage5_gate_safety_contract.py::test_stage5_a_gate_blockers_are_visible_and_cap_score` |
| R-A-S5-004 | 无 blocker 时，不应触发 cap，且可进入 A 侧 signoff-ready。 | `tests/test_member_a_stage5_gate_safety_contract.py::test_stage5_a_gate_signoff_ready_without_blockers` |

## 4. A 侧签字条件

- [x] Gate/Safety/Audit 评分口径已固定
- [x] blocker 显式字段已落地
- [x] blocker 分数上限保护已落地
- [x] 规则-测试锚点可复跑
- [x] 不以评分掩盖 blocker

## 5. A 侧签字结论

> A-side sign-off: **PASS**  
> 日期：2026-04-24  
> 对应 PR：#90  
> 证据：`scripts/full_workflow_runner.py` + `tests/test_stage5_log_outputs.py` + `tests/test_member_a_stage5_gate_safety_contract.py`

