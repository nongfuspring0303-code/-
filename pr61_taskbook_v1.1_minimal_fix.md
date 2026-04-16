# PR61 三人分工任务书（最小修错版 v1.1）

## 一、项目目标（唯一北极星）

将《主题板块催化持续性引擎 v1.0》的**8个治理文档**全部转化为**可阻断、可审计、可回滚的工程能力**，并**安全接入现有主链A0-A4体系**。

最终实现：**主链约束副链，副链增强主链的协同决策系统**。

---

## 二、冻结契约（唯一标准）

```yaml
contract_name: theme_catalyst_engine
contract_version: v1.0
producer_module: theme_engine

# 业务字段
event_id:
event_scope: sector_theme
primary_theme:
current_state: [FIRST_IMPULSE|CONTINUATION|EXHAUSTION|DEAD]
continuation_probability:
trade_grade: [A|B|C|D]
candidate_audit_pool:

# 输出信包字段（按主文档第9节输出信包约束）
contract_name:
contract_version:
producer_module:
safe_to_consume:
fallback_reason:
error_code:

# 主链融合字段
conflict_flag:
conflict_type: [C1_market_reject|C2_market_neutral|C3_market_favorable|unknown]
final_decision_source: [mainchain_only|mainchain_capped_theme|theme_only_degraded|theme_only]
macro_regime: [RISK_OFF|MIXED|RISK_ON]
theme_capped_by_macro: [true|false]
macro_override_reason:
final_trade_cap: [INTRADAY|1_TO_2_DAYS|STANDARD]
```

---

## 三、系统架构（最终形态）

```
事件输入 → A0(识别) → A1(验证) → A2(传导)
                             ↓
                        A2.5 Theme副链
                             ↓
                        路由裁决(macro > theme)
                             ↓
                        A3(适配) → 执行系统
```

**核心原则**：
- 主链决定风险天花板
- 副链决定主题排序与机会精细度
- 副链不得绕过主链直接触发执行

---

## 四、三人分工（强约束版）

### 👤 **A：Contract Owner（契约治理 + E2E验收主责）**

#### 核心职责
负责3个治理附件的工程落地：

**1. Consumer Contract Mapping Table**
- 实现字段映射表（按PR原文15个字段）：
  | 字段 | 来源模块 | 消费模块 | 可空 | 用途 | 缺失时默认行为 |
  |---|---|---|---|---|---|
  | primary_theme | theme_mapper | 盘前 / 个股 / 统一裁决 | 否 | 主题识别 | 拒绝高置信消费 |
  | current_state | continuation_engine | 盘中 / 过夜 / 统一裁决 | 否 | 状态判断 | 降级为观察 |
  | continuation_probability | continuation_engine | 盘前 / 盘中 | 是 | 延续概率 | 不参与排序 |
  | trade_grade | trade_adapter | 盘前 / 个股 / 统一裁决 | 否 | 交易评级 | 视为 D |
  | candidate_audit_pool | trade_adapter | 个股审计 | 是 | 审计优先池 | 空列表 |
  | conflict_flag | routing merge | 统一裁决 / 盘前 | 否 | 冲突判断 | 视为 true 并拦截 |
  | conflict_type | routing merge | 统一裁决 / 盘前 | 是 | 冲突分类 | 记录为 unknown_conflict |
  | final_decision_source | routing merge | 统一裁决 | 否 | 最终裁决来源 | 仅在主链明确命中时为 mainchain_only；否则视为 theme_only_degraded |
  | macro_regime | main chain | 统一裁决 / 盘前 | 否 | 宏观风险环境 | 仅在主链明确给出时使用；缺失时不得默认写入正常宏观状态 |
  | theme_capped_by_macro | routing merge | 统一裁决 | 否 | 是否触发主链封顶 | 默认 false；仅在宏观回避 / 冲突明确命中时置 true |
  | macro_override_reason | main chain | 统一裁决 | 是 | 主链覆盖原因 | 记录 unknown_override_reason |
  | final_trade_cap | routing merge | 统一裁决 / 执行前审查 | 否 | 评级/周期封顶结果 | 默认 INTRADAY |
  | fallback_reason | all modules | 全部消费端 | 是 | 降级解释 | 记录 unknown_fallback |
  | safe_to_consume | all modules | 全部消费端 | 否 | 安全消费开关 | 默认 false |
  | contract_name | output envelope | 全部消费端 | 否 | 契约识别 | 拒绝消费 |
  | contract_version | output envelope | 全部消费端 | 否 | 版本兼容判定 | 拒绝消费 |
  | producer_module | output envelope | 全部消费端 | 否 | 生产方追踪 | 拒绝消费 |
