# 阶段 3B：sector / ticker 真源冻结稿（B 主责）
**版本**：v1.0  
**日期**：2026-04-23  
**角色**：B 主责，A 联审契约触点，C 仅在日志/观测受影响时联审  
**阶段**：阶段 3B（sector / ticker / 伪兜底修复）

## 1. 冻结目的

本文件先把 3B 的两个唯一真源写死，再允许后续施工：

- `sectors[]` 最终白名单的唯一真源
- `ticker_pool` 的唯一真源

任何 alias / mapping / template 辅助文件，只能做映射辅助，不能扩展最终白名单或 ticker 真源。

## 2. `sectors[]` 唯一真源

### 2.1 唯一真源文件

- `configs/sector_impact_mapping.yaml`

### 2.2 冻结口径

1. `sectors[]` 最终输出只能来自白名单。
2. 白名单只能由 `configs/sector_impact_mapping.yaml` 的 canonical sector 口径冻结。
3. `configs/sector_aliases.yaml` 只能做别名归一化，不能新增白名单项。
4. `configs/premium_stock_pool.yaml` 只能作为 ticker 侧候选和回归样本来源，不能反向扩展 `sectors[]` 白名单。
5. `configs/conduction_chain.yaml`、`configs/factor_templates.yaml`、`scripts/verify_mapping_quality.py` 等文件只负责映射/模板/验收辅助，不能把未授权 sector 注入最终白名单。

### 2.3 明确边界

- 允许：`sector_aliases.yaml` 将别名归一到 canonical sector。
- 允许：`sector_impact_mapping.yaml` 负责 canonical sector 的唯一口径。
- 禁止：任何 fallback/default/unknown 通过辅助文件“顺手长出”新 sector。
- 禁止：把 `premium_stock_pool.yaml` 里的现有 stock sector 当作白名单扩容依据。

## 3. `ticker_pool` 唯一真源

### 3.1 唯一真源文件

- `configs/premium_stock_pool.yaml`

### 3.2 冻结口径

1. `ticker_pool` 只能来自 `configs/premium_stock_pool.yaml`。
2. `ticker_pool` 不允许由运行时 fallback、template collapse、sector 空集补全、或者语义猜测自动扩展。
3. `configs/sector_aliases.yaml`、`configs/sector_impact_mapping.yaml` 只能帮助 sector 归一和映射，不得反向创建 ticker。
4. `ticker_pool` 允许做过滤、排序、去重、阈值裁剪，但不允许把无依据 ticker 伪装成正式候选。

### 3.3 明确边界

- 允许：从 `premium_stock_pool.yaml` 读取静态 ticker 池。
- 允许：用 alias / mapping 辅助 sector-to-ticker 定位。
- 禁止：`fallback -> 金融 -> JPM` 这类伪兜底。
- 禁止：`unknown -> 任意 ticker`。
- 禁止：`None`、`N/A`、空字符串、占位符进入正式 ticker_pool。

## 4. 辅助文件的角色

以下文件仅能辅助，不得扩展最终真源：

- `configs/sector_aliases.yaml`
- `configs/sector_impact_mapping.yaml`
- `configs/conduction_chain.yaml`
- `configs/factor_templates.yaml`
- `scripts/verify_sector_coverage.py`
- `scripts/verify_mapping_quality.py`

它们可以做：

- 别名归一
- 模板命中
- 覆盖率验证
- 质量验收

它们不可以做：

- 扩白名单
- 扩 ticker 真源
- 伪造正式结果
- 把 fallback 包装成主路径

当前辅助配置已覆盖 `新能源`、`材料`、`原材料`、`房地产`、`通信服务` 等常见池内标签的归一化，但这些仍然只是归一化层，不是新增真源。

## 5. 3B 施工原则

1. 先冻结真源，再改逻辑。
2. 真源只允许单点定义。
3. 辅助文件只做映射，不做扩容。
4. 任何 fallback / template collapse 必须能被验收脚本识别为非正式路径。
5. B 侧最终输出里，sector / ticker 必须可追溯到上述两个真源文件。
