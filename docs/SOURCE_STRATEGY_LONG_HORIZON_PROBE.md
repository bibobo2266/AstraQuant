# Source Canonical Strategy Long-Horizon Accounting Probe

Status: **PASS**

Purpose: connect real canonical breakout candidates to the causal RAW portfolio simulator without evaluating strategy performance.

## Integration window

- signal window: 2016-01-04 through 2026-06-30
- post-signal drain sessions requested: 5
- simulation sessions: 2016-01-04 through 2026-07-07
- session count / RAW NAV snapshots: 2,559
- canonical signal candidates supplied: 35,592
- candidate tickers in scoped execution source: 1,551
- PIT-unsafe CA tickers quarantined: 4
- signal rows removed by PIT CA quarantine: 76
- integration-only policy: 10% NAV target, max 10 positions, 12% RAW stop, 20-session re-entry gap, 250-session max hold, 1000-share lot, seed 0

## Accounting/event audit counts

- entries executed: 215
- entry candidates skipped/blocked: 35,377
- RAW stop exits: 140
- RAW max-hold exits: 65
- blocked exit attempts: 19
- supported corporate actions applied: 14,260
- corporate-action cash payments settled: 12,037

## Final accounting state

- open managed positions: 9
- settled cash: 24815005.028909937
- pending receivables: 328865.2688299995
- pending payables: 0.0
- RAW market value: 26552750.0
- NAV: 51696620.29773994

## Gates

| Gate | Result |
|---|---|
| canonical_signals_used | PASS |
| canonical_strategy_simulator_used | PASS |
| entries_executed | PASS |
| raw_nav_snapshots_complete | PASS |
| pending_payables_nonnegative | PASS |
| pending_receivables_nonnegative | PASS |
| settled_cash_nonnegative | PASS |
| no_adjusted_execution_fallback | PASS |
| unsupported_ca_cash_zero | PASS |
| pit_unsafe_ca_tickers_excluded | PASS |

## Performance lock

The numeric NAV/cash values above are accounting state only. No return, CAGR, drawdown, MAR, Sharpe, hit rate, or strategy comparison is computed.

If this smoke fails because a held security cannot be marked from current RAW data, the next task is an explicit RAW stale-mark policy; adjusted prices remain prohibited as a fallback.
