# Astra Task: Verify Read-Only Source Runtime Access

## Goal

Verify that the Astra/local runtime can read the frozen external source data at `../minervini_picks/data` without modifying `minervini_picks`.

This is a small-task protocol. Do not attempt the full data audit in one run.

## Non-negotiable rules

- NEVER write, edit, delete, rename, commit, or otherwise modify anything under `minervini_picks`.
- AstraQuant is the only writable project.
- Do not copy the source parquet dataset into AstraQuant Git.
- Derived outputs may go under AstraQuant `data_derived/`.
- Important findings must be written to Markdown immediately.
- After every completed subtask, append a row to `docs/MASTER_PROGRESS.md`.
- Do not wait until the whole job is finished to save results.

## Subtasks

### AR-001 — Resolve runtime paths

Confirm:
- AstraQuant working directory
- source repo path
- whether `../minervini_picks/data` exists
- whether it is readable
- whether AstraQuant can create files in its own `data_derived/`

Record the result in:
- `docs/RUNTIME_SOURCE_ACCESS.md`
- `docs/MASTER_PROGRESS.md`

Stop if the source path is not readable.

### AR-002 — Prove read-only behavior

Without changing source files:
- stat/list representative source directories
- read metadata from one small representative source file or parquet footer if practical
- do not rewrite or touch timestamps/content
- record how read-only safety is enforced operationally

Update:
- `docs/RUNTIME_SOURCE_ACCESS.md`
- `docs/MASTER_PROGRESS.md`

### AR-003 — Minimal representative parquet probe

Only after AR-001 and AR-002 pass, inspect one representative file from each available family, using metadata/footer reads where possible:

- RAW market data
- adjusted research prices
- corporate actions/reference
- PIT industry
- tradability
- fundamentals
- monthly revenue
- margin
- institutional
- KBar

For each representative file record:
- path
- readable yes/no
- physical size
- schema/columns
- row count if inexpensive
- min/max date if inexpensive
- suspected key fields
- availability/known-date fields if present
- notes/limitations

Write results to:
- `docs/RUNTIME_SOURCE_ACCESS.md`
- `docs/DATA_INVENTORY.md`
- `docs/MASTER_PROGRESS.md`

## Stop condition

Stop after AR-003. Do NOT run a full multi-million-row audit, build features, run backtests, or modify source data.

## Required final report

At completion, summarize only:
- AR-001 status
- AR-002 status
- AR-003 status
- files changed in AstraQuant
- blockers
- exact next recommended small task

Every DONE status must cite an evidence path.