- 输出：`schemas/theme_contract_mapping.yaml`
- 覆盖PR原文15个字段

**2. Contract Versioning & Compatibility**
- 实现contract信封：`contract_name/version/producer_module`
- 版本规则：
  - 非破坏性变更：可直接进入次版本
  - 破坏性变更：必须至少保留一个兼容窗口
  - 推荐窗口：1个minor version
- 变更流程：提出变更 → 标注breaking/non-breaking → 更新主文档 → 更新schema → 更新mapping → E2E验收 → 合并
- 输出：`schemas/theme_contract_envelope.yaml`

**3. E2E Acceptance Checklist（主责）**
- 定义6类验收样本：
  - 正常链路 (E2E-01)
  - 映射失败 (E2E-02: THEME_MAPPING_FAILED)
  - basket为空 (E2E-03: BASKET_EMPTY)
  - 主副链冲突 (E2E-04: macro vs theme)
  - 主链缺失降级 (E2E-05: MAINCHAIN_MISSING)
  - replay一致性 (E2E-06)
- 输出：`tests/acceptance/theme_e2e_samples.yaml`

#### 主链接入任务
- 扩展主链输入schema，增加theme_output字段
- 定义主链消费规则文档：
  - safe_to_consume=false → 降级处理，标记DEGRADED模式
  - conflict_flag=true → 降级处理
  - theme_capped_by_macro=true → 禁止高评级

#### 禁止事项
- ❌ 不允许修改runner逻辑
- ❌ 不允许写业务代码
- ❌ 不允许修改healthcheck

#### 验收标准
- schema完整且通过校验
- registry正确指向
- E2E样本可执行
- 主链可识别theme字段

---

### 👤 **B：Gate Owner（门禁风控 + 幂等性）**

#### 核心职责
负责3个治理附件的工程落地：

**1. Error & Fallback Codebook**
- 实现错误码映射（按PR原文）：
  ```python
  # 标准输出字段（按Error & Fallback Codebook文档）
  {
    "status": "success|degraded|failed",
    "error_code": "...",
    "fallback_reason": "...",
    "degraded_mode": true|false,
    "safe_to_consume": true|false,
    "retryable": true|false,
    "missing_dependencies": []
  }

  # 错误码映射规则（按文档原文）
  CONFIG_MISSING:
    - status: "failed"
    - safe_to_consume: false
    - degraded_mode: true
    - fallback_reason: "CONFIG_MISSING"
  
  CONFIG_INVALID:
    - status: "failed"
    - safe_to_consume: false
    - fallback_reason: "CONFIG_INVALID"
    - 禁止输出高置信结论
  
  THEME_MAPPING_FAILED:
    - status: "failed"
    - safe_to_consume: false
    - trade_grade: "D"
    - fallback_reason: "THEME_MAPPING_FAILED"
  
  BASKET_EMPTY:
    - status: "degraded"
    - trade_grade: "C" 或 "D" (禁止A/B)
    - fallback_reason: "BASKET_EMPTY"
  
  MARKET_DATA_MISSING:
    - status: "degraded"
    - safe_to_consume: false
    - trade_grade: "C" (仅观察级)
    - fallback_reason: "MARKET_DATA_MISSING"
  
  VALIDATION_SKIPPED:
    - status: "failed"
    - safe_to_consume: false
    - 禁止continuation升级
    - fallback_reason: "VALIDATION_SKIPPED"
  
  STATE_ENGINE_INSUFFICIENT_DATA:
    - status: "degraded"
    - current_state: "FIRST_IMPULSE" 或 "DEAD"
    - fallback_reason: "STATE_ENGINE_INSUFFICIENT_DATA"
  
  DOWNSTREAM_OUTPUT_DEGRADED:
    - status: "degraded"
    - safe_to_consume: false
    - fallback_reason: "DOWNSTREAM_OUTPUT_DEGRADED"
  ```
