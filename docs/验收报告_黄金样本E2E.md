# 事件驱动交易系统 — 黄金样本 E2E 验收报告

> **版本**: baseline_v1.1 (18 cases)  
> **生成时间**: 2026-04-15T08:18:34Z  
> **报告路径**: `logs/acceptance/latest_acceptance_report.json`  
> **Baseline 路径**: `tests/acceptance/baseline_v1.1_18cases.json`

---

## 一、验收结论

| 维度 | 结果 |
|---|---|
| 总用例数 | 18 |
| 通过数 | **18** |
| 失败数 | **0** |
| 阈值达标 | **PASS** |
| Layer 0 资格检查 | **PASS** |

**结论：18/18 黄金样本全部通过，全链贯通且无退化。**

---

## 二、样本分布

| 分类 | 用例数 | 通过率 | 用例 ID |
|---|---|---|---|
| **宏观 (macro)** | 5 | 100% | `rate_cut_001`, `rate_hike_001`, `cpi_hot_001`, `tight_mixed_regime_001`, `weak_narrative_strong_asset_001` |
| **政策 (policy)** | 3 | 100% | `tariff_escalation_001`, `qe_signal_001`, `bullish_with_risk_gate_001` |
| **财报 (earnings)** | 3 | 100% | `earnings_beat_nvda_001`, `earnings_miss_bank_001`, `sector_mismatch_001` |
| **地缘 (geopolitics)** | 3 | 100% | `oil_spike_001`, `strait_shipping_001`, `low_trust_high_impact_001` |
| **低信任 (low_trust)** | 4 | 100% | `rumor_low_rank_001`, `weak_news_001`, `incomplete_news_001`, `pseudo_official_001` |

---

## 三、Case 矩阵

| CASE_ID | CHAIN_OK | FIELDS_OK | PATH_OK | SIGNAL_OK | RISK_OK | MIXED_OK | FINAL |
|---|---|---|---|---|---|---|---|
| macro_rate_cut_001 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| macro_rate_hike_001 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| macro_cpi_hot_001 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| macro_tight_mixed_regime_001 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| macro_weak_narrative_strong_asset_001 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| policy_tariff_escalation_001 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| policy_qe_signal_001 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| policy_bullish_with_risk_gate_001 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| earnings_beat_nvda_001 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| earnings_miss_bank_001 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| earnings_sector_mismatch_001 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| geopolitics_oil_spike_001 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| geopolitics_strait_shipping_001 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| geopolitics_low_trust_high_impact_001 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| low_trust_rumor_low_rank_001 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| low_trust_weak_news_001 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| low_trust_incomplete_news_001 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| low_trust_pseudo_official_001 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |

---

## 四、核心指标

| 指标 | 实际值 | 阈值 | 状态 |
|---|---|---|---|
| 链路完整率 | **1.0000** | >= 0.95 | PASS |
| 必要字段缺失率 | **0.0000** | <= 0.01 | PASS |
| 方向一致率 | **1.0000** | >= 0.80 | PASS |
| 路径一致率 | **1.0000** | >= 0.75 | PASS |
| 高风险误放行率 | **0.0000** | <= 0.05 | PASS |
| 回归退化 | **0 新增失败** | 不允许恶化 | PASS |

---

## 五、验收层级说明

### Layer 0 — 运行资格

调用 `scripts/system_healthcheck.py --mode dev`，确认：
- 环境依赖正常（pytest, yaml, requests）
- 配置文件可加载
- 链路指向正确实现模块
- 回归测试引用一致

### Layer 1 — 全链贯通

贯通路径：`SourceRanker → PathRouter → PathAdjudicator → OpportunityScorer`

每个 case 断言以下字段完整存在：
`source_rank`, `dominant_path`, `mixed_regime`, `opportunities`, `state_machine_step`, `gate_reason_code`

### Layer 2 — 规则准确性

**五类断言**（无主观判断）：

| 断言类型 | 含义 | 示例 |
|---|---|---|
| **字段完整性** | 链路未断裂 | 所有 required_fields 存在 |
| **方向边界** | 不违背因果逻辑 | 降息不允许 SHORT |
| **路径类型** | 中游逻辑合理 | 商品冲击必须有 asset_pricing |
| **风险上限** | 不度激进 | 低 source_rank 不允许 EXECUTE |
| **Mixed Regime** | 路径差距小时强制保守 | 两条 path 差距<12 时必须触发 mixed_regime |

---

## 六、典型 case 行为

### 宏观：降息 (`macro_rate_cut_001`)
- source_rank: A（联邦储备官网）
- dominant_path: `rates_liquidity` (fundamental, 82.0)
- signal: LONG ✓
- final_action: EXECUTE ✓
- mixed_regime: true（利率与资产定价路径 gap < 12）

