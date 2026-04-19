# Golden E2E Acceptance Report

Generated at: 2026-04-17T19:34:23.909684Z

## Layer 0
- healthcheck: PASS
- returncode: 0

## Case Matrix

| CASE_ID | CHAIN_OK | FIELDS_OK | PATH_OK | SIGNAL_OK | RISK_OK | MIXED_OK | FINAL |
|---|---|---|---|---|---|---|---|
| earnings_beat_nvda_001 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| earnings_miss_bank_001 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| earnings_sector_mismatch_001 | PASS | PASS | PASS | FAIL | PASS | PASS | FAIL |
| geopolitics_low_trust_high_impact_001 | PASS | PASS | PASS | FAIL | PASS | PASS | FAIL |
| geopolitics_oil_spike_001 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| geopolitics_strait_shipping_001 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| low_trust_incomplete_news_001 | PASS | PASS | FAIL | PASS | PASS | PASS | FAIL |
| low_trust_pseudo_official_001 | PASS | PASS | FAIL | PASS | PASS | PASS | FAIL |
| low_trust_rumor_low_rank_001 | PASS | PASS | FAIL | PASS | PASS | PASS | FAIL |
| low_trust_weak_news_001 | PASS | PASS | FAIL | PASS | PASS | PASS | FAIL |
| macro_cpi_hot_001 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| macro_rate_cut_001 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| macro_rate_hike_001 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| macro_tight_mixed_regime_001 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| macro_weak_narrative_strong_asset_001 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| policy_bullish_with_risk_gate_001 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| policy_qe_signal_001 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| policy_tariff_escalation_001 | PASS | PASS | PASS | PASS | PASS | PASS | PASS |

## Metrics
- chain_completeness_rate: 1.0000
- required_fields_missing_rate: 0.0000
- direction_consistency_rate: 0.8889
- path_consistency_rate: 0.7778
- high_risk_false_release_rate: 0.0000
- threshold_pass: PASS
