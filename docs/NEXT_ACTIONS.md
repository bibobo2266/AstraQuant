# Next Actions

## NOW

The data-remediation layer is frozen. Continue in small, recoverable tasks:

1. verify Astra/local runtime can read the external source root without write access
2. run parquet-level inventory: schemas, rows, dates, tickers, nulls, duplicates, PIT fields
3. freeze the canonical inventory
4. begin Execution Semantics Validation
5. audit active workflows/scripts and trace all signal/execution/accounting price sources
6. enforce the canonical RAW/ADJ/CA/PIT contract before any portfolio-performance retest

## CURRENT GATE

- RAW history: READY, 100.0000% eligible coverage
- Adjusted history: READY for research coordinate
- Corporate actions: READY_WITH_LIMITATION
- PIT industry: READY_WITH_LIMITATION; uncovered periods remain excluded
- Tradability: READY_WITH_LIMITATION
- source repository remains immutable/read-only

## PERFORMANCE LOCK

Do not use CAGR, Sharpe, MAR, MDD, or strategy ranking as acceptance criteria until:

- entry/stop/exit/sizing/mark all use RAW
- no adjusted execution fallback exists
- share count reconciles
- cash and receivables reconcile
- corporate actions reconcile
- NAV reconciles
- signal source semantics are declared

## RESEARCH AFTER DATA/ACCOUNTING GATES

1. construct canonical PIT dataset
2. materialize feature registry
3. preregister EXP-R001
4. run EXP-R001 only after all required gates pass
5. proceed to EXP-R002 / Complexity Lab only through the promotion protocol