### 宏观：紧缩混合 regime (`macro_tight_mixed_regime_001`)
- **刁钻样本**：两条路径差距仅 1.0（73.0 vs 72.0）
- dominant_path: `policy_uncertainty_fundamental` (fundamental, 73.0)
- mixed_regime: **true** ✓（must_have_mixed_regime 断言）
- signal: WATCH ✓（混合 regime 强制保守）
- final_action: WATCH ✓

### 宏观：弱叙事强资产 (`macro_weak_narrative_strong_asset_001`)
- **刁钻样本**：narrative=52.0, asset_pricing=86.0
- dominant_path: `yield_curve_strong_signal` (asset_pricing, 86.0) ✓
- signal: SHORT ✓
- final_action: EXECUTE ✓

### 政策：利多 + 风险门禁 (`policy_bullish_with_risk_gate_001`)
- **刁钻样本**：sector 方向 LONG 但 risk_blocked=true
- dominant_path: `fiscal_spending_fundamental` (fundamental, 80.0)
- signal: LONG ✓
- final_action: **WATCH** ✓（risk_blocked 强制保守）

### 地缘：航运中断 (`geopolitics_strait_shipping_001`)
- dominant_path: `freight_repricing` (asset_pricing, 76.0)
- signal: SHORT ✓
- final_action: **WATCH** ✓（风险上限断言：场景保守，不允许直接 EXECUTE）
- risk_flags: market_cap + price_data ✓

### 地缘：低信任高影响 (`geopolitics_low_trust_high_impact_001`)
- **刁钻样本**：source_rank=C 但事件影响大
- source_rank: C（social 源）
- dominant_path: `energy_disruption_repricing` (asset_pricing, 78.0)
- signal: LONG ✓
- final_action: **WATCH** ✓（低信任源强制保守）

### 财报：板块不匹配 (`earnings_sector_mismatch_001`)
- **刁钻样本**：公司 LONG 但板块方向 SHORT
- dominant_path: `mixed_earnings_fundamental` (fundamental, 75.0)
- signal: WATCH ✓（方向冲突）
- final_action: WATCH ✓

### 低信任：伪官方 (`low_trust_pseudo_official_001`)
- **刁钻样本**：source_url 是 fed.gov 但内容空洞
- source_rank: A（official 源）但内容弱
- dominant_path: `conference_narrative` → narrative guard 生效 → `weak_asset` (asset_pricing, 46.0)
- signal: WATCH ✓
- final_action: WATCH ✓

### 低信任：谣言 (`low_trust_rumor_low_rank_001`)
- source_rank: C（social 源）
- dominant_path: `weak_asset` (asset_pricing, 43.0)
- signal: WATCH ✓（forbidden: LONG, SHORT）
- final_action: WATCH ✓

---

## 七、Github 对比分析（补充）

> 本节于 2026-04-15 新增，说明新增验收包与 GitHub 主分支的对比分析。

### 与主分支（origin/main）对比

| 对比项 | 结果 |
|--------|------|
| configs/ | **无变化** |
| scripts/ | 仅格式化调整（ai_semantic_analyzer.py 代码风格） |
| transmission_engine/core/ | **无变化** |

### 本地新增文件（Untracked）

| 目录 | GitHub 是否存在 | 说明 |
|---|---|---|
| `tests/acceptance/` | ❌ 不存在 | 新增验收用例目录 |
| `tests/golden_cases/` | ❌ 不存在 | 新增黄金样本目录 |
| `tests/scripts/` | ❌ 不存在 | 新增验收脚本目录 |
| `logs/acceptance/` | ❌ 不存在 | 新增验收日志输出 |

### 新增文件清单

```
tests/acceptance/
├── baseline_v1.0_12cases.json    # 初始 baseline
├── baseline_v1.1_18cases.json    # 当前 baseline
├── case_schema.json              # case 结构约束
└── scoring_thresholds.yaml       # 6 项指标阈值

tests/golden_cases/               # 18 个黄金样本（5 类）
├── macro/        (5 cases)
├── policy/       (3 cases)
├── earnings/     (3 cases)
├── geopolitics/  (3 cases)
└── low_trust/    (4 cases)

tests/scripts/                   # 验收执行脚本
├── run_golden_e2e_acceptance.py      # 主脚本：加载样本→执行全链→断言验证→输出报告
├── compare_acceptance_baseline.py    # 回归比对：当前结果 vs baseline，检测退化
└── summarize_acceptance_results.py   # 快速摘要：提取关键指标，输出简洁报告

logs/acceptance/                 # 输出产物
├── latest_acceptance_report.json # 详细 JSON 报告
└── latest_acceptance_report.md   # 人类可读 Markdown 报告
```

### 验收结论

- **是否越界**：否
- **修改类型**：纯增量（验收包层）
- **覆盖范围**：仅在 acceptance/golden_cases/scripts 目录添加测试数据和脚本，未触及核心模块边界
- **GitHub 原始测试**：tests/ 下原有 test_*.py 文件未被修改

---

## 八、Baseline 版本化

