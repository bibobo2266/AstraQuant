# Source-Backed Accounting Smoke Replay

Status: **PASS**

Purpose: exercise the accounting-only replay against real frozen RAW/tradability source data.
This is not a strategy backtest and no performance metric is used as an acceptance criterion.

## Selected source window

- ticker: 2330
- entry session: 2026-09-22
- mark/stop-observation session: 2026-09-23
- exit session: 2026-09-24
- quantity: 100

## RAW decisions

- sizing RAW open: 2505.0
- entry RAW open: 2505.0
- stop observation RAW low: 2475.0
- mark RAW close: 2500.0
- exit RAW close: 2475.0

## Accounting gates

| Gate | Result |
|---|---|
| signal_source_declared | PASS |
| sizing_raw | PASS |
| entry_raw | PASS |
| stop_observation_raw | PASS |
| exit_raw | PASS |
| mark_raw | PASS |
| share_count_reconciles | PASS |
| cash_reconciles | PASS |
| receivables_reconcile | PASS |
| nav_reconciles | PASS |
| no_adjusted_execution_fallback | PASS |

## Accounting state

- opening cash: 1000000.0
- pre-exit RAW market value: 250000.0
- pre-exit NAV: 999500.0
- final settled cash after exit settlement: 997000.0

These values are retained only to prove accounting identity. They are not strategy-performance evidence.

## Scope limitation

This source smoke window intentionally tests a plain trade lifecycle. Corporate-action replay remains a separate gate.
