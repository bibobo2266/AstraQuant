# Master Progress

This file is the append-only master tracker for AstraQuant.

Allowed statuses: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`, `FAILED`, `REJECTED`, `NEEDS_REVIEW`.

| ID | Phase | Task | Status | Inputs | Output / Finding | Evidence | Decision | Files Changed | Next Step |
|---|---|---|---|---|---|---|---|---|---|
| P0-001 | 0 | Lock repository scope | DONE | User authorization | Only `bibobo2266/AstraQuant` may be modified | Explicit user instruction | ACCEPT | README.md, docs/* | Keep all work isolated here |
| P0-002 | 0 | Initialize governance docs | DONE | Project specification | Core documentation created | Repository files | ACCEPT | docs/* | Bootstrap architecture |
| P0-003 | 0 | Bootstrap package skeleton | DONE | Architecture plan | Minimal PIT, research, portfolio, and test modules created | Repository files and commits | ACCEPT | pyproject.toml, src/*, tests/* | Add data inventory tooling |
| P0-004 | 0 | Establish core invariants | DONE | Architecture rules | PIT availability contract and fill-only position mutation encoded in tests | tests/test_core_invariants.py | ACCEPT | src/astraquant/data/contracts.py, src/astraquant/portfolio/*, tests/test_core_invariants.py | Run tests when CI/runtime is available |
| P1-001 | 1 | Build source data inventory | TODO | Repo data paths | Not started | — | — | — | Add inventory tooling and connect data |
