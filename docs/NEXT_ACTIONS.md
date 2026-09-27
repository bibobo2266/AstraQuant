# Next Actions

## NOW

Continue building framework components that do not require source data:

1. DecisionPacket builder from ResearchResultSummary + portfolio/risk context
2. human review record and immutable review history
3. order-intent guard that requires explicit human approval before execution path
4. generic risk-constraint interfaces without strategy-specific thresholds
5. artifact indexing for run outputs
6. CI hardening after workflow results are available

## COMPLETED DURING DATA-FREEZE PERIOD

- read-only SourceDataAdapter boundary
- feature and experiment registries
- Newey-West / BH-FDR / parameter-plateau primitives
- validation ladder and promotion policy
- walk-forward temporal contracts and locked-OOS guard
- placebo/permutation hooks
- dataset/run manifests
- research run orchestration
- research result summary schema
- DecisionPacket contract
- fill-only position mutation
- order lifecycle
- portfolio fill/cash/settlement orchestration
- execution-assumption interfaces and version registry
- cash and settlement domain
- experiment preregistration
- artifact store conventions
- documentation index
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
