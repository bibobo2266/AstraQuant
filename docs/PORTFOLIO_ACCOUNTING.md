# Portfolio Accounting

## Position invariant

Only `Fill` events mutate positions.

Signals, model scores, recommendations, DecisionPackets, and human approvals do not directly change holdings.

## Cash model

AstraQuant separates:

- `settled_cash`
- `pending_receivables`
- `pending_payables`

`projected_cash` is informative but is not the same thing as settled cash available for use.

## Settlement model

Settlement timing is an explicit domain input. The core engine does not hard-code a market-specific settlement cycle.

A settlement contains:

- settlement ID
- amount
- receivable/payable direction
- due time
- optional originating fill
- actual settlement time

Taiwan-specific settlement rules will be added only after execution assumptions are explicitly frozen.
