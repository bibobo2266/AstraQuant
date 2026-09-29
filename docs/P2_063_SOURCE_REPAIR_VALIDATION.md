# P2-063 Source Repair Validation

Status: **PASS**

- P2-060 exclusions SHA256: 379d58f6a8aa06b1e020d56911930f4bc01861d3eeca109613d9e5b1e490d134
- eligible distinct tickers: 1,986
- candidate IDs pure four-digit numeric: True
- 2883B RAW rows: 1,092
- 2883B tradability rows: 1,092
- 2883B RAW range: 2021-12-30 → 2026-07-07
- 2883B canonical RAW mark on 2021-12-30: 9.59

## Four hard checks

| Check | Result |
|---|---|
| p2_060_exclusion_sha_unchanged | PASS |
| frozen_top25_eligible_ticker_count_1986 | PASS |
| 2883b_raw_tradability_window_covered | PASS |
| suffix_security_markable_but_not_candidate | PASS |

Research candidate construction remains four-digit ordinary-share only. 2883B is admitted solely to the valuation/execution path when received through an explicit corporate action.

No adjusted-price fallback or synthetic trade is used by this validation.
