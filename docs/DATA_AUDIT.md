# Data Audit

Status: **PHASE 1 COMPLETE — READY_WITH_LIMITATIONS**

Source repository: `bibobo2266/minervini_picks`  
Access mode: **immutable / read only**  
Consumer repository: `bibobo2266/AstraQuant`

## Decision

The source-remediation phase remains frozen. Runtime access, parquet structure, daily-price key integrity, tradability linkage, PIT/reference temporal structure, and PIT-bearing fundamental availability fields have now been checked from AstraQuant's transient GitHub Actions runtime.

This does **not** unlock strategy-performance interpretation. Portfolio retesting remains locked until the execution/accounting coordinate is repaired and its reconciliation gates pass.

## Runtime boundary

AstraQuant GitHub Actions can transiently checkout the private source repository with `MINERVINI_READ_TOKEN`, make the checkout filesystem read-only, read parquet files, and write only small audit outputs back to AstraQuant.

No source parquet is copied into AstraQuant Git.

Evidence: `docs/RUNTIME_SOURCE_PROBE.md`.

## Canonical parquet inventory

Metadata inventory covers 85 parquet files across the canonical source families:

| Family | Files | Metadata row total | Distinct schema hashes |
|---|---:|---:|---:|
| RAW | 12 | 5,905,898 | 1 |
| Adjusted | 13 | 6,279,698 | 3 |
| Reference | 9 | 7,117,398 | 6 |
| Fundamentals | 29 | 23,401,426 | 7 |
| Institutional | 14 | 33,683,482 | 3 |
| KBar | 8 | 21,453,337 | 1 |

These are physical metadata row totals, not deduplicated logical-universe counts.

Evidence: `docs/CANONICAL_PARQUET_INVENTORY.md`.

## Daily price integrity

Yearly RAW and adjusted price files have:

- zero null logical keys;
- zero duplicate `(date, stock_id)` keys;
- zero off-year rows.

RAW price-null/invalid rows exist, but the tradability layer explicitly captures them. Across numeric four-digit stock rows, there are zero missing tradability joins, zero disagreements between independently calculated RAW OHLC validity and `tradability.valid_ohlc`, and zero invalid/null RAW rows incorrectly allowed for buying.

Adjusted-price files contain internally invalid OHLC rows. Classification shows none of those rows are marked valid by tradability. Rows without tradability coverage must be excluded from canonical research construction. Source remediation is not reopened solely for these adjusted rows.

Decision: **RAW execution coordinate structurally usable subject to tradability; adjusted research coordinate requires canonical masking.**

Evidence:

- `docs/RAW_ADJ_QUALITY_AUDIT.md`
- `docs/PRICE_SEMANTICS_VALIDITY_AUDIT.md`
- `docs/ADJ_INVALID_CLASSIFICATION.md`

## PIT and reference integrity

### Industry PIT

The PIT interval table contains 1,990 intervals across 1,982 IDs with:

- zero duplicate `(stock_id, valid_from)`;
- zero null `valid_from`;
- zero invalid interval ranges;
- zero overlapping intervals;
- zero blank industry values.

Historical dates before the first known classification remain uncovered by design. Current industry must never be backfilled into pre-history.

### Monthly industry snapshots

252,239 rows with zero key-null rows, zero duplicate `(stock_id, available_date)`, and zero blank industry values.

### Tradability

5,236,790 rows with zero duplicate `(stock_id, date)` and zero key-null rows. No `observed_trade=False` row is buy/sell allowed, and no `valid_ohlc=False` row is buy allowed.

### Corporate actions

41,224 canonical ledger rows with zero duplicate canonical keys and zero null event dates.

Limitations:

- 22,665 rows have unknown `known_date`;
- 4 rows have `known_date > event_date`;
- unknown dates remain UNKNOWN and are never guessed.

Unknown `known_date` limits PIT use of corporate-action information as a research feature. Economic accounting must still apply the actual effective event semantics rather than adjusted-price inference.

Evidence: `docs/PIT_REFERENCE_AUDIT.md`.

## Fundamental PIT integrity

| Dataset | Rows | Duplicate logical keys | date null | available_date null | Availability rule failures |
|---|---:|---:|---:|---:|---:|
| Financials | 1,408,596 | 0 | 0 | 0 | 0 |
| Monthly revenue | 267,093 | 0 | 0 | 0 | 0 |
| Margin | 4,856,840 | 0 | 0 | 0 | 0 |
| Dividend | 18,557 | 0 | 0 | 0 | 0 |

Known limitations retained:

- financial-statement availability uses statutory-deadline approximations and can be too early for some financial institutions;
- historical financial values may reflect vendor/current revisions instead of the exact originally published figures;
- dividend rows without a usable announcement date may fall back to the event date and are not safe as announcement-timing features without explicit provenance.

Evidence: `docs/FUNDAMENTAL_PIT_AUDIT.md`.

## Frozen readiness classification

| Layer | Phase-1 classification | Required treatment |
|---|---|---|
| RAW market data | READY | execution/accounting coordinate only |
| Adjusted research series | READY_WITH_LIMITATION | signals/features only; mask invalid/non-tradable rows; never execute on ADJ |
| Corporate actions | READY_WITH_LIMITATION | event-aware accounting; unknown PIT dates stay unknown |
| PIT industry | READY_WITH_LIMITATION | exclude uncovered stock-days; no backward fill |
| Tradability | READY_WITH_LIMITATION | enforce block states during execution |
| Financials | READY_WITH_LIMITATION | use available_date; conservative handling for financial institutions and revisions |
| Monthly revenue | READY_WITH_LIMITATION | use available_date |
| Margin | READY_WITH_LIMITATION | T-close information only for T+1-open decisions |
| Dividend research fields | READY_WITH_LIMITATION | announcement provenance required for timing features |
| Institutional / KBar | INVENTORIED | deeper feature-specific PIT semantics deferred until needed |

## Remaining blocker before portfolio retest

The active legacy portfolio backtest still mixes coordinates:

- adjusted entry;
- adjusted stop observation/fill;
- adjusted exit;
- adjusted mark-to-market;
- adjusted cash/P&L;
- reverse-engineered pseudo-RAW for sizing;
- implicit corporate-action treatment.

Therefore performance metrics remain locked.

The next phase is systematic execution-coordinate replacement:

**signal coordinate declared → RAW entry/stop/exit/sizing/mark → tradability gate → explicit CA ledger → cash/receivable/share mutation → NAV reconciliation → only then performance.**
