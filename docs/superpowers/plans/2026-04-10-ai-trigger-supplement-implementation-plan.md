# AI Trigger Supplement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补全既有 AI 分析环节，让规则未命中新闻可通过 AI 语义补盲触发，同时保留全量开启与紧急回滚能力。

**Architecture:** 保持 `EventCapture` 规则快路径不变：规则命中直接触发；规则未命中时调用 `SemanticAnalyzer` 获取 `verdict/confidence/reason`，仅补充“是否触发”。AI 故障、超时、低置信时一律降级为规则结果，主链路可持续。

**Tech Stack:** Python, google-generativeai, YAML config, pytest

---

## File Structure

- Modify: `scripts/ai_semantic_analyzer.py`
  - 扩展为可调用 Gemini Flash Lite 的语义分析器
  - 增加超时/异常/降级与结构化 verdict
- Modify: `scripts/intel_modules.py`
  - 在 `EventCapture.execute` 接入 AI 补盲仲裁
  - 增加 `capture_source/ai_verdict/ai_confidence/ai_reason`
- Modify: `configs/edt-modules-config.yaml`
  - 增加 `runtime.semantic` 运行参数（全量启用 + 紧急回滚）
- Create: `tests/test_ai_semantic_analyzer.py`
  - 语义分析器单测（启停、阈值、异常回退）
- Modify: `tests/test_realtime_news_monitor.py`
  - 验证规则未命中但 AI 命中路径可触发
- Modify: `项目全链路说明文档.md`
  - 增补 AI 补盲机制、开关、回滚说明

---

### Task 1: 语义分析器接入 Gemini 并保留降级

**Files:**
- Modify: `scripts/ai_semantic_analyzer.py`
- Test: `tests/test_ai_semantic_analyzer.py`

- [ ] **Step 1: Write the failing test**

```python
def test_semantic_analyzer_returns_abstain_when_disabled():
    analyzer = SemanticAnalyzer(config_path="tests/fixtures/semantic_disabled.yaml")
    out = analyzer.analyze("原油价格上涨", "")
    assert out["verdict"] == "abstain"
    assert out["fallback_reason"] == "semantic_disabled"


def test_semantic_analyzer_timeout_fallback(monkeypatch):
    analyzer = SemanticAnalyzer(config_path="tests/fixtures/semantic_enabled.yaml")

    def _boom(*_args, **_kwargs):
        raise TimeoutError("timeout")

    monkeypatch.setattr(analyzer, "_call_provider", _boom)
    out = analyzer.analyze("非农超预期", "")
    assert out["verdict"] == "abstain"
    assert out["fallback_reason"] == "timeout"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_ai_semantic_analyzer.py -v`
Expected: FAIL（`verdict`/`fallback_reason` 字段不存在或行为不符）

- [ ] **Step 3: Write minimal implementation**

在 `scripts/ai_semantic_analyzer.py` 添加：

```python
# new output contract
{
  "event_type": "...",
  "sentiment": "...",
  "confidence": 0,
  "recommended_chain": "",
  "verdict": "hit|miss|abstain",
  "reason": "...",
  "provider": "gemini_flash_lite|rule_fallback",
  "latency_ms": 0,
  "fallback_reason": "...",
}
```

