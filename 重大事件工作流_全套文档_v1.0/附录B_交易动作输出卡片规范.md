# 附录B｜交易动作输出卡片规范 v1.0

- **文档类型**：专项规范 / 输出契约文件
- **文档状态**：正式版
- **版本**：v1.0
- **所属总纲**：重大事件工作流总纲与执行总规范 v1.0
- **作用**：定义重大事件工作流的最终交易动作输出格式、字段含义、动作等级、拦截与降级口径
- **适用对象**：下游输出模块、路径裁决模块、市场确认模块、联调与验收人员

---

## 一、文档目的

本规范用于回答一个最实际的问题：

> 当重大事件经过识别、验证、映射、路径收敛和市场确认后，系统最终要以什么格式把结果交给人或下游模块？

本规范的核心目标不是“写得好看”，而是：

- 让输出**像交易语言**
- 让不同模块对“最终动作”有统一口径
- 让人看完后知道“能不能做、做谁、怎么做、什么时候不做”

---

## 二、总原则

### 2.1 交易动作卡片不是摘要卡片
禁止把最终输出做成“解释型摘要”。
最终卡片必须回答：

- 能不能做
- 做谁
- 怎么做
- 仓位级别
- 风险开关
- 当前处于什么状态

### 2.2 交易动作卡片是主链成品
新闻、证据、路径、评分都只是中间层。
交易动作卡片才是主链对外的**成品层**。

### 2.3 不允许输出模糊结论
禁止出现以下模糊表达作为最终结论：

- 值得关注
- 可以留意
- 建议观察一下
- 有一定机会
- 或许会受益

最终必须压缩为可判定结论。

---

## 三、卡片固定结构

## 3.1 标准结构

交易动作卡片由以下 6 层组成：

1. 事件层
2. 主路径层
3. 市场确认层
4. 动作层
5. 风险层
6. 一句话结论层

---

## 四、字段定义

## 4.1 事件层字段

| 字段名 | 必填 | 说明 |
|---|---:|---|
| `event_name` | 是 | 事件名称，要求简洁、明确 |
| `event_type` | 是 | 事件类型，如 policy_shock / war / tariff / epidemic / financial_stress |
| `event_time` | 是 | 事件首发时间 |
| `time_window` | 是 | 当前所处时间窗口，如 0-24h / 24-48h / 48-72h / 72-120h / >120h |
| `evidence_grade` | 是 | 证据等级，A / B / B- / C |
| `catalyst_state` | 是 | 催化状态，First Impulse / Continuation / Exhaustion / Dead |

### 4.2 主路径层字段

| 字段名 | 必填 | 说明 |
|---|---:|---|
| `primary_path` | 是 | 当前唯一主路径，必须为最短、最硬、最可交易路径 |
| `secondary_paths` | 否 | 次级备选路径，可为空 |
| `rejected_paths` | 否 | 被放弃路径，可为空，用于说明为何未入主池 |
| `target_bucket` | 是 | 优先交易对象类型：ETF / Sector / Leader / Follower |

### 4.3 市场确认层字段

| 字段名 | 必填 | 说明 |
|---|---:|---|
| `macro_state` | 是 | 宏观环境：risk-on / mixed / risk-off |
| `sector_confirmation` | 是 | 板块承接：strong / medium / weak / none |
| `leader_confirmation` | 是 | 龙头确认：confirmed / partial / unconfirmed / failed |
| `a1_market_validation` | 是 | A1 市场验证结论：pass / partial / fail |

### 4.4 动作层字段

| 字段名 | 必填 | 说明 |
|---|---:|---|
| `trade_grade` | 是 | 动作评级：A / B / C / D |
| `trade_decision` | 是 | 交易结论：tradable / observe_only / intraday_only / overnight_allowed / avoid |
| `best_target` | 是 | 最优对象，可为 ETF、板块龙头或单一个股 |
| `best_setup` | 是 | 最优打法：buy_dip / breakout / pullback_confirm / no_chase / avoid |
| `position_tier` | 是 | 仓位级别：test / light / medium / none |
| `execution_window` | 是 | 执行窗口：open / intraday / close_near / next_day_watch |

### 4.5 风险层字段

| 字段名 | 必填 | 说明 |
|---|---:|---|
| `risk_switches` | 是 | 风险开关列表，触发后必须降级或退出 |
| `invalidators` | 是 | 失效条件列表 |
| `downgrade_rules` | 是 | 从更高等级自动降级的规则 |
| `blockers` | 否 | 阻断交易的硬性条件 |

### 4.6 一句话结论层字段

| 字段名 | 必填 | 说明 |
|---|---:|---|
| `one_line_verdict` | 是 | 一句话最终裁决，必须能直接读懂 |

---

## 五、动作等级定义

## 5.1 A 级
- 可做，且具备较强延续预期
- 可进入中等仓位层
- 需同时满足：主路径清晰、市场确认强、龙头确认明确、风险开关清楚

