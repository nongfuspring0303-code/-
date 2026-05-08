## C 提交模板（PR123 parse baseline）

### 0) 提交结论
- baseline_type: `PR123_parse_baseline`
- owner: `C`
- reviewer: `A`
- 一句话结论: `PR123 parser baseline 本地复跑通过（32/32），因 base_sha==head_sha，comparison_status=observe_only。`

### 1) 基本信息（必填）
- base_branch: `origin/main`
- base_sha: `6db2d524621ac57ea967844309450c8911637ac3`
- head_sha: `6db2d524621ac57ea967844309450c8911637ac3`
- latest_head_at_submit_time: `6db2d524621ac57ea967844309450c8911637ac3`
- ci_run_id: `N/A（本次为 main 上本地 baseline 复跑）`
- ci_conclusion: `N/A`
- ci_url: `N/A`

### 2) 执行命令与结果（必填）
- test_commands:
  - `python3 -m pytest -q tests/test_ai_semantic_json_parser.py tests/test_ai_semantic_analyzer.py`
- test_results_summary:
  - `32 passed, 0 failed`
- artifacts:
  - `test-only baseline：本轮以 pytest 结果作为基线证据，不产出独立 parse_baseline_report.json`
  - `test-only baseline：本轮以测试断言覆盖 parse_error_type 分类，不产出独立 parse_error_distribution.json`

### 3) 比较口径（必填）
- window_definition: `parser contract baseline replay on merged main (no live traffic window)`
- dedup_rule: `N/A（test-based baseline，无事件去重）`
- filter_rule: `仅 parser 相关测试文件`
- comparison_status: `observe_only`
- 说明:
  - `base_sha == head_sha，按规则使用 observe_only，不宣称优化已生效。`

### 4) 指标快照（必填）
- parse_success_rate: `N/A（本轮为契约测试，不是线上样本统计）`
- parse_failed_rate: `N/A`
- not_called_rate: `N/A`
- parse_error_type_coverage: `1.0（测试证据：tests/test_ai_semantic_json_parser.py::test_parse_failed_always_has_non_empty_parse_error_type）`
  - 定义：`parse_failed_with_type / total_parse_failed`
- provider_error_count: `N/A（未做线上窗口计数）`
- timeout_count: `N/A`
- truncated_response_count: `N/A`
- empty_response_count: `N/A`

### 5) 安全与边界（必填）
- token/secret/raw_response/internal_path/traceback 泄露: `否`
- 白名单外改动: `否（本次仅复跑，无新增改动）`
- 若有 extra file: `N/A`
- execution/Gate/final_action/broker 改动: `否`

### 6) 回滚（必填）
- rollback_note:
  - `本次为复跑提交，无代码变更，无需回滚`
  - `验证命令：python3 -m pytest -q tests/test_ai_semantic_json_parser.py tests/test_ai_semantic_analyzer.py`

### 7) 冻结输入状态（新增）
- freeze_gate_input_ready: `yes`
