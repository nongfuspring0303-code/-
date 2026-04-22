# Member A Start-Now Checklist

## Current Role
- Phase 0 lead
- Phase 2 lead
- Contract/Gate/state-machine compatibility owner

## Today (P0)
1. Freeze baseline schema and files
2. Freeze v2.2 feature flags and rollback owners
3. Freeze joint-review touchpoints for A/B/C
4. Confirm stage-owner matrix published and acknowledged

## Phase 0 Exit Criteria (A-owned)
- [x] contract preconditions frozen
- [x] gate truth-source frozen
- [x] dual-write plan frozen
- [x] Go/No-Go checklist complete
- [x] golden fixtures landed (`tests/fixtures/edt_goldens/*.json`)
- [x] rollback sanitization supports DB compatibility downgrade

## Phase 2 Start Criteria
- [x] stage 1 logs can carry provenance and reject reason
- [x] blocker tests are defined
- [x] no default market-data path can bypass gate

## Phase 2 Deliverables (A-owned)
- [x] A1 default-value disguise removed
- [x] MarketValidator provenance gate in place
- [x] Output gate hard lines in place:
  - missing opportunity -> no EXECUTE
  - market_data_stale -> no EXECUTE
  - market_data_default_used -> no EXECUTE
  - market_data_fallback_used -> no EXECUTE
