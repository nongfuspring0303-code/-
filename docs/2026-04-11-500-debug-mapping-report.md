# 2026-04-11 调试报告：event-update 500 与新闻->板块->个股落盘链路

## 1. 背景与目标

### 1.1 背景
- 在本地运行 `./run_local.sh` 后，`realtime_news_monitor` 能抓取新闻，但出现：
  - `POST /api/ingest/event-update` 返回 `500`
  - `logs/event_bus_live.jsonl` 中几乎只有 `event_update`
  - 缺少 `sector_update` / `opportunity_update`，无法做完整映射研究。

### 1.2 本次目标
1. 找到 `500` 根因并修复。
2. 验证事件可稳定入总线（`event_update` 不再 500）。
3. 验证 `sector_update` / `opportunity_update` 能落盘。
4. 给出后续可执行改动计划，供成员并行推进。

---

## 2. 测试方法

## 2.1 调试方法论
- 先证据后修复：先复现并抓日志，再做最小改动。
- 分层定位：
  1) API 接口层（`config_api_server.py`）
  2) 发布层（`run_c_module_stack.py` 的 `publish_from_api`）
  3) EventBus 主循环层（`event_bus.py`）
  4) 新闻监控调度层（`realtime_news_monitor.py`）
- 最小改动验证：只改一处，重跑同样流程对比结果。

### 2.2 数据与证据文件
- 事件总线落盘：`logs/event_bus_live.jsonl`
- 调试运行日志：`/tmp/edt_debug_fix.log`
- 基线统计文档：`docs/mapping-research-baseline-20260411.md`

---

## 3. 测试过程（逐步）

### 3.1 基线统计（修复前）
对历史 `logs/event_bus_live.jsonl` 做统计（按 `payload.type`）：
- 消息类型：仅 `event_update`
- 事件轨迹（按 `trace_id`）存在，但 `sector_update` / `opportunity_update` 为 0

结论：在当前落盘证据中，链路停留在事件层，无法计算映射质量。

### 3.2 复现 500
启动本地栈后观察日志（此前采样）：
- 出现 `POST /api/ingest/event-update HTTP/1.1" 500`
- 同时看到 `publish event failed` 日志。

### 3.3 根因定位
关键链路：
- `config_api_server.py` 在 ingest 路由中调用 `_publish_event(...)`。
- `_publish_event(...)` 调用 `run_c_module_stack.py` 注入的 `publish_from_api(...)`。
- `publish_from_api(...)` 内部使用：`fut.result(timeout=5)` 等待 `bus.publish(...)` 完成。

结合代码与日志定位到阻塞点：
- `run_c_module_stack.py` 使用 `news_task = asyncio.create_task(news_monitor.run_loop_async())`
- `realtime_news_monitor.py` 的 `run_loop_async()` 内直接调用同步 `run_once()`
- `run_once()` 包含网络请求和 A/B 流水线同步计算（重 CPU/IO）
- 导致 EventBus 所在事件循环被阻塞，`fut.result(timeout=5)` 超时并抛异常，API 返回 500。

### 3.4 最小修复
修改文件：`scripts/realtime_news_monitor.py`

修改点（`run_loop_async`）：
- 修复前：`triggered = self.run_once()`
- 修复后：`triggered = await asyncio.to_thread(self.run_once)`

目的：将同步耗时逻辑放入线程池执行，避免阻塞主事件循环。

### 3.5 修复后验证
重启栈并观察 `/tmp/edt_debug_fix.log`：
- `POST /api/ingest/event-update` 返回 `200`
- 日志出现 `✅ 推送新闻预览到C模块成功`
- 未再出现同类 500。

### 3.6 打通下游落盘验证
为确保板块/个股链路可落盘，执行了可触发新闻注入（含关键词 + 完整字段）：
- 通过 `RealtimeNewsMonitor._process_news(news)` 驱动 A/B。
- 日志出现：
  - `✅ A/B计算完成`
  - `✅ 推送板块到C模块成功`
  - `✅ 推送机会到C模块成功`

随后统计 `logs/event_bus_live.jsonl` 的新增消息：
- `event_update`: 12
- `sector_update`: 1
- `opportunity_update`: 1

结论：链路在技术上已打通，`sector/opportunity` 已可落盘。

---

## 4. 测试结果总结

### 4.1 本次已确认通过
1. `event-update 500` 问题可复现、已定位、已通过最小改动修复。
2. 修复后 ingest 返回恢复为 `200`。
3. `sector_update` / `opportunity_update` 已有实证落盘（至少 1 条）。

### 4.2 当前仍存在的业务层问题
- 自然新闻流下，`sector/opportunity` 产出仍偏少。
- 根因偏向“触发门控策略”而非链路故障：
  - `EventCapture` 关键词库偏英文，中文新闻命中不足。
  - 语义分析受超时/限流影响时，常回到 `abstain`。

这会导致“技术链路通了，但自然样本下游信号稀疏”。

---

## 5. 后续改动计划（建议拆分给两位成员）

## 5.1 计划A：提升自然流触发率（成员1）
目标：提高自然新闻下 `captured=True` 比例，增加下游样本量。

建议改动：
1. 扩充 `modules.EventCapture.params.keywords`（补中文宏观/政策/行业词）。
2. 审核 `ai_confidence_threshold` 与 `runtime.semantic.min_confidence` 的联动阈值。
3. 对高价值类别（关税/制裁/央行）增加规则优先兜底。

验收指标：
- 自然流 1 小时窗口内：`sector_update` 覆盖率明显高于当前基线。

### 5.2 计划B：映射质量度量自动化（成员2）
目标：让“新闻->板块->个股”质量可量化。

建议改动：
1. 新增映射统计脚本（读取 `event_bus_live.jsonl`）。
2. 输出核心指标：
   - event->sector 覆盖率
   - event->opportunity 覆盖率
   - direction 一致率（若有标注）
3. 生成日报/快照到 `docs/` 或 `logs/`。

验收指标：
- 每次回归可一键产出同口径指标，支持前后对比。

### 5.3 计划C：稳态防回归（我继续）
目标：防止同类事件循环阻塞问题回归。

建议改动：
1. 增加回归测试：验证 `run_loop_async` 不阻塞发布。
2. 给 `publish_from_api` 增加更明确的超时异常日志（区分 timeout / other errors）。
3. 增加启动阶段健康探针（EventBus ready 后再启动 monitor）。

---

## 6. 交付物清单
- 调试修复代码：`scripts/realtime_news_monitor.py`
- 基线报告：`docs/mapping-research-baseline-20260411.md`
- 本详细报告：`docs/2026-04-11-500-debug-mapping-report.md`

---

## 7. 给协作者的结论（一句话）

本次问题不是“映射算法本身坏掉”，而是先发生了事件循环阻塞导致 ingest 500；该问题已修复并验证链路可落盘。下一阶段重点是提高自然新闻触发率与映射质量度量自动化。
