# Architecture

## Design principle

AstraQuant separates data, research, decisions, and execution so that research results cannot silently become portfolio state.

## Data spine

```text
Read-only Source Data
→ Data Audit
→ Canonical Normalization
→ Point-in-Time Join
→ Feature Registry
```

## Research spine

```text
Hypothesis
→ ExperimentSpec
→ Frozen Protocol
→ Trial Registry
→ Validation
→ Candidate
→ Promotion Gate
```

## Decision spine

```text
Evidence
→ Thesis
→ DecisionPacket
→ Human Review
→ Outcome
→ Feedback
```

## Execution spine

```text
Human-approved Decision
→ OrderIntent
→ Order
→ Fill
→ Position
→ Settlement
```

## Complexity Lab

The Complexity Lab exists to test whether model complexity earns its place.

Planned controls include:

- feature-family clustering
- redundancy analysis
- complexity curves
- family ablation
- feature knockout tests
- noise injection
- shadow models
- disagreement analysis
- feature-rank stability
- SHAP/family-importance stability
- regime personality drift

A more complex model is not preferred unless it demonstrates stable incremental out-of-sample value.

## Point-in-time rule

For information-bearing records:

- `effective_at`: period the information describes
- `available_at`: earliest time the system could legitimately know it
- `recorded_at`: when the system recorded it

Backtests may only consume records satisfying:

```text
available_at <= simulation_time
```
