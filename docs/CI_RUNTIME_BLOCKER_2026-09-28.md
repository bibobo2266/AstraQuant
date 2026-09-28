# GitHub Actions Runtime Blocker — 2026-09-28

Status: **RESOLVED_INFRASTRUCTURE**

The P2-058 canonical FIFO reconstruction tests and P2-059 eligible-universe CA coverage audit were initially pushed in commit `b069770c2bcc68ef9de9c47e5d71d3f366ecb6a7`.

## Root cause

AstraQuant had been changed from public to private. GitHub Actions usage on the private repository required billable Actions capacity, while the account spending limit was effectively $0 after account-payment/spending-limit restrictions. GitHub created workflow/job objects but did not start runner steps.

Run `36418298213` exposed the GitHub annotation:

> The job was not started because recent account payments have failed or your spending limit needs to be increased.

This explains the prior empty step lists and missing log blobs.

## Resolution

AstraQuant was changed back to a public repository. `bibobo2266/minervini_picks` remains private and is still treated as immutable source data.

After the repository visibility change, failed runs for commit `b069770c2bcc68ef9de9c47e5d71d3f366ecb6a7` were rerun. The standard `tests` workflow (run `36418298213`, attempt 3) started normally and passed all recorded steps, including the pytest step.

The source-backed eligible-universe CA coverage audit was also rerun separately; its research status is tracked under P2-059 and must be determined from the actual source audit output, not from this infrastructure resolution.

## Evidence boundary

This incident is infrastructure/billing evidence only. It does **not** change any source-data, RAW execution, corporate-action, accounting, signal, placebo, capacity, or performance evidence.

The source repository boundary is unchanged:

- writes are permitted only to `bibobo2266/AstraQuant`;
- `bibobo2266/minervini_picks` remains strictly read-only;
- source checkout keeps `persist-credentials: false`;
- source checkout is made filesystem read-only before source-backed scripts run.

No failed pre-resolution job is interpreted as evidence about strategy correctness or source quality.

## Ubuntu runner reproducibility note

GitHub has announced a future `ubuntu-latest` migration to Ubuntu 26 beginning 2026-10-19. Current evidence-producing workflows should therefore be migrated to an explicitly pinned runner (for example `ubuntu-24.04`) in a separate infrastructure-only change before that migration can alter the runtime environment. This note does not retroactively change any existing evidence.
