# Fixed-Trade-Path Execution-Cost Attribution

Status: **PASS**

Purpose: isolate pure execution-cost drag by freezing the exact zero-friction baseline fill path. Unlike the full execution-sensitivity reruns, this attribution does not allow fees/slippage to alter sizing, capacity, entry selection, stops, or holding paths.

## Frozen path

- signal window: 2016-01-04 through 2026-06-30
- simulation/drain horizon: 2016-01-04 through 2026-07-07
- RAW NAV sessions: 2,559
- baseline fills frozen: 420
- baseline entries: 215
- baseline RAW stop exits: 140
- baseline max-hold exits: 65

## Fixed-path cost attribution

| Scenario | Fee bps/fill | Slippage bps/fill | Slippage drag | Fee drag | Total cost drag | Final NAV | Total return | CAGR | Max DD | Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline_0_0 | 0 | 0 | 0.00 | 0.00 | 0.00 | 51,696,620.30 | 416.97% | 16.93% | -36.42% | 0.794 |
| stress_10_10 | 10 | 10 | 831,296.12 | 831,289.53 | 1,662,585.65 | 50,034,034.64 | 400.34% | 16.56% | -38.22% | 0.767 |
| stress_25_25 | 25 | 25 | 2,078,240.31 | 2,078,199.08 | 4,156,439.40 | 47,540,180.90 | 375.40% | 16.00% | -41.09% | 0.727 |
| stress_50_50 | 50 | 50 | 4,156,480.62 | 4,156,315.71 | 8,312,796.34 | 43,383,823.96 | 333.84% | 14.99% | -46.35% | 0.662 |

## Gates

| Gate | Result |
|---|---|
| baseline_fill_path_frozen | PASS |
| all_scenarios_same_nav_sessions | PASS |
| cost_drag_monotonic | PASS |
| final_nav_monotonic_nonincreasing | PASS |
| pit_unsafe_ca_tickers_excluded | PASS |

## Interpretation boundary

This is a mechanical attribution on a frozen trade path. It answers how much the observed baseline path would lose to explicit cost assumptions. It is not a fully executable counterfactual because higher costs could change cash availability and future decisions. The separate full reruns capture that endogenous path dependence.
