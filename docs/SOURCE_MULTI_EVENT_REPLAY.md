# Source-Backed Multi-Event Canonical Replay

Status: **PASS**

Purpose: prove one continuous canonical replay can process multiple real source events and trade lifecycles without adjusted execution prices.
This is an accounting/integration test, not strategy-performance evidence.

## Split leg

- ticker: 6949
- event date: 2026-09-07
- share multiplier: 20.0
- source: TWSE TWTB8U
- entry session: 2026-08-26 at RAW open 1405.0
- quantity before event: 100.0
- quantity after event: 2000.0
- exit session: 2026-09-07 at RAW close 67.1

## Cash-dividend leg

- ticker: 2330
- event date: 2026-09-22
- known date: 2026-09-01 00:00:00
- cash per share: 7.00000137
- source: FinMind TaiwanStockDividend
- entry session: 2026-09-21 at RAW open 2445.0
- receivable accrued: 700.000137
- event-day RAW close mark: 2460.0
- exit session: 2026-09-22 at RAW close 2460.0

## Gates

| Gate | Result |
|---|---|
| signal_declared | PASS |
| split_entry_raw | PASS |
| split_quantity_reconciles | PASS |
| split_exit_raw | PASS |
| split_position_flat | PASS |
| dividend_entry_raw | PASS |
| dividend_receivable_reconciles | PASS |
| dividend_exit_raw | PASS |
| dividend_position_flat | PASS |
| pending_payables_zero | PASS |
| outstanding_receivable_retained | PASS |
| final_market_value_zero | PASS |
| canonical_runner_path_used | PASS |
| no_adjusted_price_used | PASS |

## Final accounting state

- settled cash: 4995200.0
- pending receivables: 700.0001369999954
- pending payables: 0.0
- final RAW market value: 0.0
- final NAV: 4995900.000137

The remaining receivable is intentional because the canonical source ledger has no payment-date field. AstraQuant does not guess the payment date.
