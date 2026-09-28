# Frozen Canonical Local Parameter Neighborhood

Status: **PASS**

Purpose: perturb a small prespecified neighborhood around the frozen canonical configuration without selecting a winner, retuning after results, or changing the accounting path. This is a local parameter-stability diagnostic, not OOS validation.

## Prespecified neighborhood

- baseline: lookback 250, stop 12%, max hold 250 sessions
- lookback perturbations: 200 and 300
- stop perturbations: 10% and 14%
- max-hold perturbations: 200 and 300 sessions
- all other settings fixed: top-turnover universe fraction 25%, 10% NAV target, max 10 positions, 20-session re-entry gap, 1000-share lot, seed 0
- execution assumptions: zero explicit fees and zero slippage
- common-support exclusion: ticker 2823 is excluded from every row because its 2021-12-30 merger consideration is a multi-security conversion (2883 + 2883B + cash) not yet modeled by the canonical CA engine

## Results in prespecified order

| Scenario | Lookback | Stop | Max hold | Signals | 2823 signal rows removed | Entries | Stop exits | Max-hold exits | Final NAV | CAGR | Max DD | Sharpe | Final NAV vs baseline | CAGR delta pp |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 250 | 12% | 250 | 35,569 | 23 | 215 | 140 | 65 | 63,265,479.54 | 19.20% | -49.54% | 0.895 | 0.00% | 0.00 |
| lookback_200 | 200 | 12% | 250 | 38,986 | 24 | 226 | 153 | 63 | 22,684,599.08 | 8.11% | -41.27% | 0.483 | -64.14% | -11.09 |
| lookback_300 | 300 | 12% | 250 | 32,322 | 21 | 225 | 151 | 63 | 56,185,795.09 | 17.86% | -36.98% | 0.862 | -11.19% | -1.34 |
| stop_10pct | 250 | 10% | 250 | 35,569 | 23 | 253 | 178 | 65 | 28,634,253.10 | 10.53% | -39.07% | 0.601 | -54.74% | -8.66 |
| stop_14pct | 250 | 14% | 250 | 35,569 | 23 | 184 | 104 | 70 | 33,047,478.14 | 12.05% | -39.04% | 0.656 | -47.76% | -7.15 |
| hold_200 | 250 | 12% | 200 | 35,569 | 23 | 234 | 139 | 85 | 64,770,758.87 | 19.46% | -40.06% | 0.893 | 2.38% | 0.27 |
| hold_300 | 250 | 12% | 300 | 35,569 | 23 | 177 | 115 | 53 | 112,309,468.47 | 25.89% | -32.74% | 1.089 | 77.52% | 6.69 |

## Operational gates

| Gate | Result |
|---|---|
| all_prespecified_scenarios_complete | PASS |
| baseline_present | PASS |
| all_nav_positive | PASS |
| pit_unsafe_ca_tickers_quarantined | PASS |
| unsupported_multi_security_terminal_excluded | PASS |

## Interpretation boundary

No scenario is promoted or selected from this table. The purpose is to expose whether nearby settings create materially different behavior. Any later plateau claim must use a declared criterion and must not retrospectively choose the best row.

Ticker 2823 is a declared common-support exclusion for this diagnostic, not a performance-based filter. Source evidence shows last trading 2021-12-17, suspension from 2021-12-20, conversion/delisting 2021-12-30, and consideration of 0.8 shares 2883 + 0.73 shares 2883B + TWD 11.5 cash per old share. Cross-security conversion remains a separate accounting feature to implement.
