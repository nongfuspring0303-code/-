# PR110 Scope (Minimal Causal Contract)

## In Scope
- expectation_gap contract output
- market_validation evidence array output
- dominant_driver output
- relative/absolute direction contract output
- config-driven thresholds and defaults under `configs/tier1_mapping_rules.yaml`
- unit tests for the four outputs

## Out of Scope
- fatigue_score / lifecycle_state / time_scale / decay_profile
- execution_suggestion and any execution auto-action logic
- path quality eval and attribution report engine changes
- workflow runner / gate / execution / final_action changes

## Risk & Rollback
- Risk is limited to analysis-layer output schema extension in `ConductionMapper`.
- Rollback strategy: revert this PR branch commit; no migration needed.

## Acceptance
- `tests/test_conduction_mapper_dynamic.py` passes with new PR110 contract tests.
- Existing mapper tests stay green.
- No runtime artifacts (`reports/`, `logs/`) added by this PR.
