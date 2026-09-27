# Canonical Stop and Cash-Commitment Semantics

## RAW stop handling

Long-position sell stops use RAW OHLC only.

A stop is observed when the session RAW low touches or breaches the stop level.

Fill reference:

- if RAW open is at or below the stop, use RAW open (gap-through-stop case);
- otherwise use the explicit stop level inside the observed RAW bar.

Sell-side tradability is enforced before a stop fill may be created.

If the RAW low never reaches the stop, the result is `STOP_NOT_TRIGGERED` and no Fill is created.

## Cash commitment

A new buy may not commit cash already reserved for pending payables.

`available_to_commit_cash = max(0, settled_cash - pending_payables)`

Pending receivables do not count as available cash until they actually settle.

CanonicalExecutionService calculates the actual fill notional plus fees before creating an order. If required cash exceeds available-to-commit cash, execution fails before order/position/cash state mutation.

## Purpose

These rules remove two legacy ambiguities before portfolio-policy migration:

- stop trigger/fill is no longer based on adjusted lows/opens;
- multiple unsettled buys cannot silently overcommit the same settled cash.