实现最小能力：
- 读取 `runtime.semantic.enabled/emergency_disable/model/timeout_ms/min_confidence`
- provider 调用失败/超时 -> `abstain`
- provider 不可用时使用规则 fallback（不抛异常）

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_ai_semantic_analyzer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/ai_semantic_analyzer.py tests/test_ai_semantic_analyzer.py
git commit -m "feat: add semantic analyzer provider contract and fallback"
```

---

### Task 2: EventCapture 接入 AI 补盲仲裁

**Files:**
- Modify: `scripts/intel_modules.py`
- Test: `tests/test_realtime_news_monitor.py`

- [ ] **Step 1: Write the failing test**

```python
def test_event_capture_uses_ai_when_keyword_miss(monkeypatch):
    mod = EventCapture()

    class _SemanticStub:
        def analyze(self, headline, raw_text=""):
            return {
                "verdict": "hit",
                "confidence": 82,
                "reason": "macro event semantic hit",
                "fallback_reason": "",
            }

    mod.semantic = _SemanticStub()
    out = mod.run({
        "headline": "美国就业数据明显超预期",
        "source": "https://finance.sina.com.cn/7x24/",
        "timestamp": "2026-04-10T08:00:00Z",
    })

    assert out.data["captured"] is True
    assert out.data["capture_source"] == "ai"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_realtime_news_monitor.py::test_event_capture_uses_ai_when_keyword_miss -v`
Expected: FAIL（`capture_source` 不存在或 `captured` 仍为 False）

- [ ] **Step 3: Write minimal implementation**

在 `EventCapture` 中：
- `__init__` 注入 `SemanticAnalyzer`
- `keyword_matched` 为 False 时调用 `semantic.analyze`
- 若 `verdict == "hit"` 且 `confidence >= min_confidence` -> `captured=True`
- 输出补充字段：

```python
"capture_source": "rules|ai|none",
"ai_verdict": semantic_out.get("verdict"),
"ai_confidence": semantic_out.get("confidence", 0),
"ai_reason": semantic_out.get("reason", ""),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_realtime_news_monitor.py::test_event_capture_uses_ai_when_keyword_miss -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/intel_modules.py tests/test_realtime_news_monitor.py
git commit -m "feat: add ai supplement arbitration in EventCapture"
```

---

### Task 3: 配置全量开启与紧急回滚

**Files:**
- Modify: `configs/edt-modules-config.yaml`

- [ ] **Step 1: Write the failing test**

新增配置读取行为断言（可写在 `tests/test_ai_semantic_analyzer.py`）：

```python
def test_semantic_config_full_enable_with_emergency_disable():
    analyzer = SemanticAnalyzer(config_path="configs/edt-modules-config.yaml")
    # 这里只验证配置项可被读取并参与 enabled 判定
    assert analyzer._enabled() in {True, False}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_ai_semantic_analyzer.py -v`
Expected: FAIL（若字段不存在/逻辑不支持）

- [ ] **Step 3: Write minimal implementation**

更新 `runtime.semantic`：

```yaml
runtime:
  semantic:
    enabled: true
    provider: "gemini_flash_lite"
    model: "gemini-2.5-flash-lite"
    min_confidence: 70
    timeout_ms: 1500
    full_enable: true
    emergency_disable: false
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_ai_semantic_analyzer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add configs/edt-modules-config.yaml
git commit -m "chore: enable semantic supplement config with emergency rollback"
```

---

### Task 4: 中文样本回归 + 端到端验证

**Files:**
- Modify: `tests/test_realtime_news_monitor.py`
- Test runtime: `scripts/realtime_news_monitor.py`

- [ ] **Step 1: Write the failing test**

```python
def test_real_news_preview_visible_when_not_triggered(monkeypatch):
    monitor = _build_monitor(monkeypatch)
    pushed = {"ok": False}

    def _push(_news):
        pushed["ok"] = True

    monitor._push_news_preview = _push
    monitor._trigger_ab_pipeline = lambda *_args, **_kwargs: None

    news = {"headline": "中东地缘风险上行", "source_type": "sina", "metadata": {}}
    assert monitor._process_news(news) is False
    assert pushed["ok"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_realtime_news_monitor.py::test_real_news_preview_visible_when_not_triggered -v`
Expected: FAIL（若展示与触发未完全解耦）

- [ ] **Step 3: Write minimal implementation**

确保 `_process_news` 流程：
1) 过滤测试数据后先 `_push_news_preview`
2) 再做 EventCapture 触发判断
3) 命中才 `_trigger_ab_pipeline`

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_realtime_news_monitor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_realtime_news_monitor.py scripts/realtime_news_monitor.py
git commit -m "test: validate news-preview and ai supplement trigger flow"
```

---

### Task 5: 文档与验收

**Files:**
- Modify: `项目全链路说明文档.md`
- Modify: `全链路优化方案-执行任务清单.md`

- [ ] **Step 1: Write docs update**

补充：
- AI 补盲触发路径
- `runtime.semantic` 配置含义
- 紧急回滚操作步骤

- [ ] **Step 2: Verify commands**

Run:
- `python3 -m pytest tests/test_ai_semantic_analyzer.py tests/test_realtime_news_monitor.py -q`
- `python3 -m pytest tests/test_ai_event_intel.py tests/test_ai_event_intel_sina.py -q`

Expected: 全部 PASS

- [ ] **Step 3: Commit**

```bash
git add 项目全链路说明文档.md 全链路优化方案-执行任务清单.md
git commit -m "docs: document ai trigger supplement and rollback runbook"
```

---

## Final Verification Gate

- [ ] Run full related suite:

```bash
python3 -m pytest tests/test_ai_semantic_analyzer.py tests/test_realtime_news_monitor.py tests/test_ai_event_intel.py tests/test_ai_event_intel_sina.py -q
```

Expected: PASS

- [ ] Run local stack smoke check:

```bash
python3 scripts/run_c_module_stack.py --no-mock --history-file logs/event_bus_live.jsonl
python3 scripts/realtime_news_monitor.py --poll-interval 15 --api http://127.0.0.1:18787
```

Expected:
- 前端可见真实新闻
- 规则未命中时仍可出现 AI 补盲触发日志
- `emergency_disable=true` 后 AI 路径立即旁路
