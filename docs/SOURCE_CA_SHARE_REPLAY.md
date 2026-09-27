# Source-Backed Corporate-Action Share Replay

Status: **PASS**

Purpose: replay one official share-multiplier event on RAW economic coordinates.
This is an accounting test, not strategy-performance evidence.

## Source event

- ticker: 6949
- source event type: par_value_change_split
- event date: 2026-09-07
- source: TWSE TWTB8U
- share multiplier: 20.0
- known_date: NaT

## Replay window

- pre-event RAW session: 2026-08-26
- post-event RAW session: 2026-09-07
- entry RAW open: 1405.0
- pre-event RAW close mark: 1490.0
- post-event RAW close mark: 67.1

## Share accounting

- quantity before event: 100.0
- average cost before event: 1405.0
- total cost basis before event: 140500.0
- quantity after event: 2000.0
- average cost after event: 70.25
- total cost basis after event: 140500.0

## Accounting checks

| Gate | Result |
|---|---|
| source_event_type_supported | PASS |
| explicit_share_multiplier | PASS |
| raw_entry | PASS |
| raw_pre_event_mark | PASS |
| raw_post_event_mark | PASS |
| quantity_reconciles | PASS |
| cost_basis_reconciles | PASS |
| cash_unchanged_by_share_mutation | PASS |
| no_adjusted_price_used | PASS |

## NAV observations

- pre-event NAV: 1008500.0
- post-event NAV: 993700.0

The difference between pre/post NAV is not used as a pass/fail return metric because the marks are on different trading sessions. The accounting gate checks share and cost-basis identities only.

## Limitation

This replay covers an official par-value/share-split event with an explicit share_multiplier. Cash-dividend payment-date replay remains limited because the canonical source ledger has no payment-date field.
