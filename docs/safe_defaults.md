# AI 安全降级因子说明（B1.1）

## 目标

当 AI 超时或失败时，系统必须进入可复现、可审计的保守模式，且不能绕过硬风控。

## 配置位置

- `configs/edt-modules-config.yaml`
- `modules.RiskGatekeeper.params.ai_safe_defaults`

## 默认策略

1. `on_ai_timeout`
- action: `WATCH`
- factors:
  - `A0=0`
  - `A-1=0`
  - `A1=0`
  - `A1.5=0`
  - `A0.5=100`

2. `on_ai_error`
- action: `BLOCK`
- factors:
  - `A0=0`
  - `A-1=0`
  - `A1=0`
  - `A1.5=0`
  - `A0.5=100`

## 执行约束

1. 降级触发后，`RiskGatekeeper` 的 G7 会输出明确拒绝原因。
2. 决策输出必须包含 `decision_summary`，记录 `mapping_version`、`model_version`、`prompt_version`。
3. 任意场景下，硬风控（G1~G3）优先级高于 AI 建议。
