# 同伴复核 Checklist（阶段四修正）

日期：2026-04-09

## A. 文档一致性

- [ ] 主文件已更新：`阶段三完成度+阶段四规划.md`（含第十二章）
- [ ] 执行记录存在：`阶段四自动修正执行记录-20260409.md`
- [ ] 本轮计划存在：`docs/superpowers/plans/2026-04-09-phase4-mapping-completion-plan.md`

## B. 映射补齐复核（A/B/D/F/G）

- [ ] `configs/conduction_chain.yaml` 存在以下链路：
  - [ ] `liquidity_stress_chain`（A）
  - [ ] `public_health_chain`（B）
  - [ ] `geo_risk_chain`（D）
  - [ ] `macro_data_chain`（F）
  - [ ] `market_structure_chain`（G）
- [ ] `event_to_chain_mapping` 已有对应关键词映射（A/B/D/F/G）

## C. 错配安全复核

- [ ] `scripts/conduction_mapper.py` 已实现关键词匹配强度（短语优先于 token）
- [ ] `scripts/conduction_mapper.py` 已实现类别默认链路（A/B/C/D/E/F/G）
- [ ] 贸易会谈类样本不会误入 `tariff_chain`

## D. 门禁与 CI 复核

- [ ] 新脚本存在：`scripts/verify_mapping_quality.py`
- [ ] CI 已接入 mapping gate：`.github/workflows/ci.yml`
- [ ] 门禁参数为：`--min-family-coverage 1.0 --min-precision 0.9`

## E. 测试文件复核

- [ ] `tests/test_mapping_families.py` 存在并覆盖 A/B/D/F/G 样本
- [ ] `tests/test_conduction_mapper_dynamic.py` 含错配与热更新场景

## F. 必跑命令（复核执行）

```bash
python3 -m pytest -q
python3 scripts/verify_mapping_quality.py --min-family-coverage 1.0 --min-precision 0.9
python3 scripts/verify_sector_coverage.py --min-coverage 0.90
python3 scripts/verify_dedupe_accuracy.py --min-accuracy 0.95
python3 scripts/verify_direction_consistency.py --min-rate 0.85
```

期望结果：
- [ ] `pytest` 全绿（当前基线：`197 passed`）
- [ ] `verify_mapping_quality` 返回 `passed: true`
- [ ] 其余 3 个门禁返回 `passed: true`

## G. 结论签字

- 复核人：____________
- 复核日期：____________
- 结论：
  - [ ] 通过（可进入下一阶段）
  - [ ] 有条件通过（需补充项：________________）
  - [ ] 不通过（问题清单：________________）

## H. 增量复核（板块别名字典 + Energy 候选恢复）

- [ ] 新增配置存在：`configs/sector_aliases.yaml`
- [ ] `scripts/opportunity_score.py` 已实现 alias canonical 归一（`sectors` + `stock_candidates`）
- [ ] 回归测试存在并通过：`tests/test_opportunity_score.py::test_fallback_pool_supports_sector_alias_dictionary`
- [ ] 运行日志中可见 `opportunity_update` 包含 `XOM`：`logs/event_bus_history.jsonl`
- [ ] 网页实测：`Energy` 新闻卡下可见 `XOM` 机会卡（可为 `WATCH`）

## I. 全量任务复核（从拉取最新版后到当前）

### I.1 计划与执行链路完整性
- [ ] 计划文件存在：`docs/superpowers/plans/2026-04-09-phase4-p0-p1-implementation-plan.md`
- [ ] 计划文件存在：`docs/superpowers/plans/2026-04-09-phase4-mapping-completion-plan.md`
- [ ] 计划文件存在：`docs/superpowers/plans/2026-04-09-sector-alias-dictionary-implementation-plan.md`
- [ ] 执行记录已同步：`阶段四自动修正执行记录-20260409.md`
- [ ] 主文件已同步增量章节：`阶段三完成度+阶段四规划.md`

### I.2 P0/P1 能力复核（代码与测试点）
- [ ] P0-1 实时行情失败形态：`scripts/data_adapter.py` + `tests/test_data_adapter.py`
- [ ] P0-2 新闻源强失败（非静默 fallback）：`scripts/ai_event_intel.py` + `tests/test_ai_event_intel.py`
- [ ] P0-3 实时价优先评分 / 缺实时价强制 WATCH：`scripts/opportunity_score.py` + `tests/test_opportunity_score.py`
- [ ] P0-4 schema 默认统一 v1.0：`scripts/ai_event_intel.py` + `scripts/ai_signal_adapter.py`
- [ ] P1 EventBus 落盘恢复：`scripts/event_bus.py` + `tests/test_event_bus.py`
- [ ] P1 CI 门禁接入：`.github/workflows/ci.yml`

