# LLM 新闻分析层设计与字段映射规范（完整版 v2.1）

## 一、 认知演进：从“工具”到“系统理解引擎”

本项目对 LLM 的应用已完成从“语义分析插件”到“受约束事件理解引擎”的质变。以下是我们达成共识的演进路径，作为 Member A/B/C 协同开发的认知底座。

### 1. 演进的五个阶段
*   **阶段 1：工具级（初识）** —— LLM = 关键词提取器（仅输出基础 4 标签）。
*   **阶段 2：权力误判（风险期）** —— 误认为 LLM 可直接裁决交易。风险：系统退化为不可审计的黑箱。
*   **阶段 3：边界校正（核心共识）** —— **LLM 负责理解新闻（A0/A-1），规则系统握有最终执行权。**
*   **阶段 4：能力瓶颈（架构阵痛）** —— 发现 4 字段无法支撑 A0-A4 主链逻辑，必须深度结构化。
*   **阶段 5：系统级重构（当前状态）** —— **LLM 作为受约束的理解模块嵌入系统**，提供三层结构（抽取、推理、治理）输出。

### 2. 四大本质升级
1.  **从“标签思维” → “事件对象思维”**：输出是一个能被系统直接消费的 Event Object。
2.  **从“模型输出” → “Contract 输出”**：严禁自然语言解释，输出必须强校验且符合 Schema。
3.  **从“AI 驱动” → “规则约束 AI”**：结论采用“AI 建议 + 规则裁决”，A0-A4 拥有绝对否决权。
4.  **从“单点分析” → “系统生命周期嵌入”**：LLM 深度参与 A0 生命周期、A2 传导、A1 软验证及 A2.5 副链路由。

---

## 二、 核心定位与原则

### 1. 总体定位
> **LLM 负责“理解世界”（理解语义与逻辑），规则系统负责“决定能不能做”（风控与执行）。**

### 2. 核心红线（必须遵守）
1️⃣ **NO A1 → NO TRADE**：LLM 只负责 A0（识别）和 A-1（预期差），A1（市场验证）必须由真实价格和成交量决定。
2️⃣ **禁止越权**：LLM 严禁输出任何直接的交易指令（Action）或仓位比例（Position Size）。
3️⃣ **辅助而不替代**：AI 是“第二意见”或“情报增强”，绝非替代原有的硬性风控闸门（Gates）。

---

## 三、 LLM 职责边界：分层结构

### Layer 1：抽取层 (Facts)
| 字段 | 说明 | 类型 |
|------|------------|------|
| `event_type` | 16 种预定义事件类型（如：policy_shock, monetary 等） | String (Enum) |
| `entities` | 板块、个股、国家、币种等实体清单 | List[Object] |
| `sentiment` | 极简情绪判定（Positive / Negative / Neutral） | Enum |

### Layer 2：推理层 (Inference - 核心升级)
| 字段 | 说明 | 价值 |
|------|------------|------|
| `a0_event_strength` | 事件强度评级（0-100） | 驱动 A0 优先级 |
| `expectation_gap` | 预期差（-100 到 100） | **核心 A-1 逻辑输入** |
| `narrative_vs_fact` | 叙事驱动 vs 事实驱动 (narrative/fact/mixed) | 驱动 L0.5 降权逻辑 |
| `transmission_path` | 因果传导链（A -> B -> C） | A2 板块传导参考 |
| `novelty_score` | 重大新颖性评分（0-100） | 触发 A3 预期差权重修正 |
| `event_scope` | 波及范围（Macro/Sector/Theme） | 确定 A2.5 整合广度 |
| `narrative_stage` | 叙事生命周期 (Initial/Developing/Peak/Fading) | **主题催化引擎的核心动力** |
| `evidence_spans` | 新闻原文证据片段 | 用于后期审计与置信度追溯 |

### Layer 3：治理层 (Governance & Replay)
- `model_path`: 使用的模型全路径/版本
- `prompt_version`: 提示词版本 ID
- `input_snapshot_id`: 全量输入数据的唯一快照
- `latency_ms`: AI 响应时长

---

## 四、 深度应用场景

### 1. A1 的“软验证”辅助（Soft AI Validation）
当价格（Price）与成交量（Volume）信号处于模糊区间（如 50-70 分）时，系统请求 AI 进行倾向性分析。
*   **规则**：AI 的辅助分（0.3 权重）不能改变 A1 的否定结论，仅用于在“可做可不做”时的概率增强。

### 2. AI 风险守门员（Risk Guardian）
在 `RiskGatekeeper` 完成所有硬规则检查后，最后一步由 AI 进行语义层面的黑天鹅扫描。
*   **用途**：捕捉规则集外（Out-of-set）的特殊风险，如特定地缘政治新闻中的“隐含负面溢出”。

### 3. 叙事全生命周期追踪
结合主题催化引擎，由 AI 判定当前新闻是属于叙事的“高潮（Peak）”还是“末端（Fading）”。
*   **红线**：若判定为 `Fading`，即便评分再高，副链也必须强制启动退场保护模式。

---

## 五、 工程化约束

### 1. 成本与配额管理 (`AIBudgetManager`)
*   所有 AI 调用必须经过预算管理器。
*   当当日预算归零或延迟过高时，系统必须无缝降级（Fallback）到基于关键词和分类映射的原始规则。

### 2. 生产级 Prompt 规范
*   **严格 JSON 输出**：严禁输出任何 Markdown 标记或自然语言干扰。
*   **英文 Prompt**：为了确保推理的一致性和对齐（Alignment），强制使用英文 Prompt。
*   **Risk Flags 机制**：如果 AI 对新闻不确定，必须在 `risk_flags` 字段中返回（如 `missing_data`, `low_source_trust`），系统据此调低置信度。

---

## 六、 标准输出 Schema 示例

```json
{
  "event_type": "monetary_policy",
  "a0_event_strength": 85,
  "expectation_gap": -45,
  "narrative_vs_fact": "fact",
  "entities": [
    {"name": "Federal Reserve", "ticker": "FED", "type": "org"}
  ],
  "transmission_path": ["Rates Up", "USD Strong", "Growth Down"],
  "narrative_stage": "Developing",
  "novelty_score": 0.6,
  "confidence": 92,
  "risk_flags": [],
  "evidence_spans": ["Federal Reserve raises benchmark rate by 50 basis points"],
  "llm_meta": {
    "model": "glm-4-plus",
    "prompt_version": "v3.0_prod",
    "input_snapshot_id": "SN-0417-001"
  }
}
```

---

## 七、 最终演进路线图

1.  **Phase 1**: 替换 `AISignalAdapter` 的 4 字段逻辑，升级为 Layer 1/2 抽取。
2.  **Phase 2**: 在 `WorkflowRunner` 中集成 A1 辅助验证 (AI Soft Assist)。
3.  **Phase 3**: 上线 `RiskGuardian` 模块，完成 AI 对整体 Setup 的最后审核。
4.  **Phase 4**: 联动主题催化引擎，实现基于 AI 认知的完整叙事轮动决策。

---
**文档状态**: v2.1 ( Member A/B/C 生产执行准则 )  
**更新日期**: 2026-04-17  
**核心理念**: **AI 用来解释复杂世界，代码用来管理绝对风险。**
