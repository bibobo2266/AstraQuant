# NAV Reconciliation

AstraQuant portfolio valuation now requires RAW mark decisions for every open position.

## Formula

`NAV = settled_cash + pending_receivables - pending_payables + RAW market value`

where:

`RAW market value = sum(position_quantity × RAW mark)`

## Hard failures

Valuation fails when:

- an open position has no RAW mark decision;
- the mark decision is not a `MARK` use;
- the RAW mark is non-executable / unavailable;
- the RAW mark is missing or non-positive;
- the mark ticker does not match the position.

Adjusted prices are not accepted as a valuation fallback.

## Corporate-action interaction

Cash-dividend receivables are already included through `pending_receivables`. When a declared dividend payment is made, the same amount moves from pending receivable to settled cash, leaving NAV unchanged by the transfer itself.

## Scope

This component validates the accounting identity for current shares/cash/receivables/payables. Non-cash corporate-action share mutations and security mappings are still pending.
