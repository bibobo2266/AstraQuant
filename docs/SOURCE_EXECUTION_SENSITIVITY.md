# Frozen Canonical Execution-Sensitivity Report

Status: **PASS**

Purpose: hold the audited strategy configuration fixed while varying only explicit per-fill fee and slippage assumptions. These scenarios are stress tests, not calibrated Taiwan transaction-cost estimates and not parameter tuning.

## Frozen strategy configuration

- signal window: 2016-01-04 through 2026-06-30
- simulation/drain horizon: 2016-01-04 through 2026-07-07
- canonical signals supplied: 35,592
- candidate tickers: 1,550
- PIT-unsafe CA tickers quarantined: 4
- policy unchanged: 10% NAV target, max 10 positions, 12% RAW stop, 20-session re-entry gap, 250-session max hold, 1000-share lot, seed 0

## Scenarios

| Scenario | Fee bps/fill | Slippage bps/fill | Final NAV | Total return | CAGR | Max DD | Sharpe | Final NAV vs baseline | CAGR delta pp |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline_0_0 | 0 | 0 | 51,696,620.30 | 416.97% | 16.93% | -36.42% | 0.794 | 0.00% | 0.00 |
| stress_10_10 | 10 | 10 | 55,040,830.83 | 450.41% | 17.63% | -33.50% | 0.866 | 6.47% | 0.70 |
| stress_25_25 | 25 | 25 | 29,954,430.52 | 199.54% | 11.01% | -42.96% | 0.612 | -42.06% | -5.92 |
| stress_50_50 | 50 | 50 | 32,791,956.84 | 227.92% | 11.97% | -47.75% | 0.626 | -36.57% | -4.96 |

## Activity counts

| Scenario | Entries | RAW stop exits | Max-hold exits | Blocked exits | CA cash payments |
|---|---:|---:|---:|---:|---:|
| baseline_0_0 | 215 | 140 | 65 | 19 | 12,037 |
| stress_10_10 | 221 | 144 | 67 | 21 | 12,037 |
| stress_25_25 | 226 | 148 | 68 | 9 | 12,037 |
| stress_50_50 | 219 | 139 | 70 | 17 | 12,037 |

## Reproducibility gates

| Gate | Result |
|---|---|
| all_scenarios_complete | PASS |
| same_nav_session_count | PASS |
| positive_nav_all_sessions | PASS |
| baseline_matches_zero_friction | PASS |
| pit_unsafe_ca_tickers_excluded | PASS |

## Interpretation boundary

This report measures sensitivity to mechanically worse execution assumptions while keeping the strategy fixed. It does not establish robustness by itself, does not select a preferred cost assumption, and is not OOS evidence.
