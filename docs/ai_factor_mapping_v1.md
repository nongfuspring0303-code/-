# AI因子映射冻结文档 v1

## 目的

冻结 A 输出到 B 因子的映射口径，保证并行开发期间不漂移。

## 映射关系（v1）

- `evidence_score` -> `A0`
- `consistency_score` -> `A-1`
- `freshness_score` -> `A1`
- `confidence` -> `A1.5`
- `counter_signal_penalty` -> `A0.5`

## 版本字段

- `mapping_version`: `factor_map_v1`
- `schema_version`: `ai_factor_map_v1`

## 变更规则

1. 映射关系变更必须升级 `mapping_version`。
2. 变更必须同次更新：schema + tests/mocks + module-registry + 任务清单。
3. 运行时映射从 `configs/edt-modules-config.yaml` 的 `modules.AISignalAdapter.params.mapping_versions` 读取。
4. 若请求版本不存在，且 `allow_version_rollback=true`，自动回退到 `active_mapping_version`。
