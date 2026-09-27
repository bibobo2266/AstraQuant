# Data Phase Plan

The source-data remediation layer is now frozen. AstraQuant will treat `bibobo2266/minervini_picks` as an immutable read-only source and will not modify it.

## Working rule

This phase is intentionally broken into small, recoverable tasks. Each completed task must update its Markdown evidence and append a row to `docs/MASTER_PROGRESS.md`.

## Phase 1 — Inventory and contracts

- P1-002: record the frozen source-readiness gates
- P1-003: inventory canonical source families and paths
- P1-004: define the four-layer data contract
- P1-005: verify AstraQuant runtime can mount/read the external source root
- P1-006: inspect schemas, row counts, date ranges, nulls, duplicates, and ticker coverage in runtime
- P1-007: freeze the canonical inventory after runtime verification

## Phase 2 — Execution semantics validation

- P2-001: inventory active workflows and scripts
- P2-002: trace signal price sources
- P2-003: trace entry/stop/exit price sources
- P2-004: trace position sizing and affordability sources
- P2-005: trace mark-to-market and P&L sources
- P2-006: trace corporate-action dependencies
- P2-007: produce RAW/ADJ violation list
- P2-008: enforce no adjusted-price execution fallback
- P2-009: define feature price semantics and CA lookback requirements
- P2-010: define accounting reconciliation invariants
- P2-011: run dry-run execution validation
- P2-012: allow portfolio retest only after accounting gates pass

## Phase 3 — Canonical PIT dataset

Starts only after Phase 1 and Phase 2 gates pass.

## Research gate

CAGR, Sharpe, MAR, MDD, model comparisons, and strategy promotion remain locked until accounting correctness and PIT/data semantics pass.
