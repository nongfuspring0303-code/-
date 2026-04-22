# 阶段 3B：规则-测试映射（B 主责）
**版本**：v1.0  
**日期**：2026-04-23  
**角色**：B 主责，A 联审契约触点，C 仅在日志/观测受影响时联审  
**阶段**：阶段 3B（sector / ticker / 伪兜底修复）

## 1. 规则映射总表

> 说明：下列测试锚点分为“现有参考锚点”和“本轮 3B 最小新增锚点”两类。  
> 只要现有锚点不能直接覆盖规则语义，就必须在本 PR 补最小新增测试。

### R-B-S3B-001
- **Rule Statement**：`sectors[]` 最终输出只能来自白名单。
- **Test Anchor**
  - 现有参考锚点：
    - `tests/test_mapping_families.py::test_family_samples_map_expected_chain`
    - `tests/test_asset_validator.py::test_asset_validator_uses_whitelist_and_notes_for_non_whitelist_assets`
    - `tests/test_conduction_mapper_dynamic.py::test_conduction_mapper_filters_invalid_semantic_values`
  - 本轮最小新增锚点：
    - `tests/test_member_b_stage3b_sector_ticker_integrity.py::test_stage3b_sectors_final_output_whitelist_only`

### R-B-S3B-002
- **Rule Statement**：`ticker_pool` 只能来自真源池，不得无依据补全。
- **Test Anchor**
  - 现有参考锚点：
    - `tests/test_opportunity_score.py::test_premium_pool_filters_by_threshold_and_membership`
    - `tests/test_opportunity_score.py::test_premium_pool_keeps_boundary_values`
    - `tests/test_opportunity_score.py::test_premium_pool_reports_stock_sources`
  - 本轮最小新增锚点：
    - `tests/test_member_b_stage3b_sector_ticker_integrity.py::test_stage3b_ticker_pool_requires_truth_source`

### R-B-S3B-003
- **Rule Statement**：不得再出现金融/JPM 伪兜底。
- **Test Anchor**
  - 现有参考锚点：
    - `tests/test_conduction_mapper_dynamic.py::test_conduction_mapper_ignores_unknown_semantic_chain_and_keeps_rule_match`
    - `tests/test_conduction_mapper_dynamic.py::test_trade_talk_context_not_overridden_by_broad_tariff_tokens`
  - 本轮最小新增锚点：
    - `tests/test_member_b_stage3b_sector_ticker_integrity.py::test_stage3b_financial_jpm_fallback_removed`

### R-B-S3B-004
- **Rule Statement**：placeholder 泄漏率 ≤ 1%。
- **Test Anchor**
  - 现有参考锚点：
    - `tests/test_member_b_stage2_mapping_protection.py::test_member_b_stage2_mapping_protection_cases`
    - `tests/test_member_b_stage2_mapping_protection.py::test_member_b_stage2_target_tracking_not_invented`
  - 本轮最小新增锚点：
    - `tests/test_member_b_stage3b_sector_ticker_integrity.py::test_stage3b_placeholder_leakage_under_1_percent`

### R-B-S3B-005
- **Rule Statement**：template collapse 不得把失败路径伪装成正式输出。
- **Test Anchor**
  - 现有参考锚点：
    - `tests/test_conduction_mapper_dynamic.py::test_conduction_mapper_ignores_unknown_semantic_chain_and_keeps_rule_match`
    - `tests/test_conduction_mapper_dynamic.py::test_conduction_mapper_picks_reloaded_chain_config`
  - 本轮最小新增锚点：
    - `tests/test_member_b_stage3b_sector_ticker_integrity.py::test_stage3b_template_collapse_does_not_promote_failure_path`

## 2. 联审边界

### A 联审触点

以下规则若要进入正式 contract / gate 口径，必须给 A 联审：

- `sectors[]`
- `ticker_candidates`
- `theme_tags`
- `A1 target_tracking`
- fallback 与正式结果边界

### C 联审触点

以下情况若影响日志、scorecard、join、traceability，必须给 C 联审：

- 输出字段落盘路径变化
- 观测字段新增/删减
- 回放或联调证据链变化

### B 可独立闭环

以下内容属于 B 的 3B 主责闭环，可先施工再联审：

- `sectors[]` 白名单裁剪
- `ticker_pool` 来源约束
- 金融/JPM 伪兜底删除
- placeholder 清理
- template collapse 收敛

## 3. 规则到验收的最低要求

1. 每条规则都必须有可执行测试锚点。
2. 每条规则都必须能回退到唯一真源文件。
3. 任何“看起来合理”的 fallback，都不等于正式结果。
4. 若现有测试不足以覆盖规则，必须在同一 PR 补最小新增测试，不得只写文档。
