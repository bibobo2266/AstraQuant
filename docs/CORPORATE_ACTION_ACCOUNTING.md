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
- non-cash corporate actions are represented in the event type enum but their share/security mutations are not implemented yet.

## Remaining corporate-action work

- stock dividends / splits and share-count reconciliation;
- rights issues;
- capital reductions;
- merger/security mapping;
- integration with the portfolio replay service;
- event-level reconciliation back to the canonical source ledger.
