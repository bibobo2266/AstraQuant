# Next Actions

## NOW

Continue building framework components that do not require source data:

1. time-respecting walk-forward split contracts
2. placebo / permutation validation hooks
3. dataset and run manifest models
4. validation result schema and ladder enforcement
5. portfolio cash and settlement domain

## BLOCKED UNTIL DATA FREEZE

- actual source inventory
- schema/null/duplicate audit
- corporate-action reconciliation
- point-in-time financial audit
- canonical research dataset
- feature calculation
- backtests
- ML training
- strategy recommendations

The source repository must remain untouched. It may later be exposed to AstraQuant as a read-only checkout or mount.

## AFTER DATA FREEZE

1. connect SourceDataAdapter to the cleaned source-data root
2. execute Phase 1 inventory
3. execute Phase 2 data audit
4. validate corporate actions and PIT semantics
5. construct canonical research dataset
6. begin EXP-R001 only after data gates pass
