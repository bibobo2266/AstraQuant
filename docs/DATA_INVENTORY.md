# Data Inventory

Status: INITIAL STATIC INVENTORY — runtime parquet inspection still pending.

Source repository: `bibobo2266/minervini_picks`  
Access policy: READ ONLY. AstraQuant must never modify the source repository.

## Frozen readiness gates

| Dataset / Layer | Status | Evidence / Limitation |
|---|---|---|
| RAW price history | READY | 4,893,591 / 4,893,591 eligible stock-days; 100.0000%; missing 0 |
| Adjusted price history | READY for research coordinate | Used as continuity/research representation; execution use prohibited |
| Corporate actions | READY_WITH_LIMITATION | Historical remediation frozen; reopen only if execution validation reveals a specific missing economic field |
| PIT industry | READY_WITH_LIMITATION | Uncovered stock-days must be excluded rather than backfilled from current industry |
| Tradability | READY_WITH_LIMITATION | Eligible-table coverage 100%; limitation concerns inferred states, not RAW coverage |
| Fundamentals | REMEDIATION COMPLETE | Runtime schema/PIT audit pending |
| Monthly revenue | REMEDIATION COMPLETE | Runtime schema/PIT audit pending |
| Margin | REMEDIATION COMPLETE | Runtime schema/PIT audit pending |
| Dividends | REMEDIATION COMPLETE | Runtime schema/PIT audit pending |
| KBar | REMEDIATION COMPLETE | Runtime schema/PIT audit pending |
| Institutional | REMEDIATION COMPLETE | Runtime schema/PIT audit pending |

## Canonical source families observed

| Family | Source paths | Intended role | Static status |
|---|---|---|---|
| RAW market data | `data/raw/prices_raw_2015.parquet` … `prices_raw_2026.parquet` | execution/accounting coordinate | READY |
| Adjusted research prices | `data/adj/prices_adj_2015.parquet` … `prices_adj_2026.parquet` | signals and continuity features | READY |
| Corporate actions | `data/reference/corporate_actions_ledger.parquet`, `corporate_actions_official.csv`, `corporate_actions_reconciliation.csv`, `data/adj/dividend_events.parquet` | economic event engine and reconciliation | READY_WITH_LIMITATION |
| PIT industry | `data/reference/industry_pit.parquet`, `industry_monthly_snapshots.parquet`, `industry_pit_coverage.csv` | PIT classification | READY_WITH_LIMITATION |
| Tradability | `data/reference/tradability.parquet`, `tradability_coverage.csv` | execution eligibility/state | READY_WITH_LIMITATION |
| Financial statements | `data/fundamentals/financials.parquet`, `balance_sheet.parquet` | structural/fundamental features | REMEDIATION COMPLETE |
| Monthly revenue | `data/fundamentals/month_revenue.parquet` | PIT fundamental features | REMEDIATION COMPLETE |
| Margin | `data/fundamentals/margin.parquet` | market-positioning features | REMEDIATION COMPLETE |
| Market value | `data/fundamentals/market_value_2015.parquet` … `2026.parquet` | size/liquidity context | REMEDIATION COMPLETE |
| Valuation | `data/fundamentals/stock_per_2015.parquet` … `2026.parquet` | valuation features | REMEDIATION COMPLETE |
| Institutional | `data/inst/stock_inst_2015.parquet` … `2026.parquet`, `total_inst.parquet`, `futures_inst.parquet` | flow/positioning features | REMEDIATION COMPLETE |
| KBar | `data/kbar/kbar_2019.parquet` … `2026.parquet`, `_manifest.json` | intraday/minute research or replay | REMEDIATION COMPLETE |

## Static evidence already verified

- Final execution-readiness gate reports RAW history as READY.
- RAW coverage is 100% for every year 2015–2026 under the historical TWSE/TPEx eligibility denominator.
- `raw_history_missing_stockdays.csv` contains no missing stock-days.
- Tradability gate reports READY_WITH_LIMITATION with 100% eligible-stock-day table coverage and zero duplicate `(date, stock_id)` rows.
- PIT industry coverage contains READY, PARTIAL, and one BLOCKED history; uncovered dates are not to be backfilled from present-day classifications.

## Runtime inspection still required

The following cannot be considered verified until AstraQuant has direct read-only parquet access:

- physical row counts
- complete column schemas and dtypes
- min/max dates
- unique ticker counts
- null profiles
- duplicate-key profiles
- timezone/date normalization
- exact availability/known-date fields
- provider/provenance metadata
- cross-file key consistency

Until then, this document is an initial source map rather than the final canonical inventory.

## Runtime representative probe — 2026-09-27

GitHub Actions successfully checked out the private source repository transiently with the fine-grained read-only token and read representative parquet metadata from all ten canonical source families.

Highlights:

- RAW 2026: 421,888 rows; 11 columns; date range 2026-01-02 to 2026-09-24; source field present.
- Adjusted 2026: 488,425 rows; 8 columns; date range 2026-01-02 to 2026-09-24.
- Corporate-action ledger: 41,224 rows; 13 columns; known_date present; source_url/source_name present.
- Tradability: 5,236,790 rows; 20 columns; date range 2015-01-05 to 2026-09-24.
- Financials: 1,408,596 rows; available_date present.
- Monthly revenue: 267,093 rows; available_date present.
- Margin: 4,856,840 rows; available_date present.
- Institutional 2026: 3,728,223 rows.
- KBar 2026: 3,526,949 rows.
- All ten representative files were readable.

Evidence: `docs/RUNTIME_SOURCE_PROBE.md`.

This probe used parquet footer/metadata reads only. Full canonical inventory, null profiles, duplicate-key checks, and cross-file reconciliation remain pending.
