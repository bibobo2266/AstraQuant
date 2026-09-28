# Frozen Canonical Strategy Descriptive Performance Report

Status: **PASS**

This report computes descriptive statistics for the exact audited canonical long-horizon configuration. It is not OOS validation, robustness validation, parameter promotion, or an investment recommendation.

## Frozen configuration

- signal window: 2016-01-04 through 2026-06-30
- simulation/drain horizon: 2016-01-04 through 2026-07-07
- RAW NAV sessions: 2,559
- starting capital: 10,000,000.00
- canonical signals supplied: 35,592
- PIT-unsafe CA tickers quarantined: 4
- signal rows removed by PIT CA quarantine: 76
- policy: 10% NAV target, max 10 positions, 12% RAW stop, 20-session re-entry gap, 250-session max hold, 1000-share lot, seed 0
- execution assumptions: zero explicit fees, zero slippage in this frozen descriptive run

## Descriptive statistics

- final NAV: 51,696,620.30
- total return: 416.97%
- CAGR: 16.93%
- maximum drawdown: -36.42%
- maximum drawdown date: 2025-04-22
- annualized daily volatility (sqrt(252)): 24.05%
- daily Sharpe ratio (rf=0, sqrt(252)): 0.794
- positive-session return rate: 51.76%
- best session return: 6.86%
- worst session return: -9.58%

## Activity/accounting counts

- entries executed: 215
- RAW stop exits: 140
- RAW max-hold exits: 65
- blocked exit attempts: 19
- corporate actions applied: 14,258
- corporate-action cash payments settled: 12,036
- ending pending receivables: 328,865.268830
- ending pending payables: 0.000000

## Reproducibility gates

| Gate | Result |
|---|---|
| same_signal_window_as_long_horizon_probe | PASS |
| same_policy_configuration | PASS |
| raw_nav_series_complete | PASS |
| no_unsupported_ca_cash | PASS |
| pit_unsafe_ca_tickers_excluded | PASS |
| positive_nav_all_sessions | PASS |

## Interpretation boundary

These are in-sample/descriptive statistics for one frozen canonical configuration. They do not establish expected future returns. The next research steps are temporal replication, execution sensitivity, parameter-plateau testing, falsification/placebo work, and then truly locked future OOS evaluation.
