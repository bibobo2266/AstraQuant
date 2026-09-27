# Next Actions

## NOW

Continue building framework components that do not require source data:

1. add additional generic risk constraints: cash, position size, concentration interfaces
2. extend audit links from OrderIntent to Order/Fill/Settlement
3. connect artifact index and persistence to research orchestration outputs
4. add a top-level AstraQuant service/facade to compose research, decision, review, risk, and portfolio flows
5. harden CI and fix any failing tests on current head
6. keep all data-dependent work blocked until the source dataset is declared final

## COMPLETED DURING DATA-FREEZE PERIOD

- immutable source boundary and SourceDataAdapter
- PIT/data contracts
- feature, experiment, and execution-assumption registries
- validation statistics, ladder, walk-forward, falsification, and promotion policy
- preregistration, run lineage, research orchestration, and result summaries
- DecisionPacket builder and stable packet IDs
- append-only human review history
- combined human-approval + risk pre-order gate
- end-to-end experiment/run/dataset/packet/review/intent audit chain
- append-only JSONL governance persistence
- generic risk-constraint framework
- order/fill/position/cash/settlement domain
- artifact store and index
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
