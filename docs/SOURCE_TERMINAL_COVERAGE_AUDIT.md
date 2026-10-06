# Source Terminal Coverage Audit

Status: **PASS_AUDIT_WITH_UNVERIFIED_FALLBACK**

Purpose: one-time terminal-security lifecycle coverage inventory for the frozen P2-060 common-support universe. This audit does not change candidates, exclusions, execution, accounting, valuation, or OOS governance.

## Frozen scope gates

- P2-060 eligible-universe window: 2016-01-04 through 2026-06-30
- terminal coverage window: 2016-01-04 through 2026-07-07
- frozen eligible distinct tickers: 1,986 (expected 1,986)
- P2-060 exclusion rows / distinct tickers: 482 / 355
- P2-060 exclusion SHA256: 379d58f6a8aa06b1e020d56911930f4bc01861d3eeca109613d9e5b1e490d134
- common-support distinct tickers audited: 1,631

A security is classified as RAW-terminal here only when its maximum RAW date in the currently available source is earlier than 2026-07-07. A temporary gap that later resumes in the source is therefore not mislabeled as terminal.

Hard rules: no adjusted-price fallback, no stale RAW mark outside an explicit modeled terminal window, and no silent ticker exclusion.

## Summary

- RAW-terminal tickers in common support: 78
- modeled: 4
- unmodeled: 74
- conservative fallback coverage: 74
- row-count reconciliation: summary and rendered table are generated from the same dataframe; current unmodeled count = 74. The earlier 72-row presentation discrepancy is corrected.

## Modeled terminal securities

| Ticker | Last RAW | Modeled event | Date alignment | Tradability coverage end | Source availability |
|---|---|---|---|---|---|
| 6286 | 2016-04-20 | CASH_MERGER_EXTINGUISHMENT | PASS | — | terminal_events.csv |
| 5305 | 2020-11-23 | CASH_MERGER_EXTINGUISHMENT | PASS | — | terminal_events.csv |
| 2823 | 2021-12-17 | MULTI_LEG_SHARE_CONVERSION_PLUS_CASH | PASS | — | MOPS share-conversion disclosure; value weights use disclosed 20-day common reference price 13.69, preferred issue price 10.0, and cash 11.5 |
| 4141 | 2022-04-26 | CASH_MERGER_EXTINGUISHMENT | PASS | — | terminal_events.csv |

## Unmodeled terminal securities

**Terminal window**: `E1_INSIDE` means the security's Last RAW date falls on or before
`2021-12-30`, the last observed row of the frozen E1 panel (the manifest declares
`period_end = 2021-12-31`; the one-day difference is a day with no qualifying row).
`E1_OUTSIDE` means the RAW history continues past E1 and the terminal event happened
after it. Counts: **42 E1_INSIDE / 32 E1_OUTSIDE** out of 74.
Only the `E1_INSIDE` subset carries an in-E1 lifecycle event; the `E1_OUTSIDE` subset
was listed here because this audit's judgment window is the whole source
(through `2026-07-07`), not E1.


