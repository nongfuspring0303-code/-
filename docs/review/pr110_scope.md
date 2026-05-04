# PR110 Scope (Minimal Causal Contract)

## In Scope
- expectation_gap contract output
- market_validation evidence array output
- dominant_driver output
- relative/absolute direction contract output
- config-driven thresholds and defaults under `configs/tier1_mapping_rules.yaml`
- unit tests for the four outputs
- causal contract schema/policy artifacts

## Field Definitions (PR110 atomic outputs)
- `expectation_gap`: `positive_surprise | negative_surprise | in_line | unknown | conflict`
- `macro_factor`: primary macro factor object (`factor/direction/strength`)
- `market_validation`: `validated | partial | unconfirmed | contradicted | insufficient_data` + evidence array
- `dominant_driver`: `primary + secondary[]`
- `relative_direction`: `outperform | underperform | neutral | unknown`
- `absolute_direction`: `positive | negative | neutral | mixed | unknown`
- `impact_layers`: fixed layer list for contract (`macro/sector/theme/ticker/liquidity`)
- `confidence`: causal and validation confidence in `[0,1]`

## Fallback Rules
- missing expectation gap => `unknown` (never silently converted to `in_line`)
- invalid expectation gap input => `conflict`
- missing market change data => evidence `observed=missing`, top status `unconfirmed/insufficient_data`
- PR110 only extends analysis contract, does not produce execution decisions

## Consumer Boundary
- PR110 outputs are contract-layer analytics only.
- No auto-trading fields may be emitted or consumed from this layer (`final_action`, `trade_decision`, `execution_suggestion` out of scope).

## CI Validation
- `tests/test_causal_contract_schema.py`
- `tests/test_causal_contract_fields.py`
- `tests/test_causal_contract_consumer_boundary.py`

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
