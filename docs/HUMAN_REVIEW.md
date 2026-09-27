# Human Review and Execution Guardrail

AstraQuant follows one non-negotiable operating rule:

> System prepares; human decides.

## Review history

Human review is append-only. Each review record stores:

- review ID
- DecisionPacket ID
- reviewer
- decision
- reason
- review timestamp

Allowed decisions are APPROVED, REJECTED, and DEFERRED.

A later review does not erase an earlier review. The complete review history remains available for audit.

## Execution guard

An OrderIntent may be created from a DecisionPacket only when the latest review for that packet is explicitly APPROVED.

No model score, signal, promotion state, confidence value, or research result can bypass this guard.

If the latest review is REJECTED or DEFERRED, or if no review exists, the execution path is blocked.
