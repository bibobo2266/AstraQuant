# Corporate-Action Source Profile

Status: **DONE — semantic inventory**

Purpose: profile the frozen canonical corporate-action ledger before implementing non-cash mutations or source-backed CA replay.

- rows: 41,224
- unique stock IDs: 2,353
- event_date null: 0
- known_date null: 22,665
- known_date > event_date: 4
- payment-date-like columns present: NONE
- record-date-like columns present: NONE

## Event-type field coverage

| Event type | Rows | IDs | known_date populated | cash/share | share multiplier | rights ratio | subscription price |
|---|---:|---:|---:|---:|---:|---:|---:|
| ex_right_dividend | 22,097 | 2,291 | 0 | 10,293 | 10,293 | 10,293 | 0 |
| dividend | 18,557 | 1,775 | 18,557 | 18,557 | 0 | 18,557 | 0 |
| capital_reduction | 544 | 393 | 0 | 238 | 238 | 0 | 0 |
| par_value_change_split | 24 | 22 | 0 | 0 | 24 | 0 | 0 |
| capital_reduction_deficit | 2 | 2 | 2 | 0 | 2 | 0 | 0 |

## Accounting implications

- The ledger can support event-date/economic-event replay only for fields actually populated by event type.
- Unknown known_date remains a PIT limitation and is never inferred.
- If no payment-date field exists, a cash-dividend source replay can accrue a receivable at the effective/ex date but cannot move it to settled cash on a guessed payment date.
- Non-cash share mutations must be implemented only for event types with explicit, interpretable share-mutation fields.
- Event types with insufficient economic fields remain accounting-limited rather than reverse-engineered from adjusted prices.

## Next small task

Implement generic share-multiplier mutation with explicit corporate-action provenance, then source-test only event types whose ledger fields support that mutation.
