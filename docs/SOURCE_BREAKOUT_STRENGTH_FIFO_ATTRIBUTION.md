# Breakout-Strength Direction + CA-Aware FIFO Attribution

Status: **PASS**

## Trade-level results — primary statistic

| Rule | Trades | Win rate | Avg win | Avg loss | Payoff | Expectancy / trade | Stop-normalized expectancy |
|---|---:|---:|---:|---:|---:|---:|---:|
| ticker_asc | 182 | 30.22% | 57.07% | -12.49% | 4.568 | 8.60% | 0.716 |
| turnover_desc | 228 | 22.37% | 63.58% | -12.85% | 4.949 | 4.31% | 0.359 |
| turnover_asc | 201 | 28.86% | 47.73% | -13.04% | 3.660 | 4.49% | 0.375 |
| breakout_excess_desc | 243 | 22.22% | 67.95% | -12.76% | 5.327 | 5.18% | 0.432 |
| breakout_excess_asc | 179 | 28.49% | 49.00% | -12.09% | 4.053 | 5.32% | 0.443 |
| hash_asc | 204 | 28.43% | 59.33% | -12.51% | 4.744 | 7.92% | 0.660 |

Closed-trade expectancy excludes every entry fill with any remaining open FIFO lot.

### Open (unclosed) entry lots — excluded from expectancy

