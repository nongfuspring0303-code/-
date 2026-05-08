## PR122 Chain Baseline Evidence Pack

### 0) 提交结论
- baseline_type: `PR122_chain_baseline`
- owner: `B`
- reviewer: `A`
- 一句话结论: `PR122 chain baseline 补测完成，关键测试与审计命令通过，A 侧同意放行。`

### 1) 基本信息
- base_branch: `main`
- base_sha: `6db2d524621ac57ea967844309450c8911637ac3`
- pr122_head_sha: `5c729f955aa6fc6e7495fa1812a2e66292d4a845`
- local_head_sha: `6db2d524621ac57ea967844309450c8911637ac3`
- pr122_merged_at: `2026-05-08T19:02:57Z`
- ci_run_id: `N/A（本次为本地 baseline 复跑）`
- ci_conclusion: `N/A`
- ci_url: `N/A`

### 2) 执行命令与结果
- test_commands:
  - `python3 -m pytest -q tests/test_opportunity_score.py`
  - `python3 -m pytest -q tests/test_live_chain_audit.py`
- test_results:
  - `tests/test_opportunity_score.py: 19 passed, 1 warning`
  - `tests/test_live_chain_audit.py: 10 passed`
- command_exit_codes:
  - `test_opportunity_score: 0`
  - `test_live_chain_audit: 0`
  - `live_chain_audit_cli: 0`
  - `semantic_mapping_strict_report_cli: 0`
- audit_commands:
  - `python3 scripts/live_chain_audit.py --input tests/fixtures/semantic_chain/sample_chain.jsonl`
  - `python3 scripts/semantic_mapping_strict_report.py --input tests/fixtures/semantic_chain/sample_chain.jsonl`
- audit_results:
  - `live_chain_audit: records_total=3, missing_event_hash_count=0, missing_semantic_trace_id_count=0, event_hash_coverage=1.0, semantic_trace_id_coverage=1.0, primary_sector_only=true`
  - `semantic_mapping_strict_report: strict_join_ready_count=1, strict_join_failed_count=0, event_hash_mismatch_count=0, semantic_trace_id_mismatch_count=0, fallback_pollution=false`
- artifacts:
  - `artifacts/pr122_chain_baseline_20260509_040707`

### 3) 比较口径
- comparison_status: `observe_only`
- window_definition: `fixture-only / no live window replay`
- dedup_rule: `strict key = event_hash + semantic_trace_id`
- filter_rule: `PR122 fixture validation only`

### 4) 指标结论
- strict_join_status: `PASS`
- event_hash_status: `PASS`
- semantic_trace_id_status: `PASS`
- primary_sector_only_status: `PASS`
- secondary_sector_audit_only_status: `PASS`

### 5) 风险与边界
- risk: `本次为基线复跑，未改业务代码。`
- execution/Gate/final_action/broker 改动: `否`
- 白名单外改动: `否`

### 6) 回滚信息
- rollback_note:
  - `本次无代码变更，无需回滚。`
  - `若需复核，复跑上述测试与审计命令。`

### 7) A 侧裁决
- baseline_replay_status: `PASS`
- 需要 A 审查: `yes`
- 是否可以进入 PR124: `yes（A final signoff）`
- freeze_gate_input_ready: `yes`
