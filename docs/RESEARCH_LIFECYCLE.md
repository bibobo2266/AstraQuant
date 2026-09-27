# Research Lifecycle

AstraQuant keeps protocol, execution, evidence, promotion, and human decision separate.

```text
ExperimentPreregistration
        |
        v
RunManifest
        |
        v
ValidationReport
        |
        v
PromotionPolicy
        |
        v
ResearchResultSummary
        |
        v
DecisionPacket
        |
        v
Human Review
```

## Rules

- A preregistration is frozen before result inspection.
- Every meaningful attempt receives a run/trial identity.
- Validation evidence is explicit; absent evidence is not inferred.
- Promotion is mechanical policy evaluation, not a trading decision.
- A promoted research candidate still requires human review before any OrderIntent.
- Research orchestration itself does not calculate alpha or mutate portfolio state.
