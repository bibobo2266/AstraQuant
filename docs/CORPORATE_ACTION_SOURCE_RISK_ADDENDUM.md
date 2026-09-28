# Corporate-Action Source Risk Addendum

Date: 2026-09-28

Status: **NEEDS_RUNTIME_AUDIT**

This addendum records newly identified source-semantics risks from a refreshed read-only review of `bibobo2266/minervini_picks`. Source-code facts are separated from claims that still need reproduction against the frozen parquet files.

## Source-code-verified facts

### Mixed construction of `rights_ratio`

For TPEx official `exDailyQ` rows, `fetch_official_corporate_actions.py` sets:

- `cash_per_share` from the TPEx cash field;
- `rights_ratio` from the TPEx stock-distribution field;
- `share_multiplier = 1 + rights_ratio / 1000`.

For FinMind-derived `dividend` rows, `build_corporate_actions_ledger.py` instead writes `rights_ratio` from `StockEarningsDistribution` / `StockDividend` and leaves `share_multiplier` empty.

Therefore `rights_ratio` is not safe to interpret with one universal formula across source types. AstraQuant must branch on source provenance and verified units.

### FinMind-derived event date currently comes from `date`

The source builder currently sets FinMind-derived `event_date` using the row's `date` field. It does not use `CashExDividendTradingDate` or `StockExDividendTradingDate`.

AstraQuant must not assume that this FinMind `event_date` is the authoritative ex-date until a direct frozen-source audit verifies the field semantics.

### TWSE official ex-right/dividend rows are economically incomplete by themselves

The TWSE `TWT49U` path records official ex-right/ex-dividend dates and event identity, but does not populate detailed `cash_per_share`, `share_multiplier`, or `rights_ratio`. The source code notes that detailed cash/share amounts may come from the FinMind dividend row.

AstraQuant therefore must not treat a TWSE official row alone as a complete wealth-accounting event.

### Known-date split by source

Official TWSE/TPEx `ex_right_dividend` rows are currently created without `known_date`.

FinMind-derived `dividend` rows populate `known_date` from `available_date`, falling back to `AnnouncementDate`.

Any future event join must preserve PIT timing and prove event identity before propagating announcement metadata.

## Refreshed-review claims requiring direct parquet audit

The following were reported by a refreshed source review but are not yet independently reproduced by AstraQuant against the frozen parquet files:

1. FinMind `date` has 0% match to `CashExDividendTradingDate` in tested rows and should not be used as ex-date.
2. FinMind `rights_ratio` is expressed in stock-dividend currency units per share and therefore requires a conversion such as `1 + rights_ratio / 10`, not `/1000`.
3. `CashStatutorySurplus` and `StockStatutorySurplus` may contain additional distributable components omitted by the current builder.
4. `CashDividendPaymentDate` is populated for many FinMind rows and may support explicit receivable settlement dates.
5. Official-event rows may be safely enrichable from FinMind rows using stock ID plus authoritative ex-date once the date bug is corrected.

These claims are plausible and materially important, but they remain audit targets until reproduced in AstraQuant's read-only source runtime.

## Accounting risk if left unresolved

Potential silent errors include:

- 10x/100x share-count distortion from unit confusion;
- cash/share accrual on the wrong date;
- incomplete cash or stock distributions;
- incomplete TWSE event economics;
- look-ahead bias if announcement timing is joined incorrectly;
- receivables remaining outstanding despite known payment dates;
- NAV discontinuities without runtime exceptions.

## Required remediation order

1. Audit `date` versus `CashExDividendTradingDate` / `StockExDividendTradingDate`.
2. Audit `rights_ratio` units by source and derive source-specific multiplier formulas.
3. Audit TWSE official rows against FinMind detailed rows for safe one-to-one joins.
4. Audit statutory-surplus cash/stock components.
5. Audit `CashDividendPaymentDate` and announcement metadata for PIT-safe enrichment.
6. Keep rights-subscription economics unsupported until a dedicated source path is verified.

## Repository boundary

Only AstraQuant documentation is changed by this addendum. `bibobo2266/minervini_picks` remains read-only and unchanged.