| 版本 | 用例数 | 日期 | 说明 |
|---|---|---|---|
| v1.0 | 12 | 2026-04-15 | 初始 baseline，覆盖 5 类基础场景 |
| v1.1 | 18 | 2026-04-15 | 新增 6 个刁钻样本（冲突/mixed_regime/伪高质/低信任高影响/板块不匹配） |

**升级记录**：
- v1.0 → v1.1：新增 6 个"更容易把系统打穿"的样本

---

## 九、Baseline 与回归保护

首次运行结果已固化为 `tests/acceptance/baseline_v1.0_12cases.json`。

当前使用 baseline：`tests/acceptance/baseline_v1.1_18cases.json`。

后续任何改动（48a/48b、scorer、path_adjudicator、health_gate）均需执行：

```bash
# 1. 跑验收
python tests/scripts/run_golden_e2e_acceptance.py

# 2. 与 baseline 比对
python tests/scripts/compare_acceptance_baseline.py \
  --current logs/acceptance/latest_acceptance_report.json \
  --baseline tests/acceptance/baseline_v1.1_18cases.json

# 3. 快速摘要
python tests/scripts/summarize_acceptance_results.py
```

**合并规则**：
- 新增失败 case → 禁止合并
- 当前未达阈值 → 禁止合并
- 回归退化（与 baseline 比恶化）→ 禁止合并

---

## 十、文件清单

```
tests/
├── acceptance/
│   ├── baseline_v1.0_12cases.json    # 初始 baseline
│   ├── baseline_v1.1_18cases.json    # 当前 baseline（刁钻样本）
│   ├── case_schema.json              # case 结构约束
│   ├── expected_field_contract.yaml  # 字段契约
│   └── scoring_thresholds.yaml       # 6 项指标阈值
├── golden_cases/
│   ├── macro/
│   │   ├── rate_cut_001.json
│   │   ├── rate_hike_001.json
│   │   ├── cpi_hot_001.json
│   │   ├── tight_mixed_regime_001.json          # 刁钻：mixed_regime
│   │   └── weak_narrative_strong_asset_001.json # 刁钻：叙事弱资产强
│   ├── policy/
│   │   ├── tariff_escalation_001.json
│   │   ├── qe_signal_001.json
│   │   └── bullish_with_risk_gate_001.json      # 刁钻：利多 + 风险门禁
│   ├── earnings/
│   │   ├── earnings_beat_nvda_001.json
│   │   ├── earnings_miss_bank_001.json
│   │   └── sector_mismatch_001.json             # 刁钻：板块不匹配
│   ├── geopolitics/
│   │   ├── oil_spike_001.json
│   │   ├── strait_shipping_001.json
│   │   └── low_trust_high_impact_001.json       # 刁钻：低信任高影响
│   └── low_trust/
│       ├── rumor_low_rank_001.json
│       ├── weak_news_001.json
│       ├── incomplete_news_001.json
│       └── pseudo_official_001.json             # 刁钻：伪官方源
└── scripts/
    ├── run_golden_e2e_acceptance.py      # 主脚本
    ├── compare_acceptance_baseline.py    # baseline 回归比对
    └── summarize_acceptance_results.py   # 快速摘要

logs/acceptance/
├── latest_acceptance_report.json         # JSON 报告
└── latest_acceptance_report.md           # Markdown 报告
```

---

## 十一、验收架构设计原则

1. **固定输入** — 每个 case 是输入 + 预期断言，不依赖实时外部数据
2. **五类断言** — 字段完整 / 方向边界 / 路径类型 / 风险上限 / mixed_regime，不含主观判断
3. **baseline 固化** — 第一次跑通后固化，后续只检查是否退化
4. **分层验收** — Layer0 先确认能跑，Layer1 检查链路，Layer2 检查规则
5. **先 12 个再扩展** — 先覆盖最具代表性的样本，后续按需增加难度
6. **刁钻样本优先** — 优先补充容易把系统打穿的场景

---

## 十二、下一步计划

### 已覆盖的刁钻场景
- [x] 冲突样本：利多 headline + 风险门禁 (`bullish_with_risk_gate_001`)
- [x] 混合 regime：两条 path 非常接近 (`tight_mixed_regime_001`)
- [x] 伪高质量样本：source 看起来不错，但内容很弱 (`pseudo_official_001`)
- [x] 低信任但高影响 (`low_trust_high_impact_001`)
- [x] 财报 + 板块不匹配 (`sector_mismatch_001`)
- [x] 弱叙事强资产 (`weak_narrative_strong_asset_001`)

### 待补充场景（下一阶段）
- [ ] 多事件冲突：同一 sector 同时存在利多和利空事件
- [ ] fatigue 场景：叙事疲劳后的保守输出
- [ ] 价格缺失时的降级处理
- [ ] 极端 mixed_regime：三条 path 差距均<12

---

*本报告由 `run_golden_e2e_acceptance.py` 自动生成，原始数据见 `logs/acceptance/latest_acceptance_report.json`。*
