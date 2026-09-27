# Order Lifecycle

AstraQuant separates intent, order state, fills, positions, and settlement.

Lifecycle:

OrderIntent -> Order(CREATED) -> SUBMITTED -> PARTIALLY_FILLED/FILLED -> Position mutation -> Settlement

Orders may also end as CANCELLED or REJECTED.

## Invariants

- OrderIntent does not mutate positions.
- Creating or submitting an Order does not mutate positions.
- Only Fill events mutate Position state.
- A fill must match the order ticker and side.
- Fill quantity cannot exceed remaining order quantity.
- Settlement is separate from fill state and cash availability.

The lifecycle is intentionally generic. Broker-specific and Taiwan-market-specific rules remain outside the core until explicitly frozen.
