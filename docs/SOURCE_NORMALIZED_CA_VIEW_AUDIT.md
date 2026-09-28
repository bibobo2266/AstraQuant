# Source Normalized Corporate-Action View Audit

Status: **PASS_WITH_JOIN_LIMITATIONS**

Purpose: validate the AstraQuant-side normalized FinMind cash/stock dividend view against the frozen read-only source before integrating it into strategy/accounting replay.

## Normalized view

- normalized component rows: 19,406
- cash-dividend components: 17,039
- stock-dividend components: 2,367
- unique stock IDs: 1,721
- logical duplicate rows (stock/effective-date/kind): 0
- logical duplicate groups: 0
- nonpositive cash components: 0
- invalid stock multipliers (<= 1): 0

## PIT/payment fields

- components with known_at: 19,406
- known_at after effective date: 7
- cash components with payment_at: 16,674
- payment_at before effective date: 0

## Official-date linkage (date identity only; not yet an economic merge)

- TWSE official ex_right_dividend rows: 11,804
- TWSE rows with >=1 normalized FinMind component on same stock/ex-date: 9,197
- TPEx official ex_right_dividend rows: 10,293
- TPEx rows with >=1 normalized FinMind component on same stock/ex-date: 6,566

## Semantics

- Cash uses CashExDividendTradingDate and opening/pre-event share entitlement.
- Stock uses StockExDividendTradingDate and FinMind currency-per-share conversion to share_multiplier.
- CashEarningsDistribution and CashStatutorySurplus are additive when present.
- StockEarningsDistribution and StockStatutorySurplus are additive when present.
- Payment dates come from CashDividendPaymentDate; no guessed settlement date is introduced.
- Official-event linkage above is diagnostic only. It does not silently replace or merge source rows.

## Gate

The view is eligible for the next integration step only if logical keys are unique, economic values are valid, and no payment precedes its effective date. Date-join misses remain explicit source limitations rather than guessed matches.
