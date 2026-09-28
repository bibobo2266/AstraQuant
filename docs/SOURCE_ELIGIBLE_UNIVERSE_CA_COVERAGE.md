# Eligible-Universe Corporate-Action Coverage Audit

Status: **PASS_AUDIT_WITH_BLOCKERS**

Purpose: measure whether the full same-day tradable top-25%-turnover universe can support portfolio-level random/null controls under the canonical RAW/CA accounting path. This audit does not run a placebo portfolio and does not change the signal definition.

## Scope

- signal window: 2016-01-04 through 2026-06-30
- eligible date-ticker pairs: 1,131,215
- distinct eligible tickers: 1,986
- simulation/CA horizon: 2016-01-04 through 2026-07-07

## Normalized dividend CA coverage

- normalized components in eligible ticker scope: 15,566
- known_at missing: 0
- known_at after effective date: 4
- cash components with unknown payment_at: 0

## Non-dividend canonical-ledger timing

- supported non-dividend rows in eligible ticker scope: 479
- known_date missing: 478
- known_date after event_date: 0

## Canonical builder result

- generated instructions: 16,044
- builder unsupported count: 4
- builder unsupported summary: {'normalized_known_after_effective': 4}

Unknown payment dates are not automatically blockers because canonical accounting can retain receivables without guessing settlement. Unknown or post-effective information timing is a PIT issue and must be explicitly quarantined or otherwise source-audited before portfolio-level null controls use those names.

## Operational gates

| Gate | Result |
|---|---|
| eligible_universe_nonempty | PASS |
| ca_builder_completed_for_full_eligible_ticker_scope | PASS |
| instruction_event_ids_unique | PASS |

## Decision boundary

This file is an audit of the expanded null-universe accounting scope. A nonzero unsupported count is adverse/source-blocking evidence, not permission to fall back to adjusted prices or silently omit affected names. Portfolio-level policy/capacity attribution remains locked until the blocker is explicitly accounted for on a common-support basis.

## Post-run PIT interpretation

The four normalized `known_at > effective_date` blockers in the 2016-01-04 through 2026-06-30 research window cross-reference to the normalized-CA audit exceptions:

- 4550 — 2016-09-12 CASH_DIVIDEND, known_at 2016-09-13
- 3234 — 2017-07-19 CASH_DIVIDEND, known_at 2017-07-26
- 5234 — 2019-06-13 CASH_DIVIDEND, known_at 2019-06-14
- 6712 — 2025-04-30 CASH_DIVIDEND, known_at 2025-05-07

These are explicit source/PIT blockers. Any common-support exclusion must name them and apply identically across baseline and controls; they may not be silently removed after observing performance.

The 478 supported non-dividend ledger rows with missing `known_date` are not counted by the current builder as runtime-unsupported because their economic event fields can be applied on the source event/effective date. However, AstraQuant's PIT policy states that unknown availability remains a research limitation. Therefore portfolio-level null/capacity attribution remains locked until a separate policy step explicitly determines whether effective-date-only exogenous accounting is sufficient for this use or whether a common-support restriction is required. No adjusted-price fallback is permitted.
