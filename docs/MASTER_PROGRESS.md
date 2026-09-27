# Master Progress

This file is the append-only master tracker for AstraQuant.

Allowed statuses: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`, `FAILED`, `REJECTED`, `NEEDS_REVIEW`.

| ID | Phase | Task | Status | Inputs | Output / Finding | Evidence | Decision | Files Changed | Next Step |
|---|---|---|---|---|---|---|---|---|---|
| P0-001 | 0 | Lock repository scope | DONE | User authorization | Only `bibobo2266/AstraQuant` may be modified | Explicit user instruction | ACCEPT | README.md, docs/* | Keep all work isolated here |
| P0-002 | 0 | Initialize governance docs | DONE | Project specification | Core documentation created | Repository files | ACCEPT | docs/* | Bootstrap architecture |
| P0-003 | 0 | Bootstrap package skeleton | DONE | Architecture plan | Minimal PIT, research, portfolio, and test modules created | Repository files and commits | ACCEPT | pyproject.toml, src/*, tests/* | Extend governance components |
| P0-004 | 0 | Establish core invariants | DONE | Architecture rules | PIT availability contract and fill-only position mutation encoded in tests | tests/test_core_invariants.py | ACCEPT | src/astraquant/data/contracts.py, src/astraquant/portfolio/*, tests/test_core_invariants.py | Run tests when runtime is available |
| P0-005 | 0 | Add read-only source boundary | DONE | Data isolation requirement | SourceDataAdapter has read/inspect operations only and blocks path escape | src/astraquant/data/source_adapter.py, tests/test_source_adapter.py | ACCEPT | source_adapter.py, DATA_SOURCE_POLICY.md, tests/test_source_adapter.py | Connect only after source data freeze |
| P0-006 | 0 | Add research governance primitives | DONE | Research OS design | Frozen experiment IDs, trial registry, feature version registry, promotion gates | Source and tests | ACCEPT | research/registry.py, features/registry.py, validation/promotion.py | Add persistence layer later |
| P0-007 | 0 | Add statistical validation primitives | DONE | Validation protocol | Newey-West mean test, BH-FDR, parameter plateau helper | src/astraquant/validation/statistics.py | ACCEPT | validation/statistics.py | Add walk-forward and placebo framework |
| P0-008 | 0 | Add DecisionPacket contract | DONE | Human-in-the-loop architecture | Evidence, constraints, unresolved questions, and human review fields formalized | src/astraquant/decision/models.py | ACCEPT | decision/models.py | Connect to candidate promotion later |
| P0-009 | 0 | Define Complexity Lab | DONE | Complexity governance | Redundancy, complexity curve, ablation, knockout, stability, shadow-model protocol documented | docs/COMPLEXITY_LAB.md | ACCEPT | COMPLEXITY_LAB.md | Implement only after PIT dataset validation |
| P0-010 | 0 | Define validation ladder | DONE | Validation governance | Levels 1–11 and locked OOS rule documented | docs/VALIDATION_LADDER.md | ACCEPT | VALIDATION_LADDER.md | Enforce in experiment results |
| P1-001 | 1 | Build source data inventory | BLOCKED | Cleaned source parquet | User is still cleaning source data; runtime path not connected | User direction | DEFER | — | Resume after user declares data final |
