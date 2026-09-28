# Corporate-Action Accounting

AstraQuant now models cash-dividend economics explicitly instead of relying on adjusted-price returns.

## Implemented flow

At the corporate-action effective/ex date:

`shares_entitled × cash_per_share` → dividend receivable

The receivable increases `CashAccount.pending_receivables` and does not immediately increase settled cash.

At the declared payment date:

dividend receivable → settled cash

## Unknown dates

If `payment_at` is unknown, the receivable remains outstanding. AstraQuant does not invent or backfill a payment date.

Likewise, `known_at` may remain unknown in the source record. That limits PIT research use but does not justify guessing the date.

## Guardrails

- cash dividends require a non-negative cash-per-share amount;
- duplicate event IDs cannot accrue twice;
- accrual cannot occur before the effective date;
- payment cannot occur before the declared payment date;
- supported share-multiplier corporate actions use explicit position-share mutations; unsupported security mappings remain unimplemented.

## Remaining corporate-action work

- source-backed stock-dividend/split/reduction replay and reconciliation;
- rights issues;
- capital reductions;
- merger/security mapping;
- integration with the portfolio replay service;
- event-level reconciliation back to the canonical source ledger.


## Share-multiplier events

For a supported non-cash corporate action with an explicit `share_multiplier`:

`new_quantity = old_quantity × share_multiplier`

`new_avg_cost = old_total_cost / new_quantity`

This preserves total historical cost basis across the exogenous share-count mutation.

Examples include official split/par-value-change ratios and capital-reduction replacement-share ratios. The system does not infer a multiplier from adjusted prices.

The same real-world event may legitimately have both a cash component and a share component; those accounting components are tracked separately under the event ID.


## Generic cash entitlements

Corporate actions other than ordinary cash dividends may also carry an explicit cash component, for example a capital-reduction refund.

AstraQuant supports this through an explicit cash-entitlement receivable:

`shares_entitled × cash_per_share → pending receivable`

The caller must declare the economic component (for example `CAPITAL_REDUCTION_REFUND`) and the correct entitlement-share basis. AstraQuant does not infer that basis from adjusted prices.

If the source does not provide a trustworthy payment date, the receivable remains outstanding and cannot be moved to settled cash by guessing a date.


## Opening-position entitlement basis

Some official corporate-action rows combine a cash entitlement with a share-count mutation.

For supported combined events, AstraQuant can declare `OPENING_POSITION` as the entitlement-share basis. The cash receivable is then accrued from the position quantity **before** the same-event share multiplier is applied.

This is required for:

- TPEx `ex_right_dividend` rows whose official source supplies cash per pre-event share and a stock-distribution multiplier; and
- capital-reduction refund rows whose official source supplies refund per pre-reduction share plus a replacement-share ratio.

Accounting order:

`opening shares → cash entitlement → share mutation`

The basis is explicit in the instruction. It is never reverse-engineered from adjusted prices.
