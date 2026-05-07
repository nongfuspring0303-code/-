# [PR-3] Project Health UI: add read-only health radar and daily monitor integration

## Branch Owner
C

## PR Opener
C

## Main Contributor
C；B 协作 daily monitor

## Reviewer / Gatekeeper
A

## 修改文件清单
- canvas/index.html
- canvas/project-health.html
- canvas/project-health.js
- canvas/runtime-config.js
- canvas/styles.css
- scripts/local_daily_project_monitor.sh
- docs/system/local_monitor_setup.md
- docs/pr/pr3_ui_polish_project_health_evidence_pack.md
- .github/workflows/ci.yml
- tests/runner.py
- tests/test_project_health_static_contract.py
- tests/test_local_daily_project_monitor_static.py
- tests/test_project_health_security_rendering.py

## 契约影响
- 不新增写接口
- 不修改 schema
- 不修改 PR-1 / PR-2 核心判定逻辑
- Project Health 页面只读展示

### API Envelope 说明
当前 Project Health 页面消费 `logs/project_gap_report.json`（本地文件），而非通过 `/api/project/*` API Envelope。原因如下：
1. **PR-3 范围约束**：PR-3 定位为纯前端展示层，后端 API 路由属于 PR-1 职责范围。
2. **兼容性设计**：`project-health.js` 已实现 `body.data || body` Envelope 解包逻辑，支持直接读取原始日志或封装后的 API 响应。
3. **测试证据**：已在 `tests/runner.py` 中通过 `test_project_health_js_envelope_dual_compatibility` 验证该逻辑。

## 测试命令和结果摘要
| 命令 | 结果 | 证据 |
|---|---|---|
| python3 tests/runner.py | **PASS (15/15)** | null 防御、XSS 反例、stale 四态、RUNTIME_CONFIG、**API Envelope 双兼容** |
| python -m pytest tests/test_project_health_*.py tests/test_local_daily_*.py | PASS | CI 注册 |
| git diff --name-only origin/main...HEAD | CLEAN | 无 PR116 文件、无 pr117_comments.txt |

## Main Baseline Revalidation
- **Baseline Source**: PR #118 (Merged)
- **Baseline Revalidation Doc**: `docs/pr/post_merge_evidence/main_baseline_revalidation_after_pr115_pr116.md`
- **Arbiter Test Status**: 已确认为 main 预存失败 (`test_multi_event_arbiter.py::test_multi_event_dedup_and_conflict`)。
- **PR 117 影响评估**: 本 PR 仅涉及 UI 与 Monitor 逻辑，未触及 Arbiter 或其底层 Event 链路，不引入或扩大该失败。

## Evidence Pack
docs/pr/pr3_ui_polish_project_health_evidence_pack.md

## 回滚方案
- `git revert` 本 PR
- 或单独回退 `canvas/project-health.html` / `js` / `css`
- 或删除 `scripts/local_daily_project_monitor.sh`
