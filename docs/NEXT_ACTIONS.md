# Next Actions

## NOW

Continue building framework components that do not require source data:

1. compose human approval + generic risk checks into one pre-order gate
2. add immutable review/result persistence format
3. add research-to-decision audit trail IDs across experiment/run/packet/review/intent
4. connect artifact index to run orchestration
5. add package-level facade/API cleanup
6. harden CI based on current workflow results

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
- DecisionPacket contract and builder
- append-only human review history
- explicit human-approval guard before OrderIntent creation
- generic risk-constraint interface
- fill-only position mutation
- order lifecycle
- portfolio fill/cash/settlement orchestration
- execution-assumption interfaces and version registry
- cash and settlement domain
- experiment preregistration
- artifact store and run artifact index
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
