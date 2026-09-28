# Source Corporate-Action Calendar Audit

Status: **PASS_WITH_HORIZON_LIMITS**

Purpose: verify how canonical corporate-action effective dates map onto the RAW trading-session calendar without ever moving an economic event backward.

## RAW calendar

- first RAW session: 2015-01-05
- last RAW session: 2026-09-24
- unique RAW sessions: 2,859

## Corporate-action dates

- ledger rows: 41,224
- null event_date: 0
- rows before RAW calendar horizon: 1,169
- rows after RAW calendar horizon: 35
- rows inside RAW calendar horizon: 40,020
- on-session event dates: 34,422
- non-session event dates: 5,598
- mapping failures inside horizon: 0
- backward mappings: 0

## Non-session forward-mapping gaps

| Calendar-day gap to first trading session | Events |
|---:|---:|
| 1 | 3,080 |
| 2 | 2,192 |
| 3 | 242 |
| 4 | 53 |
| 5 | 11 |
| 7 | 3 |
| 8 | 9 |
| 9 | 4 |
| 10 | 3 |
| 12 | 1 |

## Non-session event types

| Event type | Events |
|---|---:|
| dividend | 5,410 |
| ex_right_dividend | 183 |
| capital_reduction | 5 |

## Canonical policy

- If economic effective date is a trading session: apply before that session's trading.
- If economic effective date is not a trading session: apply before the first trading session after the effective date.
- Never map an event to a prior trading session.
- If no later session exists inside the configured simulation calendar: hard-fail / extend the calendar; do not guess.
- known_date, record date, and payment date remain separate concepts and are not substituted for the economic effective date.

## Horizon treatment

Rows before or after the available RAW calendar are reported separately and are not remapped into the observed horizon.

## Result

The calendar gate passes only if every in-horizon event has a deterministic same-session/forward mapping and no event maps backward.
