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


## Fill preflight atomicity

Before any order, position, cash, or settlement state is mutated, `PortfolioEngine.apply_fill` preflights:

- duplicate fill ID
- duplicate settlement ID
- order existence and fillable status
- ticker/side match
- positive quantity and price
- remaining order quantity
- non-negative fees
- sufficient position quantity for sells
- sell fees not exceeding gross proceeds

Known validation failures therefore occur before mutation. Duplicate fill IDs are rejected globally within the engine instance.

This is not a database transaction, but it closes the previously identified partial-mutation path for the engine's known validation failures.
