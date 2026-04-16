# Theme Output Mainchain Consumption Rules (Member A Scope)

## Purpose
Define how mainchain consumers process `theme_output` without changing runner logic.

## Input Contract Extension
Mainchain input schema accepts optional `theme_output` object.

## Consumption Rules
- `safe_to_consume = false` -> treat as `DEGRADED` mode and prohibit direct execution.
- `conflict_flag = true` -> treat as degraded and require conservative action.
- `theme_capped_by_macro = true` -> disallow high grade actions (A/B).

## Contract Boundary
- This document only defines schema/contract-level consumer behavior.
- No runtime routing or runner behavior is changed in this scope.
