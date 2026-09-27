# Next Actions

## NOW

Continue building framework components that do not require source data:

1. run orchestration: preregistration -> run manifest -> validation report -> promotion result
2. portfolio orchestration connecting Order fills, Position, Cash, and Settlement without violating fill-only mutation
3. versioned execution-assumption registry
4. research result summary schema for evidence/support/limitations
5. CI hardening after observing the first workflow run
6. package-level API cleanup and documentation index

## COMPLETED DURING DATA-FREEZE PERIOD

- read-only SourceDataAdapter boundary
- feature and experiment registries
- Newey-West / BH-FDR / parameter-plateau primitives
- validation ladder
- walk-forward temporal contracts
- locked future OOS overlap guard
- placebo/permutation hooks
- dataset and run manifests
- explicit validation-result schema
- DecisionPacket
- fill-only position mutation
- cash and settlement domain
- order lifecycle with partial-fill controls
- fee/slippage/execution-assumption interfaces
- validation-to-promotion policy wiring
- experiment preregistration schema
- artifact store conventions
- GitHub Actions pytest workflow
- Complexity Lab protocol

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
