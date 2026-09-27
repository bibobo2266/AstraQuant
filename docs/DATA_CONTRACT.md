# Canonical Data Contract

AstraQuant uses four distinct data layers. They are not interchangeable.

## 1. RAW MARKET DATA

Purpose: execution and economic accounting.

Examples:
- raw OHLC
- raw share volume
- turnover value
- tradability state

Rules:
- entry, stop observation, exit, sizing, affordability, mark-to-market, realized P&L, and cash accounting use RAW.
- if RAW is unavailable at an intended fill, the result is NOT_EXECUTABLE.
- adjusted data must never be used as a fallback execution price.

## 2. ADJUSTED RESEARCH SERIES

Purpose: continuity representation for research.

Examples:
- moving averages
- relative strength
- breakout levels
- trend features
- scale-relative technical features

Rules:
- adjusted series may be used only when the feature declares compatible price semantics.
- provenance and adjustment convention must be explicit where known.
- unknown adjustment semantics must be recorded as a limitation; semantics may not be inferred from a filename.

## 3. CORPORATE ACTION EVENT ENGINE

Purpose: economic continuity.

Event fields should support, when available:
- known_date
- effective_date / ex_date
- record_date
- payment_date
- event_type
- share mutation
- cash or receivable mutation
- security mapping
- source
- reconciliation status

Cash dividends crossing ex-date create a dividend receivable; payment converts receivable to cash. Unknown dates remain UNKNOWN rather than inferred.

Economic P&L is derived from RAW price movement plus share-count mutations, receivable/cash mutations, and security mappings. Adjusted returns are not a substitute for wealth accounting.

## 4. PIT + PROVENANCE

Purpose: prove when and how information was knowable.

Required semantics:
- effective_at
- available_at / known_date
- recorded_at / downloaded_at
- source/provider
- convention
- revision state
- semantic metadata

Backtests may consume a record only when its availability semantics permit it at the simulation time.

## Hard invariants

- EXECUTION asks for ADJ -> HARD FAIL
- RAW missing at intended fill -> NOT_EXECUTABLE
- RAW missing -> never ADJ fallback
- SIGNAL asks for RAW -> allowed only when the feature explicitly declares RAW_REQUIRED
- ADJ provenance unknown -> research may continue only with a declared limitation
- filenames do not define semantics
- adjusted price plus raw share volume is not automatically a coherent economic coordinate

## Feature semantic contract

Every price-dependent feature should eventually declare:

`price_semantics`
- SCALE_INVARIANT
- SCALE_SENSITIVE
- RAW_REQUIRED

`ca_window_requirement`
- CONSISTENT_ADJUSTMENT_WITHIN_LOOKBACK
- EVENT_AWARE
- NONE

Example: ATR divided by price is only scale-invariant when adjustment is consistent across the full lookback window.

## Accounting gate before performance

The first portfolio retest is judged on accounting correctness, not performance.

Required checks:
- entry = RAW
- stop observation = RAW
- exit = RAW
- sizing = RAW
- mark = RAW
- signal source is declared
- share count reconciles
- cash reconciles
- receivables reconcile
- corporate actions reconcile
- NAV reconciles
- no adjusted execution fallback

CAGR, MDD, MAR, Sharpe, and strategy comparisons remain locked until these checks pass.