| Ticker | Last RAW | Missing lifecycle event | Tradability coverage end | Source availability | Source detail | Terminal window |
|---|---|---|---|---|---|---|
| 2847 | 2016-03-09 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 3598 | 2016-05-25 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 3573 | 2016-06-22 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 4733 | 2016-08-18 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 3474 | 2016-11-29 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 6702 | 2017-01-24 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 1729 | 2017-05-17 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 2437 | 2017-06-19 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 3559 | 2017-08-23 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 3315 | 2017-09-22 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 1715 | 2017-10-18 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 2311 | 2018-04-17 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 2325 | 2018-04-17 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 4984 | 2018-08-23 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 2856 | 2018-09-17 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 3514 | 2018-09-17 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 3561 | 2018-09-17 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 6145 | 2018-09-17 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 6422 | 2018-09-19 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 1704 | 2019-01-23 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 3519 | 2019-04-30 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 2475 | 2019-05-10 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 3579 | 2019-06-25 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 1262 | 2019-10-07 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 2499 | 2020-04-06 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 1902 | 2020-05-25 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 6238 | 2020-06-10 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 6452 | 2020-08-17 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 6497 | 2020-08-24 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 4144 | 2020-10-21 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 8497 | 2020-10-21 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 5349 | 2020-10-28 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 2448 | 2020-12-23 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 3698 | 2020-12-23 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 5264 | 2021-01-06 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 1592 | 2021-06-15 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 4152 | 2021-09-29 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 2928 | 2021-10-13 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 1724 | 2021-10-25 | TERMINAL_CA_ECONOMICS_OR_SUCCESSOR_MAPPING | — | canonical CA ledger has nearby event(s) | 2021-10-06:ex_right_dividend:TWSE TWT49U | E1_INSIDE |
| 6172 | 2021-11-17 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 3144 | 2021-12-13 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 4803 | 2021-12-15 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_INSIDE |
| 8427 | 2022-02-23 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_OUTSIDE |
| 9188 | 2022-03-03 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_OUTSIDE |
| 2841 | 2022-04-06 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_OUTSIDE |
| 1507 | 2022-04-13 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_OUTSIDE |
| 8406 | 2022-04-20 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_OUTSIDE |
| 4429 | 2022-05-24 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_OUTSIDE |
| 2936 | 2022-06-24 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_OUTSIDE |
| 5820 | 2022-10-31 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_OUTSIDE |
| 3642 | 2022-11-16 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_OUTSIDE |
| 8480 | 2022-12-14 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_OUTSIDE |
| 6594 | 2023-03-23 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_OUTSIDE |
| 3536 | 2023-04-11 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_OUTSIDE |
| 1258 | 2023-05-31 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_OUTSIDE |
| 5281 | 2023-10-24 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_OUTSIDE |
| 8418 | 2024-01-24 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_OUTSIDE |
| 2443 | 2024-04-03 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_OUTSIDE |
| 1701 | 2024-08-20 | TERMINAL_CA_ECONOMICS_OR_SUCCESSOR_MAPPING | — | canonical CA ledger has nearby event(s) | 2024-07-25:ex_right_dividend:TWSE TWT49U; 2024-07-31:dividend:FinMind TaiwanStockDividend | E1_OUTSIDE |
| 6514 | 2024-10-08 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_OUTSIDE |
| 8420 | 2024-11-20 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_OUTSIDE |
| 6457 | 2024-12-25 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_OUTSIDE |
| 3202 | 2025-04-02 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_OUTSIDE |
| 2888 | 2025-07-11 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_OUTSIDE |
| 6288 | 2025-08-04 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_OUTSIDE |
| 4945 | 2025-09-01 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_OUTSIDE |
| 2809 | 2025-09-17 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_OUTSIDE |
| 6747 | 2025-11-26 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_OUTSIDE |
| 3454 | 2026-03-18 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_OUTSIDE |
| 1589 | 2026-04-02 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_OUTSIDE |
| 4804 | 2026-04-13 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_OUTSIDE |
| 4987 | 2026-05-20 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_OUTSIDE |
| 3426 | 2026-06-01 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_OUTSIDE |
| 6806 | 2026-06-22 | UNKNOWN_TERMINAL_LIFECYCLE | — | no nearby canonical suspension/CA row | external TWSE/MOPS lifecycle audit required | E1_OUTSIDE |

## Canonical modeled feed outside frozen common support

These are already curated in the engine but are not counted in the common-support modeled/unmodeled totals above.

- tickers: 6251

## Interpretation and next gate

Two-track policy is active. A CONFIRMED row in data/research/terminal_events.csv overrides the conservative fallback. PARTIAL and NOT_FOUND rows do not override it.

For every still-unmodeled terminal security, AstraQuant applies UNVERIFIED_TERMINAL_CASHOUT at the final observed RAW trading-session close using that RAW close as cash consideration. Cash mergers often include a premium, so this fallback is conservative and tends to understate rather than overstate strategy return.

No adjusted-price fallback, post-terminal stale RAW mark, synthetic trade, or silent ticker exclusion is permitted. External verification can replace fallback economics by updating the CSV without code changes.
