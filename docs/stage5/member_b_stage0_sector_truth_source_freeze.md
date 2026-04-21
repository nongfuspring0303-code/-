# 成员 B 阶段0交付物 01：sector 真源冻结结果
**版本**：v1.0  
**日期**：2026-04-21  
**角色**：成员 B  
**阶段**：阶段 0（施工准备）  
**目的**：冻结 B 侧 sector 白名单唯一真源，避免后续阶段 3B 出现双真源、旧真源、镜像反客为主、验收口径不一致。

---

# 一、冻结结论

根据当前 PR72 头部内容与仓库现状，成员 B 对 sector 真源冻结结论如下：

## 1）唯一主定义真源
- **`configs/sector_impact_mapping.yaml`**

该文件在 PR72 对应分支上存在，并已承载：
- 事件关键词 → sector / direction / score / confidence 映射
- 内部 sector tag → canonical market sector 名称映射。fileciteturn21file0

## 2）消费侧辅助参考
- `configs/premium_stock_pool.yaml`

该文件当前承载了股票池与中文 sector 字段，可用于：
- 补充 whitelist 候选
- 补充 ticker_pool 初版
- 做 broad sector / ticker 对齐校验

但它**不是** sector 白名单主定义真源。fileciteturn22file0

## 3）镜像/引用文件状态
- `registry/sectors_white_list.yaml`：当前未在 PR72 头部路径中发现可读取实体文件（fetch 404）
- 结论：当前仓库并不存在一个可用的第二真源文件，后续若新增该文件，只允许作为镜像/引用文件，不得承载主定义

---

# 二、冻结规则（正式口径）

自阶段 0 冻结起，B 侧执行以下硬规则：

1. **唯一主定义真源：`configs/sector_impact_mapping.yaml`**
2. 任何 validator、fixture、验收脚本、映射测试，均以该文件为唯一判定基准
3. `configs/premium_stock_pool.yaml` 只用于：
   - ticker_pool 初版生成
   - sector/ticker 对齐检查
   - 不得反向覆盖 sector 主定义
4. 若后续新增 `registry/sectors_white_list.yaml`，其角色只能是：
   - 自动生成镜像
   - 文档引用副本
   - 不得新增独立 sector 定义
5. 若主定义真源与镜像/消费侧映射不一致，一律以 `configs/sector_impact_mapping.yaml` 为准，并记为配置一致性缺陷

---

# 三、当前发现的问题

## 1）canonical sector 命名存在中英混杂
`configs/sector_impact_mapping.yaml` 的 `mapping:` 段当前输出的是英文 canonical market sector：
- `Industrials`
- `Financial Services`
- `Energy`
- `Consumer Cyclical`
- `Technology`
- `Healthcare` 等。fileciteturn21file0

而 `configs/premium_stock_pool.yaml` 的 `stocks[].sector` 当前大量使用中文：
- 科技
- 金融
- 能源
- 医疗
- 工业
- 消费 等。fileciteturn22file0

这意味着：
- B 在阶段 3B 之前，必须补一层 **canonical sector normalization**
- 否则 sector 白名单与 ticker_pool 对齐会持续漂移

## 2）pool 中已有 sector 候选超出当前主定义映射覆盖面
`premium_stock_pool.yaml` 里存在：
- 新能源
- 公用事业
- 房地产
- 材料
- 通信服务 等中文 sector。fileciteturn22file0

但 `sector_impact_mapping.yaml` 的 `mapping:` 当前覆盖面仍偏窄。fileciteturn21file0

这说明：
- 阶段 0 先冻结真源是对的
- 阶段 3B 时必须扩 canonical sector 与 ticker_pool 的闭环覆盖

---

# 四、B 侧执行约束

1. 成员 B 后续提交中，凡涉及：
   - `semantic_event_type`
   - `sector_candidates`
   - `ticker_candidates`
   - `theme_tags`
   - `A1 target_tracking`
   必须以本冻结结果为依据，不再引入第二套 sector 白名单口径

2. 成员 B 后续若生成：
   - `ticker_pool.yaml`
   - `sector whitelist validator`
   - `mapping fixtures`
   必须显式声明：
   - 主定义来源：`configs/sector_impact_mapping.yaml`

3. 若 A/C 改动触及：
   - sector 枚举
   - canonical sector 字段
   - replay / scorecard 中的 sector 字段
   必须触发 Joint Review

---

# 五、下一步建议（属于阶段 3B，不在本冻结物内直接修改）

1. 建立 canonical sector 对照表（中英统一）
2. 从 `premium_stock_pool.yaml` 生成 B 侧 ticker_pool 初版
3. 给 `sector_candidates -> ticker_candidates` 增加 broad sector / sub-sector 双层一致性校验
4. 把 `Financial Services` 与 `金融` 映射统一，禁止任何 fallback 伪装成金融主路径

---

# 六、交付结论

成员 B 阶段 0 对 sector 真源的冻结交付如下：

- 真源已冻结
- 旧双真源未发现落地文件
- 镜像口径已限制
- 后续阶段 3B 可以在此基础上继续做：
  - whitelist 扩充
  - ticker_pool 闭环
  - 金融/JPM 伪兜底清理

