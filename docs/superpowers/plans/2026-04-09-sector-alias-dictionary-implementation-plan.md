# Sector Alias Dictionary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a configurable sector alias dictionary so English/Chinese sector names map to one canonical sector and Energy sector opportunities can resolve to premium pool stocks.

**Architecture:** Introduce a config-driven alias resolver in B-layer scoring path. Normalize sector keys for both incoming candidates and fallback pool matching, while keeping existing opportunity output schema unchanged.

**Tech Stack:** Python 3, pytest, YAML config

---

### Task 1: Add failing regression test for cross-language sector matching

**Files:**
- Modify: `tests/test_opportunity_score.py`
- Test: `tests/test_opportunity_score.py`

- [ ] **Step 1: Write the failing test**

```python
def test_fallback_pool_supports_sector_alias_dictionary():
    scorer = OpportunityScorer()
    payload = {
        "trace_id": "evt_energy_alias",
        "schema_version": "v1.0",
        "sectors": [{"name": "Energy", "direction": "LONG", "impact_score": 0.8, "confidence": 0.8}],
        "stock_candidates": [],
    }

    out = scorer.build_opportunity_update(payload)
    assert any(opp["symbol"] == "XOM" for opp in out["opportunities"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_opportunity_score.py -k sector_alias_dictionary -v`
Expected: FAIL because `Energy` does not match `能源` in premium pool.

### Task 2: Implement configurable sector alias dictionary

**Files:**
- Create: `configs/sector_aliases.yaml`
- Modify: `scripts/opportunity_score.py`
- Test: `tests/test_opportunity_score.py`

- [ ] **Step 1: Add alias config file**

```yaml
schema_version: v1.0
updated_at: "2026-04-09T00:00:00Z"
aliases:
  能源: [Energy, Oil & Gas, Oil and Gas]
  科技: [Technology, Tech]
  金融: [Financials, Finance, Financial Services]
  医疗: [Healthcare, Health Care]
  工业: [Industrials]
  公用事业: [Utilities]
  消费: [Consumer, Consumer Cyclical, Consumer Staples]
```

- [ ] **Step 2: Implement minimal resolver in scorer path**

```python
class SectorAliasResolver:
    def canonical(self, name: Any) -> str: ...

class PremiumStockPool:
    def canonical_sector(self, name: Any) -> str: ...

# normalize sector key when grouping candidates
key = _norm_sector(self.pool.canonical_sector(cand.get("sector", "")))

# normalize sector key when selecting by sector
norm_sector = _norm_sector(self.pool.canonical_sector(sector_name))
```

- [ ] **Step 3: Run focused tests**

Run: `python3 -m pytest tests/test_opportunity_score.py -k "sector_alias_dictionary or realtime_price or missing_realtime_price" -v`
Expected: PASS.

### Task 3: Verify no regression in A/B mapping path

**Files:**
- Test: `tests/test_conduction_mapper_dynamic.py`

- [ ] **Step 1: Run mapper and opportunity smoke tests**

Run: `python3 -m pytest tests/test_conduction_mapper_dynamic.py tests/test_opportunity_score.py -v`
Expected: PASS.

### Task 4: Update project progress document

**Files:**
- Modify: `阶段三完成度+阶段四规划.md`

- [ ] **Step 1: Append execution record**

Document:
- Root cause (sector naming mismatch `Energy` vs `能源`)
- Solution (config-driven `sector_aliases.yaml` + scorer normalization)
- Evidence (new test name + pytest output)
- Runtime observation (Energy can now produce premium candidate `XOM`)

- [ ] **Step 2: Final verification**

Run: `python3 -m pytest tests/test_opportunity_score.py -k sector_alias_dictionary -v`
Expected: PASS.