- 输出：`configs/theme_error_codebook.yaml`

**2. Replay & Idempotency Policy**
- 实现幂等键（按PR原文）：
  ```python
  idempotency_key = event_id + config_version + evaluation_window
  ```
- 一致性校验：相同输入必须输出一致
- 输出：`scripts/verify_theme_replay.py`

**3. 健康检查增强**
- 扩展`system_healthcheck.py`：
  ```python
  def check_theme_contract(output):
      required = ["contract_name","contract_version","safe_to_consume"]
      if output["safe_to_consume"] == False:
          assert "fallback_reason" in output
  ```
- CI集成：阻止违规输出

#### 主链接入任务
- 防止副链绕过主链：
  ```python
  if safe_to_consume == False:
      final_action = "DEGRADED"
      prohibit_execute = True
  ```
- 冲突约束：
  ```python
  if conflict_flag:
      assert trade_grade not in ["A"]
  ```

#### 禁止事项
- ❌ 不允许修改schema定义
- ❌ 不允许改runner核心逻辑
- ❌ 不允许修改输出字段结构

#### 验收标准
- CI可拦截所有违规情况
- replay不一致可被检测
- fallback机制必须显式
- 健康检查覆盖所有异常路径

---

### 👤 **C：Runtime Owner（运行实现 + 主链融合）**

#### 核心职责
负责2个治理附件的工程落地：

**1. Chain Routing Policy**
- 实现路由裁决逻辑（按PR原文）：
  ```python
  # 冲突类型判定
  if macro_regime == "RISK_OFF":
      # C1: 宏观回避 vs 副链可做
      conflict_flag = True
      conflict_type = "C1_market_reject"
      final_trade_cap = "INTRADAY"
      GRADE_ORDER = {"A": 4, "B": 3, "C": 2, "D": 1}
      if GRADE_ORDER[trade_grade] > GRADE_ORDER["C"]:
          trade_grade = "C"
      theme_capped_by_macro = True
      macro_override_reason = "RISK_OFF 环境禁止高仓位"
      final_decision_source = "mainchain_capped_theme"
  
  elif macro_regime == "MIXED":
      # C2: 宏观中性 vs 副链强催化（修正版）
      conflict_flag = False
      conflict_type = "C2_market_neutral"
      theme_capped_by_macro = False
      final_decision_source = "theme_only"
  
  else:  # RISK_ON
      # C3: 宏观顺风 vs 副链弱催化
      conflict_flag = False
      conflict_type = "C3_market_favorable"
      theme_capped_by_macro = False
      final_decision_source = "theme_only"

  # 主链缺失时的回退
  if macro_regime is None:
      final_decision_source = "theme_only_degraded"
      fallback_reason = "MAINCHAIN_MISSING"
      safe_to_consume = False
      theme_capped_by_macro = True
  ```

**2. Observability & SLO Spec**
- 输出关键指标（按Observability & SLO Spec文档）：
  ```python
  {
    # 核心SLI指标（按文档原文）
    "theme_mapping_success_rate": ">= 95%",
    "degraded_output_rate": "<= 10%",
    "replay_consistency_rate": ">= 99%",
    "e2e_latency_ms": "由部署环境定义",
    "safe_to_consume_false_rate": "持续监控"
  }
  ```
- 日志标准化格式（按文档第6节监控要求）：
  ```python
  {
    "event_id": "...",
    "contract_version": "...",
    "config_version": "...",
    "route_result": "...",
    "mapping_result": "...",
    "validation_result": "...",
    "state_result": "...",
    "trade_grade": "...",
    "fallback_reason": "...",
    "safe_to_consume": "...",
    "e2e_latency_ms": "..."
  }
  ```
