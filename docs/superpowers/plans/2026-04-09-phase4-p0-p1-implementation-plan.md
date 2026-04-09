# Phase4 P0/P1 Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete P0/P1 blockers from the main planning file so the project can pass Phase4 pre-production acceptance.

**Architecture:** Keep existing pipeline boundaries, then fix data-truth first (market/news failure behavior), then consistency (schema/id/master), then persistence and regression gates. Every change uses TDD and an explicit rollback switch.

**Tech Stack:** Python 3.9, pytest, YAML config, WebSocket event bus, existing EDT scripts and CI workflow.

---

## File Map (locked before implementation)

- Modify: `scripts/data_adapter.py` (real market source + strict unavailable behavior)
- Modify: `scripts/ai_event_intel.py` (prod fallback hard-fail + schema default)
- Modify: `scripts/realtime_news_monitor.py` (test-data hard block + consistent degrade path)
- Modify: `scripts/opportunity_score.py` (realtime price dependency and WATCH fallback)
- Modify: `configs/edt-modules-config.yaml` (provider/fallback/master flags)
- Modify: `configs/premium_stock_pool.yaml` (price metadata aligned for realtime use)
- Modify: `scripts/ai_signal_adapter.py` (schema default to v1.0)
- Modify: `scripts/event_bus.py` (history persistence jsonl/snapshot)
- Modify: `scripts/run_c_module_stack.py` (safe mock behavior in non-dev)
- Modify: `.github/workflows/ci.yml` (add regression gates)
- Test: `tests/test_data_adapter.py`
- Test: `tests/test_ai_event_intel.py`
- Test: `tests/test_opportunity_score.py`
- Test: `tests/test_conduction_mapper_dynamic.py`
- Test: `tests/test_event_bus.py`
- Test: `tests/test_c_contracts.py`

---

### Task 1: Real Market Data (P0)

**Files:**
- Modify: `scripts/data_adapter.py`
- Modify: `configs/edt-modules-config.yaml`
- Test: `tests/test_data_adapter.py`

- [ ] **Step 1: Write failing tests for realtime market fields**

```python
def test_fetch_market_data_reports_realtime_source_when_enabled(monkeypatch):
    adapter = DataAdapter()
    monkeypatch.setattr(adapter, "_fetch_vix", lambda: {"level": 18.2, "change_pct": 1.5})
    monkeypatch.setattr(adapter, "_fetch_spx", lambda: {"change_pct": -0.4})
    out = adapter.fetch_market_data()
    assert out["market_data_source"] == "realtime"
    assert out["is_test_data"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q tests/test_data_adapter.py`
Expected: FAIL (source currently unavailable)

- [ ] **Step 3: Implement minimal realtime fetch + strict fallback shape**

```python
if realtime_ok:
    return {"vix_level": vix, "spx_change_pct": spx, "market_data_source": "realtime", "is_test_data": False}
return {"vix_level": None, "spx_change_pct": None, "market_data_source": "failed", "is_test_data": True}
```

- [ ] **Step 4: Re-run tests**

Run: `python3 -m pytest -q tests/test_data_adapter.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/data_adapter.py configs/edt-modules-config.yaml tests/test_data_adapter.py
git commit -m "feat: add realtime market data adapter with strict unavailable mode"
```

### Task 2: News Source Hard-Fail in Production (P0)

**Files:**
- Modify: `scripts/ai_event_intel.py`
- Modify: `scripts/realtime_news_monitor.py`
- Test: `tests/test_ai_event_intel.py`

- [ ] **Step 1: Write failing tests for prod no-fallback policy**

```python
def test_news_ingestion_prod_fails_when_sources_unavailable(monkeypatch):
    mod = NewsIngestion()
    monkeypatch.setattr("ai_event_intel._safe_fetch", lambda *_: None)
    out = mod.run({"environment": "prod", "sources": ["https://x"], "retries": 0})
    assert out.status.value == "failed"
```

- [ ] **Step 2: Run targeted tests**

Run: `python3 -m pytest -q tests/test_ai_event_intel.py`
Expected: FAIL

- [ ] **Step 3: Implement environment-aware fallback policy**

```python
if not items and environment == "prod":
    return ModuleOutput(status=ModuleStatus.FAILED, errors=[{"code": "NEWS_SOURCE_UNAVAILABLE"}])
```

- [ ] **Step 4: Add monitor guardrail for failed ingestion**

Run: `python3 -m pytest -q tests/test_ai_event_intel.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/ai_event_intel.py scripts/realtime_news_monitor.py tests/test_ai_event_intel.py
git commit -m "fix: enforce production hard-fail when news sources are unavailable"
```

### Task 3: Replace Static last_price in Opportunity Flow (P0)

**Files:**
- Modify: `scripts/opportunity_score.py`
- Modify: `configs/premium_stock_pool.yaml`
- Test: `tests/test_opportunity_score.py`

