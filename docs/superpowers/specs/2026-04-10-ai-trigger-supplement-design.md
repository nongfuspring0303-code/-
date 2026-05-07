# AI 触发补盲设计（规则+语义）

## 目标

在不替换现有关键词快路径的前提下，补全已有 AI 分析环节：
- 规则命中继续直接触发（低延迟）
- 规则未命中时，增加 AI 语义判定补盲（提高触发率）
- 保留紧急回滚开关，默认全量开启

## 现状与缺口

当前 `EventCapture` 主要依赖关键词匹配（`scripts/intel_modules.py`），中文实时新闻（Sina）经常出现语义相关但词面不命中，导致：
- 前端可见新闻与“触发到交易链路”之间断层
- 触发率偏低，漏掉可交易事件

仓库里已有语义分析基础模块（`scripts/ai_semantic_analyzer.py`），但当前实现是规则占位逻辑，未接入在线 LLM 判定与触发仲裁。

## 方案对比

### 方案 A（推荐）：规则优先 + AI 补充触发
- 规则命中 => 直接触发
- 规则未命中 => 调用 AI 判定 `hit/miss`
- AI 只决定“是否触发”，暂不改严重度评分

优点：风险最小、上线快、便于量化增益。
缺点：严重度仍由原链路决定。

### 方案 B：AI 同时决定触发+严重度
- AI 返回触发与 severity/confidence
- 直接影响下游执行强度

优点：自动化更高。
缺点：误判代价高，回滚与治理复杂。

### 方案 C：仅影子评估
- AI 只打日志，不参与触发

优点：最安全。
缺点：无法立刻提升触发率。

采用：**方案 A**。

## 架构设计

```
EventCapture.execute()
  -> rules_fast_path (keywords)
      hit -> captured=true, capture_source=rules
      miss -> ai_supplement_path
                -> SemanticAnalyzer.analyze(...)
                -> if ai_hit and confidence>=threshold: captured=true, capture_source=ai
                -> else captured=false
```

仲裁原则：
1. `rules` 命中永远优先；
2. `ai` 仅补盲，不覆盖规则命中结果；
3. AI 异常/超时一律降级为规则结果（不中断主链路）。

## AI 输出契约

新增语义判定字段（在 `SemanticAnalyzer.analyze` 返回体中扩展）：
- `verdict`: `hit|miss|abstain`
- `confidence`: `0-100`
- `reason`: 简短原因（审计用）
- `provider`: `gemini_flash_lite|rule_fallback`
- `latency_ms`: AI 调用耗时
- `fallback_reason`: `semantic_disabled|timeout|provider_error|confidence_below_threshold`

`EventCapture` 输出新增：
- `capture_source`: `rules|ai|none`
- `ai_verdict`, `ai_confidence`, `ai_reason`

## 配置设计（默认全量 + 紧急回滚）

在 `runtime.semantic` 下扩展：

```yaml
runtime:
  semantic:
    enabled: true
    provider: gemini_flash_lite
    model: gemini-2.5-flash-lite
    min_confidence: 70
    timeout_ms: 1500
    full_enable: true
    emergency_disable: false
```

说明：
- 你确认“全量开启”，因此 `full_enable=true`。
- 保留紧急回滚：`emergency_disable=true` 时，AI 立即旁路。

## 与现有脚本借鉴点

来源：`<LOCAL_WORKSPACE>/脚本/6.新浪时事新闻分析gemini flash lite关键词版/新浪时事新闻分析gemini flash lite关键词版.py`

复用思路：
1. 保留关键词预筛，减少 AI 调用成本；
2. 使用 Gemini Flash Lite 作为实时语义补盲模型；
3. 采用结构化输出（sentiment/summary/impact/risk），先仅消费触发判定字段，其他字段进入审计日志。

## 失败处理

- AI 超时 / API 错误 / JSON 解析失败：
  - `captured` 仅依赖规则结果
  - 记录 `fallback_reason`
  - 不阻塞 realtime monitor

## 可观测性

新增指标（写入 health/审计）：
- `rule_hit_rate`
- `ai_supplement_invocations`
- `ai_supplement_hit_rate`
- `ai_trigger_gain`（AI 增量触发数）
- `ai_timeout_rate`
- `ai_fallback_rate`
- `ai_p95_latency_ms`

## 测试策略

1. 单测：
   - 规则命中时不调用 AI
   - 规则未命中 + AI hit 时触发成功
   - AI timeout/error 时降级到规则
2. 集成：
   - Sina 中文新闻样本（原先未命中）可触发
3. 回归：
   - 现有 `EventCapture` 行为不倒退

## 范围边界

本次只补全“触发判定”能力，不在本次修改：
- 严重度评分权重
- 交易执行风控阈值
- 前端交易建议文案策略

后续阶段再评估把 AI 输出接入 severity/confidence。
