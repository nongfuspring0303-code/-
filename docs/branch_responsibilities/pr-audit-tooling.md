# Branch Responsibility: pr/audit-tooling

## Purpose

This branch is reserved for reproducible audit/metrics tooling only.

## In Scope

- `scripts/live_chain_audit.py`
  - clean-window audit for hit -> sector -> opportunity chain
  - field consistency and primary-sector-only pass metrics
- `scripts/unified_quality_report.py`
  - aggregate quality report across existing metrics scripts
- Minimal docs that explain audit entrypoints and usage

## Out of Scope

- Runtime decision logic changes (`realtime_news_monitor.py`, `opportunity_score.py`)
- Policy behavior changes (`configs/*.yaml` that affect live decisions)
- Frontend UI and layout (`canvas/*`)
- Generated outputs in PR body scope (`reports/*`, `logs/*`)

## Merge Gate

- Tool script runs successfully with current local environment.
- Output paths and metric definitions are deterministic and documented.
