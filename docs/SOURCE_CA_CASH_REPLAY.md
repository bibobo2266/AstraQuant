# Source-Backed Cash-Dividend Receivable Replay

Status: **PASS**

Purpose: replay a canonical cash-dividend event on RAW economic coordinates while preserving an unknown payment date.
This is an accounting test, not strategy-performance evidence.

## Source event

- ticker: 2330
- event date: 2026-09-22
- known date: 2026-09-01 00:00:00
- cash per share: 7.00000137
- source: FinMind TaiwanStockDividend
- payment date in canonical ledger: UNKNOWN / unavailable

## Replay

- pre-event RAW entry session: 2026-09-21
- entry RAW open: 2445.0
- post-event RAW mark session: 2026-09-22
- post-event RAW close: 2460.0
- entitled shares: 100.0
- dividend receivable accrued: 700.000137
- settled cash before accrual: 755500.0
- settled cash after accrual: 755500.0
- pending receivables after accrual: 700.000137
- NAV including receivable: 1002200.000137

## Accounting checks

| Gate | Result |
|---|---|
| source_dividend_supported | PASS |
| known_date_present | PASS |
| cash_per_share_positive | PASS |
| raw_entry | PASS |
| raw_post_event_mark | PASS |
| receivable_reconciles | PASS |
| settled_cash_unchanged_on_accrual | PASS |
| nav_includes_receivable | PASS |
| unknown_payment_date_not_guessed | PASS |
| no_adjusted_price_used | PASS |

## Decision

The dividend becomes an economic receivable at the event/effective date. Because the canonical ledger has no payment-date field, the receivable is not converted to settled cash. AstraQuant explicitly rejects a guessed payment.

This is the required behavior until a trustworthy payment date becomes available from a future source layer.
