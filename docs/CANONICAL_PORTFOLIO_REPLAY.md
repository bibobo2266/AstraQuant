# Canonical Portfolio Replay Runner

AstraQuant now has an event-driven portfolio replay runner built on top of the canonical RAW execution service.

## Responsibilities

The runner consumes externally supplied events only. It does not generate strategy signals.

Supported accounting actions:

- execute ENTRY / STOP_FILL / EXIT intents through `CanonicalExecutionService`
- settle pending trade settlements
- accrue cash-dividend receivables
- pay cash dividends only when a declared payment date exists
- apply explicit corporate-action share multipliers
- produce RAW-marked NAV snapshots

## Economic event rule

Trade fills and explicit corporate-action mutations are the only portfolio-state mutation paths.

Research signals, recommendations, DecisionPackets, and human approvals do not directly mutate holdings.

## Integration test

The replay test covers one lifecycle containing:

1. RAW buy fill
2. settlement
3. 2-for-1 share mutation
4. cash-dividend receivable accrual
5. RAW NAV snapshot
6. RAW exit fill
7. settlement
8. final NAV with the still-outstanding dividend receivable

The test verifies share quantity, average cost, settled cash, pending receivables, market value, and NAV identities.

No strategy-performance metric is used as an acceptance criterion.
