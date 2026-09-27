# Research Artifact Policy

AstraQuant distinguishes small permanent evidence from large reproducible artifacts.

## Git-tracked evidence

Prefer Git for:

- manifests
- experiment specs
- validation summaries
- small metrics JSON/CSV
- selected diagnostic figures
- Markdown findings and decisions
- code and configuration

## Retained runtime artifacts

Keep larger AstraQuant-owned outputs under a configured artifact or derived-data root such as data_derived/ or artifacts/.

Examples include canonical PIT datasets, feature matrices, fold assignments, model predictions, transaction-level backtest output, and simulation snapshots.

These outputs are retained but do not need to be committed to Git.

## Invariant

Artifacts produced by AstraQuant must never be written into the external source-data repository.
