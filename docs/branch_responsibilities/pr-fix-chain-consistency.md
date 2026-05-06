# Branch Responsibility: pr/fix-chain-consistency

## Purpose

This branch is reserved for production-impacting fixes in the news -> sector -> stock chain.

## In Scope

- `scripts/realtime_news_monitor.py`
  - opportunity payload identity consistency (`trace_id/request_id/batch_id/timestamp` alignment)
- `scripts/opportunity_score.py`
  - primary-sector-only enforcement logic
  - primary sector selection by impact score (not input order)
- `configs/premium_stock_pool.yaml`
  - flags related to primary-sector-only policy
- `tests/test_opportunity_score.py`
  - regression tests for the above behavior

## Out of Scope

- Frontend UI draft and style changes (`canvas/*`)
- Runtime logs and generated reports (`logs/*`, `reports/*`)
- Ad-hoc memory or personal notes
- Large refactors unrelated to chain correctness

## Merge Gate

- Must pass local test:
  - `/usr/bin/python3 -m pytest -q tests/test_opportunity_score.py`
- Must verify clean-window chain audit before public PR.