## 5.2 B 级
- 可做，但更适合轻仓或条件确认后做
- 可日内，也可选择性过夜
- 通常为主路径成立，但市场确认未达到最强一致

## 5.3 C 级
- 仅观察或仅日内博弈
- 不适合中仓，不适合无确认追价
- 典型场景：逻辑成立但承接弱、或事件处于衰竭边缘

## 5.4 D 级
- 回避
- 禁止包装成“有点机会”
- 只保留复盘价值，不进入主交易池

---

## 六、交易结论枚举定义

| 枚举值 | 含义 |
|---|---|
| `tradable` | 可交易 |
| `observe_only` | 仅观察，不执行 |
| `intraday_only` | 仅日内，不建议过夜 |
| `overnight_allowed` | 可考虑过夜 |
| `avoid` | 回避 |

---

## 七、最优打法枚举定义

| 枚举值 | 含义 |
|---|---|
| `buy_dip` | 回踩低吸 |
| `breakout` | 突破跟随 |
| `pullback_confirm` | 回踩确认后再入 |
| `no_chase` | 禁止追高 |
| `avoid` | 回避 |

---

## 八、仓位级别定义

| 枚举值 | 含义 |
|---|---|
| `test` | 试仓 |
| `light` | 轻仓 |
| `medium` | 中仓 |
| `none` | 不开仓 |

> 注：本系统当前不在主链中直接给出“重仓”建议。
> 若未来出现更高等级动作，应单独通过风控体系扩展，不在本附录默认开放。

---

## 九、生成规则

### 9.1 只有通过主路径收敛后，才能生成卡片
若主路径未收敛，不得提前输出“像卡片的卡片”。

### 9.2 只有通过市场确认后，才能升级为高优先级动作卡
若 A1 市场验证失败，卡片最高只能降级为 `observe_only` 或 `avoid`。

### 9.3 观察级也必须输出完整卡片
观察级不是不输出，而是要明确写清“为什么现在不做”。

---

## 十、拦截规则

以下情况禁止生成 `tradable` 或 `overnight_allowed`：

1. `evidence_grade` 为 C 且无二次确认
2. `catalyst_state` 为 Dead
3. 主路径仅为概念映射或弱二级路径
4. `a1_market_validation` = fail
5. 龙头确认 failed
6. 风险开关无法定义

---

## 十一、降级规则

以下情况应自动降级：

- 主路径成立，但板块承接从 strong 降至 weak
- 板块仍强，但龙头由 confirmed 降为 partial / unconfirmed
- 事件仍在有效窗口，但催化状态由 Continuation 转为 Exhaustion
- 风险开关之一被触发

自动降级顺序建议：

`A → B → C → D`

---

## 十二、标准输出模板（Markdown 展示）

```markdown
### 交易动作卡片

- 事件：{{event_name}}
- 类型：{{event_type}}
- 时间窗口：{{time_window}}
- 证据等级：{{evidence_grade}}
- 催化状态：{{catalyst_state}}

- 主路径：{{primary_path}}
- 次级路径：{{secondary_paths}}
- 放弃路径：{{rejected_paths}}

- 宏观环境：{{macro_state}}
- 板块承接：{{sector_confirmation}}
- 龙头确认：{{leader_confirmation}}
- A1 市场验证：{{a1_market_validation}}

- 评级：{{trade_grade}}
- 结论：{{trade_decision}}
- 最优对象：{{best_target}}
- 最优打法：{{best_setup}}
- 仓位：{{position_tier}}
- 执行窗口：{{execution_window}}

- 风险开关：{{risk_switches}}
- 失效条件：{{invalidators}}

> 一句话结论：{{one_line_verdict}}
```

---

## 十三、标准输出模板（JSON 契约）

```json
{
  "event_name": "",
  "event_type": "",
  "event_time": "",
  "time_window": "",
  "evidence_grade": "",
  "catalyst_state": "",
  "primary_path": "",
  "secondary_paths": [],
  "rejected_paths": [],
  "target_bucket": "",
  "macro_state": "",
  "sector_confirmation": "",
  "leader_confirmation": "",
  "a1_market_validation": "",
  "trade_grade": "",
  "trade_decision": "",
  "best_target": "",
  "best_setup": "",
  "position_tier": "",
  "execution_window": "",
  "risk_switches": [],
  "invalidators": [],
  "downgrade_rules": [],
  "blockers": [],
  "one_line_verdict": ""
}
```

---

## 十四、验收标准

一个合格的交易动作卡片必须同时满足：

1. 人看完后知道能不能做
2. 人看完后知道做谁
3. 人看完后知道怎么做
4. 人看完后知道什么情况下不做
5. 下游模块可直接消费 JSON 契约
6. 不依赖长篇解释才能理解

---

## 十五、最终原则

> 交易动作卡片不是解释层文案，而是重大事件工作流主链的最终执行表达。
> 它必须服务决策，而不是服务修辞。
