# 阶段三 B-1/B-2/B-3 实现说明

## 交付文件
- `configs/premium_stock_pool.yaml`
- `scripts/opportunity_score.py`
- `scripts/verify_direction_consistency.py`
- `schemas/opportunity_score_input.json`
- `schemas/opportunity_score_output.json`
- `tests/test_opportunity_score.py`

## B-1 优质股票池
- 通过 `filters` 配置统一约束：`ROE > 15`、`市值 > 500亿`、`流动性评分 > 0.6`。
- `OpportunityScorer` 仅对优质池通过股票生成机会卡，保证机会池不混入非优质标的。

## B-2 多空机会评分
- 评分输入：`impact_score`、`sector confidence`、`event_beta`。
- 输出方向：`LONG/SHORT/WATCH`。
- 验证脚本：`python3 scripts/verify_direction_consistency.py --samples 100 --min-rate 0.8`。

## B-3 机会卡字段补全
每条机会卡均输出以下字段：
- `symbol`
- `name`
- `sector`
- `signal`
- `entry_zone.support`
- `entry_zone.resistance`
- `risk_flags[]`
- `final_action`
- `reasoning`
- `confidence`
- `timestamp`

## 风控动作规则
- 风险旗标数量 `>=3`：`BLOCK`
- 存在高风险旗标：`PENDING_CONFIRM`
- 信号为 `WATCH`：`WATCH`
- 其余情况：`EXECUTE`