- SLO告警策略（按文档第5节）：
  - P1：核心契约不可消费
  - P2：质量显著退化
  - P3：可观测性异常

#### 主链接入任务
- 在workflow_runner中插入A2.5阶段
- 实现主副链决策融合（按PR61 Chain Routing Policy）：
  ```python
  # 核心三行逻辑：主链优先，副链调整，副链异常
  if macro_regime == "RISK_OFF":
      # 1. 主链优先：主链给上限，副链不能突破
      final_action = "BLOCK"
      final_decision_source = "mainchain_capped_theme"
      theme_capped_by_macro = True

  elif safe_to_consume:
      # 2. 副链调整：在上限内调整
      final_action = adjust(main_action, theme_signal)
      
  else:
      # 3. 副链异常：降级处理
      final_action = "WATCH"
  ```

#### 禁止事项
- ❌ 不允许修改schema契约
- ❌ 不允许绕过主链直接执行
- ❌ 不允许修改healthcheck逻辑

#### 验收标准
- runner输出完整contract字段
- routing裁决正确生效
- fallback机制显式且可靠
- 日志可观测且符合SLO

---

## 五、八文档工程映射表

| 治理文档 | 负责人 | 实现位置 | 产出物 |
|---------|-------|---------|--------|
| 主文档 | B主责，A/C配合 | transmission_engine/core/ | 核心引擎代码、契约基线 |
| Chain Routing Policy | C | runner | 路由裁决逻辑、冲突处理规则 |
| Error & Fallback Codebook | B | configs/ | 错误码映射表、降级规则 |
| Replay & Idempotency Policy | B | scripts/ | 幂等校验脚本、一致性检查 |
| Consumer Contract Mapping | A | schemas/ | 字段映射表、消费规则文档 |
| Contract Versioning | A | schemas/ | 版本控制机制、兼容性规则 |
| E2E Acceptance Checklist | A主责，B配合 | tests/ | 验收样本集、验收脚本 |
| Observability & SLO Spec | C | logging/ | 指标与日志 |

---

## 六、主链融合规则（一票否决）

### 禁止行为（CI必须拦截）
- ❌ safe_to_consume=false 仍执行
- ❌ 副链直接触发EXECUTE
- ❌ conflict_flag=true 仍给A评级
- ❌ replay不一致无解释
- ❌ RISK_OFF未封顶trade_grade
- ❌ 无decision_source标记
- ❌ 主链缺失时副链仍safe_to_consume=true
- ❌ C2场景conflict_flag=true
- ❌ theme_capped_by_macro未设置且macro_regime=RISK_OFF
- ❌ 无contract_name/version/producer_module信封

### 强制行为
- ✅ 所有输出必须包含contract信封
- ✅ fallback必须显式记录原因
- ✅ 宏观RISK_OFF必须封顶为C级
- ✅ 主链缺失必须标记degraded

---

## 七、最终验收标准（全部满足）

### Contract层（A负责）
- [ ] schema完整且通过校验（PR原文15个字段）
- [ ] contract_mapping.yaml存在且覆盖PR原文字段
- [ ] registry正确指向
- [ ] E2E样本覆盖6类场景（E2E-01 ~ E2E-06）
- [ ] 版本兼容性规则明确（推荐1 minor version兼容窗口）

### Gate层（B负责）
- [ ] CI可拦截所有违规情况（含8种错误码场景）
- [ ] replay一致性可检测（一致性率>99%）
- [ ] healthcheck覆盖异常路径（8种错误码全覆盖）
- [ ] fallback机制显式（所有降级必须带fallback_reason）
- [ ] 错误码映射表完整（CONFIG_MISSING/INVALID, THEME_MAPPING_FAILED, BASKET_EMPTY, MARKET_DATA_MISSING, VALIDATION_SKIPPED, STATE_ENGINE_INSUFFICIENT_DATA, DOWNSTREAM_OUTPUT_DEGRADED）

