# 阶段 3B：sector / ticker / 伪兜底修复验收标准（B 主责）
**版本**：v1.0  
**日期**：2026-04-23  
**角色**：B 主责，A 联审契约触点，C 仅在日志/观测受影响时联审  
**阶段**：阶段 3B（sector / ticker / 伪兜底修复）

## 1. 验收目标

本阶段验收只看 5 件事：

1. `sectors[]` 白名单闭环
2. `ticker_pool` 闭环
3. 金融 / JPM 伪兜底删除
4. placeholder 泄漏下降
5. template collapse 收敛

## 2. 验收方法

### 2.1 `sectors[]` 非白名单占比 = 0

- 以 `configs/sector_impact_mapping.yaml` 作为唯一真源白名单口径。
- 跑 `ConductionMapper` 和 sector 映射回归样本。
- 检查最终 `sector_impacts` / `sectors[]` 输出是否全部落在白名单内。
- 判定公式：
  - `non_whitelist_count / total_sector_outputs = 0`

### 2.2 `ticker_pool` 闭环

- 以 `configs/premium_stock_pool.yaml` 作为唯一真源池。
- 跑 `OpportunityScorer` 的正向和反向样本。
- 检查输出 ticker 是否都能在 pool 中查到。
- 检查无依据 sector / ticker 场景时是否返回 `WATCH` / 空结果，而不是伪造 ticker。

### 2.3 金融 / JPM 伪兜底删除

- 使用 `rate_cut` / `policy` 相关样本回放。
- 当 `sector_data` 为空或不足时，不能再把 fallback 伪装成 `Financial Services` / `JPM` 正式结果。
- 判定标准：
  - 不允许 `JPM` 作为默认兜底候选
  - 不允许 `SPY` 作为伪装出来的正式 ticker 结果
  - 不允许空 sector 被硬回退成金融主路径

### 2.4 placeholder 泄漏率 ≤ 1%

- 统计最终输出中的 placeholder 候选：
  - 空字符串
  - `None`
  - `N/A`
  - `NONE`
  - 其他模板占位值
- 判定公式：
  - `placeholder_leak_rate = placeholder_count / total_output_candidates <= 1%`

### 2.5 template collapse 收敛

- 对模板命中但缺少可靠 sector / ticker 信号的样本，不能把失败路径伪装成正式输出。
- 至少满足：
  - `needs_manual_review = True`
  - 不生成伪造金融/JPM 路径
  - 不生成占位 ticker

## 3. 通过条件

以下条件全部满足时，阶段 3B 才可进入 A 联审收口：

- `sectors[]` 非白名单占比 = 0
- `ticker_pool` 结果全部可追溯到真源池
- 金融 / JPM 伪兜底已删除
- placeholder 泄漏率 ≤ 1%
- template collapse 不再污染正式输出

