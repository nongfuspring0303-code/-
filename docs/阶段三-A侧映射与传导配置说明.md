# 阶段三 A 侧：映射与传导配置说明

## 目的
本说明用于约束 **A侧事件→板块映射** 与 **宏观传导链** 的配置口径，确保
- 结构稳定（类别主线）
- 便于维护（可配置扩展）
- 可测试（有明确用例与门禁）

## 单一真源
当前版本以 `configs/edt-modules-config.yaml` 作为唯一真源：
- `modules.ConductionMapper.params.event_conduction`：事件类别到宏观/板块的传导映射
- `modules.ConductionMapper.params.time_scales`：时间尺度枚举

## 事件类别 → 宏观/板块传导
位置：
```
configs/edt-modules-config.yaml
modules.ConductionMapper.params.event_conduction
```

结构示例：
```yaml
C:
  macro: [inflation_up, growth_risk_up]
  sector: [export_down, domestic_up]
```

维护规则：
1. **类别主线稳定**：优先维护 A–G 事件类别，不随新闻关键词频繁变动。
2. **宏观先行，板块跟随**：macro 必填，sector 必填。
3. **新增类别**：必须同步更新测试与文档。

## Yahoo 板块数据接入
- DataAdapter 输出 `sector_data`（Yahoo Finance assetProfile）。
- ConductionMapper 在有 `sector_data` 时，优先将内部 sector tag 映射到实际板块名称。
- 映射表：`configs/sector_impact_mapping.yaml`

## 传导路径（chain）
传导链路以 `ConductionMapper` 输出的 `conduction_path` 为准，
原则上应反映：
```
事件 → 宏观因子 → 板块 → 主题/个股
```

如果需要新增“可视化链路词条”，应同步：
- 配置（或模块内部映射）
- 测试用例
- 说明文档

## 测试与门禁
- 用例：`tests/test_conduction_mapper.yaml`
- 配置完整性测试：`tests/test_conduction_mapping_config.py`

门禁：
```bash
python3 -m pytest -q
PYTHONPYCACHEPREFIX=/tmp/pycache python3 scripts/system_healthcheck.py
```

## 变更约束（四联动）
若新增/调整字段或输出含义，必须同步更新：
1. `schemas/*.json`
2. `tests/*`
3. `module-registry.yaml`
4. 文档（本说明或相关 README）
