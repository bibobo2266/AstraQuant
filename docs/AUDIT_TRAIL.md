# End-to-End Decision Audit Trail

AstraQuant preserves the identity chain from research to execution intent:

experiment_id -> run_id -> dataset_id -> packet_id -> review_id -> intent_id

This makes it possible to answer which research run and dataset produced a DecisionPacket, which human review authorized it, and which OrderIntent resulted.

## Invariant

Missing identifiers are not silently inferred.

The audit trail stops at OrderIntent because later execution objects already carry their own order/fill/settlement identifiers. Those links can be joined to the decision trail without changing the human-approval boundary.
