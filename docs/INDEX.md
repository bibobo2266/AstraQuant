# AstraQuant Documentation Index

## Architecture and governance

- `ARCHITECTURE.md` — system spines and boundaries
- `DECISION_LOG.md` — accepted design decisions
- `MASTER_PROGRESS.md` — append-only project tracker
- `NEXT_ACTIONS.md` — current build plan
- `DATA_SOURCE_POLICY.md` — immutable external-source boundary

## Research and validation

- `EXPERIMENT_PREREGISTRATION.md` — freeze protocols before seeing results
- `LINEAGE.md` — dataset/run provenance
- `VALIDATION_LADDER.md` — evidence levels 1–11
- `COMPLEXITY_LAB.md` — complexity and black-box challenge protocol
- `RESEARCH_LIFECYCLE.md` — preregistration through human review
- `HUMAN_REVIEW.md` — append-only review history and approval guardrail
- `RISK_CONSTRAINTS.md` — generic risk-check architecture

## Execution and portfolio

- `ORDER_LIFECYCLE.md` — intent/order/fill state model
- `EXECUTION_ASSUMPTIONS.md` — fee/slippage/execution contracts
- `EXECUTION_MARKET_DATA.md` — RAW-only execution data access and tradability enforcement
- `PRICE_COORDINATES.md` — hard RAW/adjusted coordinate boundary
- `PORTFOLIO_ACCOUNTING.md` — positions, cash, settlement
- `ARTIFACTS.md` — retained outputs and Git policy

## Data phase

- `DATA_PHASE_PLAN.md` — small-task plan for inventory, execution semantics, and canonical PIT work
- `DATA_INVENTORY.md` — frozen source readiness and initial static source map
- `DATA_CONTRACT.md` — canonical RAW / adjusted / corporate-action / PIT-provenance contract
- `DATA_AUDIT.md` — frozen Phase-1 audit summary, limitations, and remaining execution blocker
- `CANONICAL_PARQUET_INVENTORY.md` — runtime parquet metadata inventory
- `RAW_ADJ_QUALITY_AUDIT.md` — RAW/adjusted key and duplicate checks
- `PIT_REFERENCE_AUDIT.md` — corporate-action, industry PIT, snapshot, and tradability integrity
- `FUNDAMENTAL_PIT_AUDIT.md` — PIT-bearing fundamental availability checks

Phase-1 runtime/data audit is complete with explicit limitations. Phase-2 execution/accounting repair is active. Performance research remains gated.

## Audit and persistence

- `AUDIT_TRAIL.md` — research-to-order-intent identity chain
- `PERSISTENCE.md` — append-only governance persistence conventions
