# Full-Universe CA/PIT Common-Support Policy

Status: **FROZEN**

Purpose: freeze the corporate-action PIT common-support exclusion set before any deterministic policy/capacity attribution is run. This is a source-governance decision, not a strategy parameter and not a result-driven filter.

## Frozen rule

1. Preserve corporate actions on their economic effective-date coordinate; do not move an economic share/cash mutation to a later information date because doing so would distort interim RAW wealth accounting.
2. A normalized dividend component whose known_at is later than its effective date is PIT-unsafe for this attribution universe.
3. A capital_reduction or par_value_change_split row with missing known_date is PIT-unsafe because it changes share quantity and its information availability cannot be proven from the canonical source.
4. Derive one ticker exclusion set from the event-level ledger below and remove that same set from baseline breakout candidates and every matched/control/deterministic-capacity rule before simulation.
5. The exclusion set is frozen before attribution. It may not be changed in response to attribution performance. A newly discovered source blocker invalidates the run and requires a new audited policy version.
6. No adjusted-price fallback and no silent ticker exclusion are permitted.

## Source-derived blocker breakdown

| Policy reason | Event type | Rows | Distinct tickers | First date | Last date |
|---|---|---:|---:|---|---|
| NORMALIZED_KNOWN_AFTER_EFFECTIVE | CASH_DIVIDEND | 4 | 4 | 2016-09-12 | 2025-04-30 |
| SHARE_MUTATION_KNOWN_DATE_MISSING | capital_reduction | 457 | 337 | 2016-01-05 | 2026-06-30 |
| SHARE_MUTATION_KNOWN_DATE_MISSING | par_value_change_split | 21 | 19 | 2019-09-09 | 2026-04-20 |

- event-level exclusions: 482
- distinct excluded tickers: 355
- exclusion ledger: `docs/SOURCE_CA_PIT_EXCLUSIONS.csv`
- exclusion ledger SHA-256: `379d58f6a8aa06b1e020d56911930f4bc01861d3eeca109613d9e5b1e490d134`

## Common-support application

The future attribution runner must load the frozen exclusion ledger, derive the exact ticker set, and assert that neither baseline nor any control/ranking rule contains an excluded ticker. The assertion is a hard gate, not a warning.

The event-level CSV is the authoritative explicit list. Each excluded event is named by ticker, effective date, event type, source, and reason. Duplicate ticker events remain separate rows for auditability.

## External-validity boundary

The frozen common-support set excludes 355 of 1,986 eligible-universe tickers, or 17.9%. Because the exclusions are concentrated in securities with capital reductions or par-value/share-coordinate changes plus four late-known dividend events, the resulting attribution applies to the common-support sub-universe, not automatically to the full Taiwan top-25%-turnover universe. This restriction is methodological rather than performance-driven and must accompany any interpretation of the attribution results.

## Decision boundary

This policy does not promote a strategy, select a capacity rule, alter signal parameters, or unlock locked OOS. It only defines the common-support universe required before policy/capacity attribution.