| Rule | Source fill | Current ticker | Quantity | Opened at |
|---|---|---|---:|---|
| ticker_asc | fill:entry:2026-04-23:1409:0 | 1409 | 187000 | 2026-04-23 00:00:00 |
| ticker_asc | fill:entry:2026-06-22:1708:0 | 1708 | 44000 | 2026-06-22 00:00:00 |
| ticker_asc | fill:entry:2026-04-16:1711:0 | 1711 | 68000 | 2026-04-16 00:00:00 |
| ticker_asc | fill:entry:2026-06-12:1714:0 | 1714 | 201000 | 2026-06-12 00:00:00 |
| ticker_asc | fill:entry:2026-04-13:2308:0 | 2308 | 1000 | 2026-04-13 00:00:00 |
| ticker_asc | fill:entry:2025-12-31:2344:0 | 2344 | 28000 | 2025-12-31 00:00:00 |
| ticker_asc | fill:entry:2026-02-23:2360:0 | 2360 | 1000 | 2026-02-23 00:00:00 |
| ticker_asc | fill:entry:2026-04-16:2484:1 | 2484 | 17000 | 2026-04-16 00:00:00 |
| ticker_asc | fill:entry:2025-11-25:2485:0 | 2485 | 5000 | 2025-11-25 00:00:00 |
| ticker_asc | fill:entry:2025-12-10:2834:0 | 2834 | 149000 | 2025-12-10 00:00:00 |
| turnover_desc | fill:entry:2026-04-23:2303:0 | 2303 | 32000 | 2026-04-23 00:00:00 |
| turnover_desc | fill:entry:2026-04-13:2308:0 | 2308 | 1000 | 2026-04-13 00:00:00 |
| turnover_desc | fill:entry:2025-10-13:2330:0 | 2330 | 1000 | 2025-10-13 00:00:00 |
| turnover_desc | fill:entry:2026-06-12:2881:0 | 2881 | 21000 | 2026-06-12 00:00:00 |
| turnover_desc | fill:entry:2026-05-20:3045:0 | 3045 | 16000 | 2026-05-20 00:00:00 |
| turnover_desc | fill:entry:2026-06-23:3189:0 | 3189 | 3000 | 2026-06-23 00:00:00 |
| turnover_desc | fill:entry:2026-06-25:5347:0 | 5347 | 14000 | 2026-06-25 00:00:00 |
| turnover_desc | fill:entry:2026-06-30:6139:0 | 6139 | 2000 | 2026-06-30 00:00:00 |
| turnover_desc | fill:entry:2025-11-03:6274:0 | 6274 | 2000 | 2025-11-03 00:00:00 |
| turnover_desc | fill:entry:2026-03-31:8046:0 | 8046 | 1000 | 2026-03-31 00:00:00 |
| turnover_asc | fill:entry:2025-12-03:1720:0 | 1720 | 32000 | 2025-12-03 00:00:00 |
| turnover_asc | fill:entry:2026-06-12:2483:0 | 2483 | 44000 | 2026-06-12 00:00:00 |
| turnover_asc | fill:entry:2026-06-29:2484:0 | 2484 | 38000 | 2026-06-29 00:00:00 |
| turnover_asc | fill:entry:2026-04-24:2855:0 | 2855 | 75000 | 2026-04-24 00:00:00 |
| turnover_asc | fill:entry:2026-02-23:2897:0 | 2897 | 182000 | 2026-02-23 00:00:00 |
| turnover_asc | fill:entry:2025-07-09:3543:0 | 3543 | 86000 | 2025-07-09 00:00:00 |
| turnover_asc | fill:entry:2026-05-07:6016:0 | 6016 | 130000 | 2026-05-07 00:00:00 |
| turnover_asc | fill:entry:2025-07-29:6290:0 | 6290 | 27000 | 2025-07-29 00:00:00 |
| turnover_asc | fill:entry:2026-06-09:6585:0 | 6585 | 2000 | 2026-06-09 00:00:00 |
| turnover_asc | fill:entry:2026-03-23:6693:0 | 6693 | 30000 | 2026-03-23 00:00:00 |
| breakout_excess_desc | fill:entry:2025-11-03:1519:0 | 1519 | 2000 | 2025-11-03 00:00:00 |
| breakout_excess_desc | fill:entry:2026-06-23:2303:0 | 2303 | 12000 | 2026-06-23 00:00:00 |
| breakout_excess_desc | fill:entry:2025-11-25:2485:0 | 2485 | 101000 | 2025-11-25 00:00:00 |
| breakout_excess_desc | fill:entry:2025-07-30:2645:0 | 2645 | 13000 | 2025-07-30 00:00:00 |
| breakout_excess_desc | fill:entry:2026-06-11:3441:0 | 3441 | 18000 | 2026-06-11 00:00:00 |
| breakout_excess_desc | fill:entry:2026-05-19:3577:0 | 3577 | 14000 | 2026-05-19 00:00:00 |
| breakout_excess_desc | fill:entry:2026-05-06:3707:1 | 3707 | 1000 | 2026-05-06 00:00:00 |
| breakout_excess_desc | fill:entry:2026-02-23:6683:0 | 6683 | 1000 | 2026-02-23 00:00:00 |
| breakout_excess_desc | fill:entry:2026-04-15:6789:0 | 6789 | 1000 | 2026-04-15 00:00:00 |
| breakout_excess_asc | fill:entry:2026-03-10:1309:0 | 1309 | 148000 | 2026-03-10 00:00:00 |
| breakout_excess_asc | fill:entry:2026-05-22:2027:0 | 2027 | 61000 | 2026-05-22 00:00:00 |
| breakout_excess_asc | fill:entry:2026-05-29:2376:0 | 2376 | 4000 | 2026-05-29 00:00:00 |
| breakout_excess_asc | fill:entry:2026-05-25:2484:0 | 2484 | 28000 | 2026-05-25 00:00:00 |
| breakout_excess_asc | fill:entry:2026-02-23:2891:0 | 2891 | 36000 | 2026-02-23 00:00:00 |
| breakout_excess_asc | fill:entry:2025-07-09:3017:0 | 3017 | 1000 | 2025-07-09 00:00:00 |
| breakout_excess_asc | fill:entry:2026-04-23:3709:0 | 3709 | 31000 | 2026-04-23 00:00:00 |
| breakout_excess_asc | fill:entry:2026-05-18:4904:0 | 4904 | 23000 | 2026-05-18 00:00:00 |
| breakout_excess_asc | fill:entry:2026-04-14:4979:0 | 4979 | 3000 | 2026-04-14 00:00:00 |
| breakout_excess_asc | fill:entry:2025-08-19:6196:0 | 6196 | 10000 | 2025-08-19 00:00:00 |
| hash_asc | fill:entry:2026-04-23:1590:0 | 1590 | 3000 | 2026-04-23 00:00:00 |
| hash_asc | fill:entry:2025-12-19:2408:0 | 2408 | 21000 | 2025-12-19 00:00:00 |
| hash_asc | fill:entry:2026-04-16:2484:1 | 2484 | 3000 | 2026-04-16 00:00:00 |
| hash_asc | fill:entry:2025-07-14:2838:0 | 2838 | 194740 | 2025-07-14 00:00:00 |
| hash_asc | fill:entry:2026-05-18:3141:0 | 3141 | 74000 | 2026-05-18 00:00:00 |
| hash_asc | fill:entry:2025-11-03:3264:0 | 3264 | 42000 | 2025-11-03 00:00:00 |
| hash_asc | fill:entry:2026-06-12:5904:0 | 5904 | 4000 | 2026-06-12 00:00:00 |
| hash_asc | fill:entry:2026-06-09:6585:0 | 6585 | 17000 | 2026-06-09 00:00:00 |
| hash_asc | fill:entry:2026-02-23:6861:0 | 6861 | 40000 | 2026-02-23 00:00:00 |
| hash_asc | fill:entry:2025-09-11:8299:0 | 8299 | 6000 | 2025-09-11 00:00:00 |

