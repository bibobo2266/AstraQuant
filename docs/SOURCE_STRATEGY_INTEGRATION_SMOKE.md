# Source Canonical Strategy Integration Smoke

Status: **PASS**

Purpose: connect real canonical breakout candidates to the causal RAW portfolio simulator without evaluating strategy performance.

## Integration window

- signal window: 2026-01-01 through 2026-03-31
- post-signal drain sessions requested: 2
- simulation sessions: 2026-01-02 through 2026-04-02
- session count / RAW NAV snapshots: 57
- canonical signal candidates supplied: 972
- candidate tickers in scoped execution source: 359
- integration-only policy: 10% NAV target, max 10 positions, 12% RAW stop, 20-session re-entry gap, 250-session max hold, 1000-share lot, seed 0

## Accounting/event audit counts

- entries executed: 26
- entry candidates skipped/blocked: 946
- RAW stop exits: 17
- RAW max-hold exits: 0
- blocked exit attempts: 1
- supported corporate actions applied: 12
- corporate-action cash payments settled: 2

## Final accounting state

- open managed positions: 9
- settled cash: 1154502.0
- pending receivables: 901000.0
- pending payables: 0.0
- RAW market value: 8264050.0
- NAV: 10319552.0

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

## Performance lock

The numeric NAV/cash values above are accounting state only. No return, CAGR, drawdown, MAR, Sharpe, hit rate, or strategy comparison is computed.

If this smoke fails because a held security cannot be marked from current RAW data, the next task is an explicit RAW stale-mark policy; adjusted prices remain prohibited as a fallback.
