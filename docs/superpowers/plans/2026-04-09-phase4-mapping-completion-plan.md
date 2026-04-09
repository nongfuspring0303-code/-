# Phase4 Mapping Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete missing event-to-chain mappings and make mapping quality auditable with deterministic regression gates.

**Architecture:** Keep existing semantic-first + rules-fallback pipeline, then expand mapping coverage by event families (A/B/D/F/G), enforce per-family tests, and add a mapping-quality verifier that fails CI when coverage or precision drops.

**Tech Stack:** Python 3.9, YAML mapping config, pytest, existing conduction mapper, CI workflow.

---

## File Map

- Modify: `configs/conduction_chain.yaml`
- Modify: `scripts/conduction_mapper.py`
- Create: `scripts/verify_mapping_quality.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `tests/test_conduction_mapper_dynamic.py`
- Create: `tests/test_mapping_families.py`

---

### Task 1: Expand Mapping Families in YAML (A/B/D/F/G)

**Files:**
- Modify: `configs/conduction_chain.yaml`
- Test: `tests/test_mapping_families.py`

- [ ] **Step 1: Write failing tests for missing families**

```python
def test_mapping_contains_required_families():
    # assert families A/B/D/F/G can map to at least one chain
```

- [ ] **Step 2: Run tests to verify fail**

Run: `python3 -m pytest -q tests/test_mapping_families.py`
Expected: FAIL

- [ ] **Step 3: Add mapping entries by family in conduction_chain.yaml**

```yaml
event_to_chain_mapping:
  - event_keywords: ["bank run", "流动性危机"]
    chain_id: "liquidity_stress_chain"
```

- [ ] **Step 4: Re-run tests**

Run: `python3 -m pytest -q tests/test_mapping_families.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add configs/conduction_chain.yaml tests/test_mapping_families.py
git commit -m "feat: complete A/B/D/F/G event mapping families"
```

### Task 2: ConductionMapper Family Routing Safety

**Files:**
- Modify: `scripts/conduction_mapper.py`
- Modify: `tests/test_conduction_mapper_dynamic.py`

- [ ] **Step 1: Add failing tests for ambiguous keyword collisions**

```python
def test_trade_meeting_not_mapped_to_tariff_chain_when_talk_context_present():
    ...
```

- [ ] **Step 2: Run tests to verify fail**

Run: `python3 -m pytest -q tests/test_conduction_mapper_dynamic.py`

- [ ] **Step 3: Implement deterministic precedence (semantic > exact phrase > token)**

```python
# do not allow broad token to override exact contextual phrase
```

- [ ] **Step 4: Re-run tests**

Run: `python3 -m pytest -q tests/test_conduction_mapper_dynamic.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/conduction_mapper.py tests/test_conduction_mapper_dynamic.py
git commit -m "fix: enforce safe precedence for conduction mapping collisions"
```

### Task 3: Mapping Quality Verifier Script

**Files:**
- Create: `scripts/verify_mapping_quality.py`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add failing smoke invocation**

Run: `python3 scripts/verify_mapping_quality.py --min-family-coverage 1.0 --min-precision 0.9`
Expected: command missing / FAIL

- [ ] **Step 2: Implement verifier**

```python
if family_coverage < threshold or precision < threshold:
    raise SystemExit(1)
```

- [ ] **Step 3: Wire into CI gates**

```yaml
- name: Verify mapping quality
  run: python scripts/verify_mapping_quality.py --min-family-coverage 1.0 --min-precision 0.9
```

- [ ] **Step 4: Validate locally**

Run: `python3 scripts/verify_mapping_quality.py --min-family-coverage 1.0 --min-precision 0.9`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/verify_mapping_quality.py .github/workflows/ci.yml
git commit -m "chore: add mapping quality gate and CI enforcement"
```

### Task 4: Full Mapping Regression Bundle

**Files:**
- Modify: `tests/test_mapping_families.py`
- Modify: `tests/test_conduction_mapper_dynamic.py`

- [ ] **Step 1: Add representative samples for each family (A/B/D/F/G)**

```python
@pytest.mark.parametrize("headline,expected_chain", [...])
def test_family_samples_map_expected_chain(headline, expected_chain):
    ...
```

- [ ] **Step 2: Run regression tests**

Run: `python3 -m pytest -q tests/test_mapping_families.py tests/test_conduction_mapper_dynamic.py`

- [ ] **Step 3: Fix any false-positive collision cases**

Run: `python3 -m pytest -q tests/test_mapping_families.py tests/test_conduction_mapper_dynamic.py`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_mapping_families.py tests/test_conduction_mapper_dynamic.py
git commit -m "test: add full family mapping regression set"
```

---

## Final Verification Gate

- [ ] `python3 -m pytest -q`
- [ ] `python3 scripts/verify_mapping_quality.py --min-family-coverage 1.0 --min-precision 0.9`
- [ ] `python3 scripts/verify_sector_coverage.py --min-coverage 0.90`
- [ ] `python3 scripts/verify_dedupe_accuracy.py --min-accuracy 0.95`
- [ ] `python3 scripts/verify_direction_consistency.py --min-rate 0.85`

Expected: all pass; no regression in trade-meeting classification; family coverage complete.
