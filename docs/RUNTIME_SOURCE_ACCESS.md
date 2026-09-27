# Runtime Source Access

## Goal

Verify read-only runtime access from AstraQuant to `../minervini_picks/data` without modifying the immutable source repository.

## Environment

- Observation time (UTC): 2026-09-27T10:21:52.921780+00:00
- Actual working directory: `/workspace/scratch/8f1e1c5d711d`
- AstraQuant working directory: not available / not confirmed
- Expected source repository relative to actual working directory: `/workspace/scratch/minervini_picks`
- Expected source data: `/workspace/scratch/minervini_picks/data`
- These were workspace handoff records, not changes made in an identified AstraQuant checkout

## AR-001 Runtime Paths

Status: **BLOCKED**

| Check | Result | Evidence |
|---|---|---|
| Current working directory | `/workspace/scratch/8f1e1c5d711d` | `pwd` returned this path |
| AstraQuant Git repository | Not confirmed | `git rev-parse --show-toplevel` and `git status --short` reported not a Git repository |
| Source repository | Missing at expected path | `../minervini_picks` not found |
| Source data exists | No at tested path | `../minervini_picks/data` not found |
| Source data readable | Cannot verify | Path absent |
| AstraQuant `data_derived/` writable | Unverified | AstraQuant checkout unavailable |

No broad filesystem search was performed.

## AR-002 Read-Only Verification

Status: **BLOCKED**

Not executed because AR-001 did not pass.

## AR-003 Representative Parquet Probe

Status: **BLOCKED**

Not executed because AR-001 and AR-002 did not pass.

## Findings

This Astra runtime did not contain the intended AstraQuant checkout or sibling source-data mount. This is an environment/mount blocker, not a data-quality failure.

## Limitations

- source read access remains unverified in Astra runtime
- derived-output write access remains unverified in Astra runtime
- no parquet probe was performed
- no source file was modified

## Exact Next Recommended Task

Launch Astra in an environment where:

- AstraQuant is a writable Git checkout
- `minervini_picks` is available as a sibling checkout or mount
- `minervini_picks/data` is read-only
- the task starts from the AstraQuant repository root

Then rerun AR-001 only. Continue to AR-002 and AR-003 only if AR-001 passes.