### I.3 中后段任务复核（阶段四追加）
- [ ] 语义层基础：`scripts/ai_semantic_analyzer.py` + `tests/test_ai_semantic_analyzer.py`
- [ ] 语义+规则传导选择：`scripts/ai_conduction_selector.py` + `scripts/conduction_mapper.py`
- [ ] Master/Worker 推送门禁：`scripts/realtime_news_monitor.py` + `tests/test_master_worker_consistency.py`
- [ ] conduction_chain 热更新：`scripts/config_center.py` + `tests/test_conduction_mapper_dynamic.py`
- [ ] websockets API 迁移：`scripts/event_bus.py` + `tests/test_event_bus.py`
- [ ] healthcheck dev/prod 门禁：`scripts/system_healthcheck.py` + `tests/test_system_healthcheck.py`
- [ ] 映射族补齐（A/B/D/F/G）：`configs/conduction_chain.yaml` + `tests/test_mapping_families.py`
- [ ] 映射质量门禁：`scripts/verify_mapping_quality.py`

### I.4 本轮新增修复复核（新闻时间 + 板块别名）
- [ ] `event_update.news_timestamp` 优先级生效：`scripts/realtime_news_monitor.py`
- [ ] 回归测试通过：`tests/test_realtime_news_monitor.py::test_push_event_update_uses_detected_at_as_news_timestamp`
- [ ] 配置化板块别名生效：`configs/sector_aliases.yaml` + `scripts/opportunity_score.py`
- [ ] 回归测试通过：`tests/test_opportunity_score.py::test_fallback_pool_supports_sector_alias_dictionary`
- [ ] 运行证据存在：`logs/event_bus_history.jsonl` 中可见 `news_timestamp` 与 `XOM`

### I.5 建议复跑命令（最小可复核集）

```bash
python3 -m pytest tests/test_opportunity_score.py tests/test_conduction_mapper_dynamic.py tests/test_realtime_news_monitor.py -v
python3 scripts/verify_mapping_quality.py --min-family-coverage 1.0 --min-precision 0.9
python3 scripts/verify_sector_coverage.py --min-coverage 0.90
python3 scripts/verify_dedupe_accuracy.py --min-accuracy 0.95
python3 scripts/verify_direction_consistency.py --min-rate 0.85
```

期望结果：
- [ ] 三个核心测试文件全部 PASS
- [ ] 四个验证脚本均返回 `passed: true`

## J. 依据两份主证据文档的交叉复核补充

### J.1 与《阶段三完成度+阶段四规划.md》对齐
- [ ] 第十二章 12.2 的“已落地任务对照”逐项可在仓库文件中定位（不少于 15 项）
- [ ] 第十二章 12.3 的 7 条验证命令可复跑，结果与文档一致
- [ ] 第十二章 12.4 的复核顺序已执行（计划 -> 追加计划 -> 执行记录 -> 命令复跑）
- [ ] 第十三章“板块别名字典 + Energy 候选恢复”内容可被代码与日志证据支撑

### J.2 与《阶段四自动修正执行记录-20260409.md》对齐
- [ ] Task 1-6（P0/P1）与 Task 7-12（追加任务）均有对应代码文件与测试文件
- [ ] 执行记录中的验证阶段演进可解释：`176 passed` -> `190 passed` -> 当前基线
- [ ] 增量记录 7.3 的三类证据齐备：测试通过 / 日志存在 / 页面可见
- [ ] 执行记录中的环境说明已核实（含 `.worktrees/phase4-auto-fix`）

### J.3 关键证据抽样（建议截图或粘贴关键行）
- [ ] `logs/event_bus_history.jsonl` 最新 `event_update` 含 `news_timestamp`
- [ ] `logs/event_bus_history.jsonl` 最新 `opportunity_update` 含 `symbol: XOM`
- [ ] 页面截图包含：新闻标题、`新闻时间|推送时间`、`Energy` 板块、`XOM` 机会卡

### J.4 结论口径统一（复核人填写）
- [ ] 结论为“通过”前，J.1/J.2/J.3 不得有未完成项
- [ ] 若“有条件通过”，需在结论处写明缺口与补齐截止时间