- [ ] **Step 1: Write failing test for WATCH fallback without realtime price**

```python
def test_opportunity_uses_watch_when_realtime_price_missing():
    out = OpportunityScorer().run({"last_price": None, "signal": "LONG", ...})
    assert out.data["final_action"] == "WATCH"
```

- [ ] **Step 2: Run tests and confirm fail**

Run: `python3 -m pytest -q tests/test_opportunity_score.py`
Expected: FAIL

- [ ] **Step 3: Implement realtime-first pricing logic**

```python
price = raw.get("realtime_price")
if price is None:
    return watch_payload("missing_realtime_price")
```

- [ ] **Step 4: Re-run opportunity tests**

Run: `python3 -m pytest -q tests/test_opportunity_score.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/opportunity_score.py configs/premium_stock_pool.yaml tests/test_opportunity_score.py
git commit -m "fix: make opportunity scoring realtime-price first with watch fallback"
```

### Task 4: Schema Version Unification to v1.0 (P0)

**Files:**
- Modify: `scripts/ai_event_intel.py`
- Modify: `scripts/ai_signal_adapter.py`
- Test: `tests/test_c_contracts.py`, `tests/test_ai_event_intel.py`, `tests/test_ai_signal_adapter.py`

- [ ] **Step 1: Write failing assertions for schema defaults**

```python
assert item["schema_version"] == "v1.0"
```

- [ ] **Step 2: Run target tests**

Run: `python3 -m pytest -q tests/test_ai_event_intel.py tests/test_ai_signal_adapter.py tests/test_c_contracts.py`
Expected: FAIL

- [ ] **Step 3: Change defaults to v1.0**

```python
"schema_version": raw.get("schema_version", "v1.0")
```

- [ ] **Step 4: Re-run tests**

Run: `python3 -m pytest -q tests/test_ai_event_intel.py tests/test_ai_signal_adapter.py tests/test_c_contracts.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/ai_event_intel.py scripts/ai_signal_adapter.py tests/test_ai_event_intel.py tests/test_ai_signal_adapter.py tests/test_c_contracts.py
git commit -m "refactor: unify schema defaults to v1.0 across intelligence pipeline"
```

### Task 5: EventBus Persistence + Multi-Instance Control (P1)

**Files:**
- Modify: `scripts/event_bus.py`
- Modify: `scripts/run_c_module_stack.py`
- Modify: `configs/edt-modules-config.yaml`
- Test: `tests/test_event_bus.py`

- [ ] **Step 1: Add failing tests for history persistence/reload**

```python
def test_event_bus_persists_history_to_jsonl(tmp_path):
    ...
```

- [ ] **Step 2: Run event bus tests (expect fail)**

Run: `python3 -m pytest -q tests/test_event_bus.py`

- [ ] **Step 3: Implement jsonl append + startup reload**

```python
with open(self.history_path, "a", encoding="utf-8") as f:
    f.write(message.to_json() + "\n")
```

- [ ] **Step 4: Add role gate for mock producer (dev-only default)**

Run: `python3 -m pytest -q tests/test_event_bus.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/event_bus.py scripts/run_c_module_stack.py configs/edt-modules-config.yaml tests/test_event_bus.py
git commit -m "feat: persist event bus history and add safer role-based runtime behavior"
```

### Task 6: Regression Gates and CI Integration (P1/P2)

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `scripts/verify_direction_consistency.py` (if needed for exit codes)
- Create: `scripts/verify_sector_coverage.py`
- Create: `scripts/verify_dedupe_accuracy.py`

- [ ] **Step 1: Write failing smoke tests/commands for new verifiers**

Run:
- `python3 scripts/verify_sector_coverage.py`
- `python3 scripts/verify_dedupe_accuracy.py`

Expected: command missing / FAIL

- [ ] **Step 2: Implement minimal verifiers with clear non-zero exit on threshold fail**

```python
if coverage < threshold:
    raise SystemExit(1)
```

- [ ] **Step 3: Wire verifiers into CI workflow**

```yaml
- name: Run regression gates
  run: |
    python scripts/verify_sector_coverage.py
    python scripts/verify_dedupe_accuracy.py
    python scripts/verify_direction_consistency.py
```

- [ ] **Step 4: Validate locally**

Run: `python3 -m pytest -q && python3 scripts/system_healthcheck.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml scripts/verify_sector_coverage.py scripts/verify_dedupe_accuracy.py scripts/verify_direction_consistency.py
git commit -m "chore: add regression quality gates for coverage dedupe and direction consistency"
```

---

## Final Verification Gate (before claiming completion)

- [ ] `python3 -m pytest -q`
- [ ] `python3 scripts/system_healthcheck.py`
- [ ] `python3 scripts/run_phase3_pressure_gate.py`
- [ ] `python3 scripts/verify_direction_consistency.py`

Expected: all pass; no silent fallback in production mode; schema defaults unified to `v1.0`.
