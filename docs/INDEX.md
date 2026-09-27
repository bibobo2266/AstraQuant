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
- `PORTFOLIO_ACCOUNTING.md` — positions, cash, settlement
- `ARTIFACTS.md` — retained outputs and Git policy

## Data-dependent work

Actual inventory, data audit, PIT reconciliation, factor calculation, backtests, and ML remain blocked until the source dataset is declared final.

## Audit and persistence

- `AUDIT_TRAIL.md` — research-to-order-intent identity chain
- `PERSISTENCE.md` — append-only governance persistence conventions
