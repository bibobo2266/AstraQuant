# PIT / Reference Data Audit

Status: **PASS_WITH_LIMITATIONS**

Scope: structural and temporal-integrity checks for corporate actions, PIT industry, monthly industry snapshots, and tradability.
This audit does not infer unknown dates or backfill missing historical industry classifications.

## Corporate actions ledger

- rows: 41,224
- duplicate canonical keys (stock_id,event_date,event_type,source_name): 0
- null event_date: 0
- null/unknown known_date: 22,665
- known_date later than event_date: 4 (reported, not automatically a failure)
- blank source_name: 0 (reported limitation)

Unknown known_date remains UNKNOWN and must not be guessed. Rows only become PIT-usable when their availability semantics are explicit.

## PIT industry intervals

- rows: 1,990
- IDs: 1,982
- duplicate (stock_id,valid_from): 0
- null valid_from: 0
- invalid valid_to < valid_from: 0
- overlapping intervals: 0
- blank industry: 0

Historical dates before first known industry remain uncovered by design; no backward fill is permitted.

## Industry monthly snapshots

- rows: 252,239
- key-null rows: 0
- duplicate (stock_id,available_date): 0
- blank industry: 0

## Tradability

- rows: 5,236,790
- duplicate (stock_id,date): 0
- key-null rows: 0
- observed_trade=False but buy allowed: 0
- observed_trade=False but sell allowed: 0
- valid_ohlc=False but buy allowed: 0

## Hard gate

Hard failures are duplicate/null temporal keys, overlapping PIT intervals, invalid interval ordering, empty industry labels, or tradability states that allow execution on non-observed/invalid rows.

Corporate-action known_date gaps and late-known events are surfaced as limitations rather than silently repaired.

## Next small task

Audit PIT-bearing fundamental datasets (financials, monthly revenue, margin, dividend) for available_date nulls, ordering, duplicate logical keys, and impossible availability-before-period relationships.
