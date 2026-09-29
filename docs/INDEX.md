# AstraQuant Documentation Index

## Architecture and governance

- `ARCHITECTURE.md` — system spines and boundaries
- `DECISION_LOG.md` — accepted design decisions
- `MASTER_PROGRESS.md` — append-only project tracker
- `NEXT_ACTIONS.md` — current build plan
- `OWNER_PRIORITY_QUEUE.md` — owner-defined mandatory execution order; read before accepting or starting new work
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

- [Corporate-action source semantics clarification](CORPORATE_ACTION_SOURCE_SEMANTICS_CLARIFICATION.md) — verified source-builder meanings, entitlement basis, known/payment-date limitations, and conversion guardrails.

- [Corporate-action source risk addendum](CORPORATE_ACTION_SOURCE_RISK_ADDENDUM.md) — mixed-unit/date/amount risks and required read-only runtime audits before further CA normalization.

- [Three-layer research engine contract](THREE_LAYER_RESEARCH_ENGINE_CONTRACT.md) — config schemas and interfaces for independently swappable universe, signal, and exit layers.

- [Research architecture playbook](RESEARCH_ARCHITECTURE_PLAYBOOK.md) — practical guide to the three-layer engine, reusable components, themes, parameter sweeps, robust-region research, and pool-specific calibration.

- [Research observation catalog](RESEARCH_OBSERVATION_CATALOG.md) — owner-supplied market context, Bollinger/VCP, and Anchor-reversal observations translated into PIT-safe, configurable research components.