### Runtime层（C负责）
- [ ] runner输出完整字段（业务字段+输出信包+主链融合字段）
- [ ] routing裁决正确（macro > theme优先级，C2的conflict_flag=false）
- [ ] fallback可靠（所有降级路径测试通过）
- [ ] 日志符合SLO（按文档定义的SLI指标）
- [ ] conflict_type正确设置（C1/C2/C3/unknown）
- [ ] theme_capped_by_macro正确标记

### 主链接入（全员）
- [ ] 副链不能绕过主链
- [ ] 决策受macro约束
- [ ] conflict_flag正确设置
- [ ] decision_source准确

---

## 八、执行顺序（关键）

1. **Contract先行**（A）：建立契约基础
2. **Gate同步**（B）：构建拦截能力
3. **Runtime实现**（C）：完成核心逻辑
4. **主链融合**（全员）：集成验证

---

## 九、核心原则（必须理解）

> **副链不是独立信号源，而是"被主链约束的增强层"**
>
> **文档不是目标，可阻断的系统行为才是目标**

所有开发必须围绕这个原则，任何绕过主链约束的设计都应被CI拦截。

---

## 十、附录：参考文档

本任务书基于以下8个治理文档制定：

1. 主题板块催化持续性引擎_v1.0_唯一规范主文档.md
2. Chain Routing Policy_链路由策略.md
3. Error & Fallback Codebook_错误与备用代码手册.md
4. Replay & Idempotency Policy_重放与幂等政策.md
5. Consumer Contract Mapping Table_消费者合同映射表.md
6. Contract Versioning & Compatibility_合同版本控制与兼容性.md
7. E2E Acceptance Checklist_端对端接受清单.md
8. Observability & SLO Spec_可观测性与SLO规范.md

---

## 十一、已修复错误列表

本次修掉的错误项：

1. **✅ C2规则修正**：将`macro_regime == "MIXED"`时的`conflict_flag = True`改为`conflict_flag = False`，保留`conflict_type = "C2_market_neutral"`作为解释标签

2. **✅ Replay幂等键恢复**：将`event_id + config_version + evaluation_window + data_snapshot_timestamp`改为`event_id + config_version + evaluation_window`，删除`data_snapshot_timestamp`

3. **✅ Consumer Contract Mapping字段口径修正**：删除"18个字段全部覆盖"表述，改为与PR原文mapping表一致的15个字段；删除mapping表中的`error_code`行

4. **✅ healthcheck字段名修正**：将`required = ["contract_name","version","safe_to_consume"]`改为`required = ["contract_name","contract_version","safe_to_consume"]`

5. **✅ E2E归属统一**：全文统一为"E2E Acceptance Checklist：A主责，B配合"，在A的职责描述、八文档工程映射表、最终验收标准三处保持一致

6. **✅ 主文档归属修正**：将"主文档 | 全员"改为"主文档 | B主责，A/C配合"，与PR主文档owner一致

7. **✅ 删除越界内容Fatigue**：删除"补充：叙事疲劳（Fatigue）机制（系统核心alpha）"整段内容

8. **✅ 删除越界内容主题引擎实现模块清单**：删除theme_event_router、catalyst_detector、theme_mapper、basket_builder、basket_validator、continuation_engine、trade_adapter这组"主题引擎实现"小节

9. **✅ 删除扩写过度的强行为规则**：删除B中的`if error_code: safe_to_consume = False`和A的mapping表中超出PR原文的强制默认动作

10. **✅ 修正主链融合与routing冲突**：统一`RISK_OFF -> mainchain_capped_theme`口径，全文保持一致

11. **✅ 统一contract/输出信包字段归属**：明确`contract_name/contract_version/producer_module/safe_to_consume/fallback_reason/error_code`为输出信包字段，统一按"输出信包约束"表述

12. **✅ 修正wording**：删除"18个contract字段"、"系统核心alpha"、"补全snapshot_time/data_version"、"完整theme_output字段"、"主文档 | 全员"等错误表述

---

**文档版本**: v1.1（最小修错版）
**创建时间**: 2026-04-16
**适用项目**: 重大事件驱动交易系统 - PR61主题板块引擎集成
**核心原则**: 严格按PR61八文档原文，只修错误不做增强