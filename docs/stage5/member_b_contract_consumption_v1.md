# 阶段0门禁文件 03：B侧消费口径冻结稿（A 执行，B 审核）
**版本**：v1.0  
**日期**：2026-04-21  
**角色**：阶段0门禁文件（A 执行，B 审核）  
**阶段**：阶段 0（施工准备）  
**目的**：本文件属于阶段0门禁文件，由成员 A 为满足阶段0执行要求统一补齐；成员 B 负责 review / sign-off，不代表阶段0执行主责属于 B。文件内容用于冻结 B 侧消费字段、判定逻辑与最小规则，确保阶段 3B 修复时不再临时改口径。

---

# 一、B 侧消费字段范围

成员 B 在后续阶段 3B 及映射验收中，明确消费以下字段：

1. `semantic_event_type`
2. `sector_candidates`
3. `ticker_candidates`
4. `theme_tags`
5. `A1 target_tracking`

以上字段若改名、改枚举、改结构，必须 Joint Review。

---

# 二、`semantic_event_type` 冻结口径

## 2.1 允许枚举（阶段 0 冻结版）
- `政策`
- `宏观`
- `商品`
- `AI`
- `军工`
- `科技`
- `公司事件`
- `天气`
- `地缘`
- `其他`

## 2.2 使用规则
1. 每条事件必须先归入一个主 `semantic_event_type`
2. 不允许直接跳过语义层去硬配 sector/ticker
3. 若无法可靠归类，则进入：
   - `其他`
   - 并优先 `NO_ACTION / WATCH`
4. 天气、例行会晤、泛政治表态、交通事故调查等，默认不应直接进入 tradeable

---

# 三、`sector_candidates` 冻结口径

## 3.1 生成规则
1. `sector_candidates` 必须来自唯一主定义真源：
   - `configs/sector_impact_mapping.yaml`
2. 不允许自由文本 sector
3. 不允许把叙事标签、评论语义、情绪词混入 sector 字段
4. 无法形成清晰 sector 映射时：
   - 允许空
   - 但不得硬回退为金融

## 3.2 当前规范
- broad sector 使用 B 侧规范枚举
- 后续阶段 3B 需要补 canonical sector normalization（中英统一）

## 3.3 明确禁止
- 禁止 `fallback -> 金融`
- 禁止 `unknown -> 金融`
- 禁止把 `theme_tags` 直接写进 `sector_candidates`

---

# 四、`ticker_candidates` 冻结口径

## 4.1 生成规则
1. `ticker_candidates` 只能来自：
   - `sector_candidates -> ticker_pool`
2. 不允许从全市场自由生成
3. broad sector / sub-sector 必须双层一致性校验
4. sector 池为空时：
   - 允许 `WATCH / NO_ACTION`
   - 不允许伪造 ticker

## 4.2 当前阶段 0 约束
- ticker_pool 可先用 `premium_stock_pool.yaml` 生成初版
- 但必须说明是 stage0 初版，不是最终完整交易池

## 4.3 明确禁止
- 禁止 `JPM(None)`、`NVDA(None)` 这类 placeholder 直出
- 禁止 sector 与 ticker 明显错配
- 禁止把 broad theme 当成 ticker 生成依据

---

# 五、`theme_tags` 冻结口径

## 5.1 角色定位
`theme_tags` 只作为：
- Narrative Boost
- 辅助叙事增强
- scorecard 解释字段

## 5.2 明确限制
1. `theme_tags` **不得单独触发 EXECUTE**
2. `theme_tags` 不得替代 `sector_candidates`
3. `theme_tags` 不得替代 `ticker_candidates`
4. `theme_tags` 不得在无目标资产绑定时抬高 A1 到可执行

---

# 六、`A1 target_tracking` 冻结口径

## 6.1 目标
A1 必须绑定具体目标资产或代理资产，禁止“泛市场高分”。

## 6.2 规则
1. 每条事件若进入 A1 路径，必须能解释：
   - 目标 ticker
   - 或目标 ETF / proxy
2. 若只有主题，没有可交易目标：
   - 允许 `WATCH`
   - 不允许 `EXECUTE`
3. 若只有 broad sector 没有 tradeable symbol：
   - 进入观察或阻断，不允许伪装已解析 symbol

---

# 七、B 侧最小判错规则

满足以下任一项，成员 B 在验收中判定为失败：

1. 非行业信息被硬映射为 sector
2. 非资产映射事件被硬映射为 ticker
3. fallback/default/unknown 被伪装成金融主路径
4. `theme_tags` 直接替代 sector/ticker
5. A1 无 target_tracking 仍高分可执行
6. sector 与 ticker 归属明显不一致
7. placeholder 泄漏到最终输出

---

# 八、门禁结论

阶段 0 的消费口径正式冻结为：

- 先语义，再 sector，再 ticker
- `theme_tags` 只辅助，不单独触发
- A1 必须绑定目标资产
- ticker 不允许自由生成
- fallback 不允许再伪装成金融/JPM

后续阶段 3B 的所有实现与验收，都以本口径稿为准。
