# 新闻->板块->个股映射研究基线（2026-04-11）

## 数据来源
- `logs/event_bus_live.jsonl`
- 采样时间：2026-04-11 本地运行记录

## 基线统计（历史记录）
- 消息总数：252（`event_update`）
- 事件轨迹数（按 `trace_id` 去重）：149
- 来源分布：`sina=246`, `rss=5`, `atom=1`
- 严重度分布：`E1=252`
- AI 判定分布（有值样本）：`abstain=99`

## 链路覆盖结果
- `event -> sector` 覆盖：0 / 149 = 0.00%
- `event -> opportunity` 覆盖：0 / 149 = 0.00%
- `event -> sector -> opportunity` 覆盖：0 / 149 = 0.00%

结论：当前日志中仅看到事件层（`event_update`），没有看到 `sector_update` 与 `opportunity_update` 的落盘证据，无法基于现有记录计算“新闻->板块->个股”映射质量指标。

## 新采样尝试（自动执行）
- 已重启本地栈并进行额外采样（约 2 个轮询周期）
- 新增消息：2（均为 `event_update`）
- 新增事件轨迹：1
- 期间出现 API 写入失败日志：`POST /api/ingest/event-update` 返回 500（启动阶段）

## 当前阻塞点
1. 下游消息缺失：`sector_update` / `opportunity_update` 未进入 event bus live 日志。
2. 启动阶段存在写入 500，可能导致事件预览/传导链路丢失。

## 下一步建议（自动化方向）
1. 先修复 `event-update` 500 问题（保证事件稳定入总线）。
2. 在相同采样窗口强制产出 `sector_update` / `opportunity_update`（可临时降低阈值或开启调试开关）。
3. 再跑映射指标自动计算（sector recall/precision, direction accuracy, symbol hit rate）。
