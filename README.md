# AstraQuant

**AstraQuant** is a clean-room, human-in-the-loop investment research and validation operating system.

> System prepares; human decides.

## Scope

This repository is intentionally isolated from other projects. It is designed to:

- ingest source market data through read-only adapters
- audit data quality and point-in-time semantics
- register versioned features and experiments
- account for every research trial
- validate signals with time-respecting methods
- study indicator redundancy and ML black-box behavior
- separate research signals from portfolio state
- prepare evidence-backed decision packets for human review

## Core spines

```text
Data:
Source → Audit → Canonical PIT Dataset → Feature Registry

Research:
Hypothesis → Frozen Experiment → Trial Registry → Validation → Candidate

Decision:
Evidence → Thesis → DecisionPacket → Human Review → Outcome → Feedback

Execution:
Decision → OrderIntent → Order → Fill → Position → Settlement
```

### Hard invariant

Signals, recommendations, and human decisions do **not** directly mutate positions.

Only fills change position state.

## Current phase

**Phase 0 — Governance and architecture bootstrap**

No strategy claims have been made and no source data has been modified.
