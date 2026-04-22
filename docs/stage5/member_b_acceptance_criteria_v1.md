# 阶段0门禁文件 04：B侧验收标准表（A 执行，B 审核）
**版本**：v1.0  
**日期**：2026-04-21  
**角色**：阶段0门禁文件（A 执行，B 审核）  
**阶段**：阶段 0（施工准备）  
**目的**：本文件属于阶段0门禁文件，由成员 A 为满足阶段0执行要求统一补齐；成员 B 负责 review / sign-off，不代表阶段0执行主责属于 B。文件内容用于把阶段 3B 及后续联调中的验收标准数字化，避免“明显改善”“基本达标”这类口径扯皮。

---

# 一、直接继承的总项目门槛

以下门槛已在正式冻结版中出现，B 侧直接继承执行：

1. `sectors_non_whitelist_rate = 0`
2. `placeholder_leak_rate <= 1%`
3. `financial_rate < 35%`

这些是 B 侧最低门槛，不达标则不得宣称阶段 3B 修复完成。

---

# 二、B 侧新增验收指标

## 2.1 sector-ticker 对齐率
### 指标
- `sector_ticker_alignment_rate`

### 目标
- 阶段 3B 结束时：**>= 95%**

### 判定
抽样及黄金样本回放中，ticker 与其 sector 候选必须一致；明显错配计失败。

---

## 2.2 金融误判率
### 指标
- `financial_false_positive_rate`

### 目标
- 相比基线显著下降
- 建议门槛：**<= 20%**
- 严格目标：**<= 15%**

### 说明
当前基线 `financial_rate` 极高，阶段 3B 的核心目标之一就是压掉“金融黑洞”。

---

## 2.3 `theme_tags` 非幽灵字段率
### 指标
- `theme_tags_not_ghost_rate`

### 目标
- **= 100%**

### 判定
凡输出或评分中使用 `theme_tags`，必须：
- 有明确字段定义
- 有消费路径
- 有解释作用

禁止：
- 仅存在文档描述
- 但不进入任何计算或解释链

---

## 2.4 A1 目标绑定率
### 指标
- `a1_target_tracking_binding_rate`

### 目标
- **>= 95%**

### 判定
A1 若给出正向高分或进入交易候选，必须能绑定：
- 具体 ticker
- 或 ETF/proxy

---

## 2.5 非可交易中性事件误放行率
### 指标
- `neutral_event_tradeable_leak_rate`

### 目标
- **= 0**

### 判定
天气、例行会晤、无明确资产映射依据的中性事件，不得进入 `EXECUTE`，也不应被硬映射成金融/JPM。

---

# 三、B 侧样本与测试要求

## 3.1 黄金样本
以下样本集必须覆盖：
1. AI / 半导体
2. 宏观 / 利率 / CPI
3. 商品 / 原油 / 黄金 / 天然气
4. 地缘
5. 天气 / 中性噪音
6. 历史金融黑洞错误样本
7. 消费 / 出口 / 补贴类样本

## 3.2 最低抽样门槛
- 小改动：30 条
- 中改动：50 条
- 涉及 sector 真源 / ticker_pool / 伪兜底 / A1 target_tracking：100 条

## 3.3 必过测试
1. `sector_ticker_alignment_test`
2. `financial_false_positive_regression_test`
3. `theme_tags_not_ghost_test`
4. `a1_target_tracking_binding_test`
5. `neutral_event_no_tradeable_test`

---

# 四、失败判定条件

满足以下任一项，成员 B 验收直接判定失败：

1. `sectors_non_whitelist_rate > 0`
2. `placeholder_leak_rate > 1%`
3. `financial_rate >= 35%`
4. `sector_ticker_alignment_rate < 95%`
5. `financial_false_positive_rate > 20%`
6. `theme_tags_not_ghost_rate < 100%`
7. `a1_target_tracking_binding_rate < 95%`
8. `neutral_event_tradeable_leak_rate > 0`

---

# 五、阶段 0 门禁结论

阶段 0 先冻结验收，不先宣称修复。  
后续阶段 3B 的所有代码与联调结果，都必须拿这份标准表做回归对比。

一句话：

**先把“怎么算修好”写死，再去修。**