## Directional trade-level comparison

- breakout_excess_desc minus hash_asc expectancy: -2.74 percentage points
- paired calendar-year block 95% interval: [-9.24, 2.63] percentage points
- effective calendar-year block count: 11; Monte Carlo resamples: 5,000
- breakout_excess_asc minus hash_asc expectancy: -2.60 percentage points
- paired calendar-year block 95% interval: [-11.10, 3.34] percentage points
- effective calendar-year block count: 11; Monte Carlo resamples: 5,000

**Verdict:** Within the frozen P2-060 sub-universe, breakout strength carries no clear directional information at trade level under the predeclared interval rule.

The verdict rule was fixed before this rerun: directional only if desc-hash is strictly above zero while asc-hash is strictly below zero; inverse only if desc-hash is strictly below zero while asc-hash is strictly above zero; otherwise no clear directional information.

## Path metrics — secondary

| Rule | CAGR | Max DD | Sharpe | Entries | Open lots |
|---|---:|---:|---:|---:|---:|
| ticker_asc | 14.12% | -31.74% | 0.794 | 192 | 10 |
| turnover_desc | 10.45% | -42.67% | 0.581 | 238 | 10 |
| turnover_asc | 13.90% | -43.41% | 0.786 | 211 | 10 |
| breakout_excess_desc | 8.79% | -37.94% | 0.497 | 252 | 9 |
| breakout_excess_asc | 10.41% | -39.59% | 0.689 | 189 | 10 |
| hash_asc | 20.47% | -39.78% | 0.990 | 214 | 10 |

## Rule provenance

- ticker_asc, turnover_desc, turnover_asc, breakout_excess_desc, hash_asc were preregistered in P2-061 before any result was observed.
- breakout_excess_asc was added in P2-062 AFTER the P2-061 result was observed, at external-reviewer request, as the symmetric counterpart required to distinguish directional signal information from dispersion-selection effects. It is NOT preregistered-blind.

## Frozen-design and valuation-scope gates

- P2-060 exclusion SHA: 379d58f6a8aa06b1e020d56911930f4bc01861d3eeca109613d9e5b1e490d134
- frozen eligible-universe distinct tickers: 1,986 (expected 1,986)
- candidate universe remains numeric four-digit ordinary shares only.
- valuation universe may additionally contain securities passively received through explicit corporate actions; these successors are never signal candidates.
- no adjusted-price fallback, synthetic sell fill, or silent ticker exclusion is permitted.
- signal definition, 250-session lookback, top-25% turnover universe, RAW execution/accounting, 10% NAV target, 10-position cap, 12% stop, 20-session re-entry, 250-session max hold, 1000-share lot, and zero fee/slippage are unchanged.

## Operational gates

| Gate | Result |
|---|---|
| frozen_exclusion_hash_matches | PASS |
| all_six_declared_rules_complete | PASS |
| common_support_exclusion_active | PASS |
| frozen_eligible_ticker_count_unchanged | PASS |
| candidate_universe_four_digit_ordinary_only | PASS |
| valuation_scope_can_include_ca_successors | PASS |
| ranking_metadata_complete | PASS |
| all_nav_positive | PASS |
| fifo_closed_trades_present_all_rules | PASS |
| no_new_ca_blocker | PASS |

## Interpretation boundary

This is an attribution/falsification diagnostic, not a promotion test. No deterministic rule is selected, no parameter is tuned, and locked OOS remains locked.

The paired calendar-year block bootstrap is a descriptive uncertainty scale. Its information count is the number of calendar-year blocks reported above; 5,000 is only the number of Monte Carlo resamples and is not an effective sample size.

Closed-trade expectancy is return on entry cost. Stop-normalized expectancy is expectancy divided by the frozen 12% stop fraction; it is not realized R.

External validity remains limited to the frozen P2-060 common-support sub-universe, which excludes 355 of 1,986 eligible-universe tickers (17.9%).
