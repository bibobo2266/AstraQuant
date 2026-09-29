# Source-backed Config Sweep

Status: **PASS**

## Research boundary

- epoch: E1：歷史開發期
- E1 is the default effect period; E2 requires explicit RESEARCH_EPOCH=E2.
- This is a candidate-level research screen, not executable portfolio evidence.
- Absolute outcome: long-direction adjusted close-to-close return 250 source sessions after the signal date.
- Demeaned outcome: stock forward return minus the same-date P2-060 common-support cross-sectional mean, then direction-adjusted.
- Demean cross-section requires four-digit numeric IDs, frozen P2-060 exclusions removed, observed_trade AND valid_ohlc, and at least 200 valid names on that date.
- No RAW fill, capacity, corporate-action path, FIFO path, stop execution, or portfolio sequencing is represented here.
- The sweep does not select or promote a winning parameter combination.
- Locked OOS remains locked.

## Frozen gates

- P2-060 exclusion SHA: 379d58f6a8aa06b1e020d56911930f4bc01861d3eeca109613d9e5b1e490d134
- eligible-universe distinct tickers: 1,986 (expected 1,986)
- signal window: 2016-01-04 through 2021-12-31
- declared Cartesian combinations: 81
- structurally invalid combinations skipped by preregistered constraints: 0
- evaluated parameter combinations: 81
- feature-cache hits / misses: 236 / 7

## Parameter-surface summary

- combinations with at least one valid forward outcome: 81/81
- total signal candidates across combinations: 1,103,262
- cross-epoch forward outcomes purged: 270,630
- median absolute-outcome coverage: 75.15%
- median demeaned-outcome coverage: 75.15%
- absolute expectancy q10 / median / q90 across combinations: 17.48% / 17.75% / 18.10%
- demeaned expectancy q10 / median / q90 across combinations: 0.74% / 0.92% / 1.09%
- fraction of combinations with positive absolute expectancy: 100.00%
- fraction of combinations with positive demeaned expectancy: 100.00%

## Marginal parameter summaries

These are medians across the other declared axes; they are descriptive and are not winner selection.

### filter:LONG_TERM_TREND_STRUCTURE.fast_sessions

| Value | Configs | Median signals | Median absolute expectancy | Median demeaned expectancy | Positive absolute configs | Positive demeaned configs |
|---|---:|---:|---:|---:|---:|---:|
| 40 | 27 | 14288 | 17.81% | 0.99% | 100.0% | 100.0% |
| 50 | 27 | 14021 | 17.73% | 0.92% | 100.0% | 100.0% |
| 60 | 27 | 13685 | 17.67% | 0.90% | 100.0% | 100.0% |

### filter:LONG_TERM_TREND_STRUCTURE.min_fast_slow_spread

| Value | Configs | Median signals | Median absolute expectancy | Median demeaned expectancy | Positive absolute configs | Positive demeaned configs |
|---|---:|---:|---:|---:|---:|---:|
| 0.0 | 27 | 14576 | 17.61% | 0.90% | 100.0% | 100.0% |
| 0.02 | 27 | 13985 | 17.75% | 0.99% | 100.0% | 100.0% |
| 0.05 | 27 | 12409 | 17.97% | 0.90% | 100.0% | 100.0% |

### filter:LONG_TERM_TREND_STRUCTURE.slope_lookback_sessions

| Value | Configs | Median signals | Median absolute expectancy | Median demeaned expectancy | Positive absolute configs | Positive demeaned configs |
|---|---:|---:|---:|---:|---:|---:|
| 5 | 27 | 14238 | 17.78% | 0.93% | 100.0% | 100.0% |
| 10 | 27 | 14021 | 17.79% | 0.95% | 100.0% | 100.0% |
| 20 | 27 | 13749 | 17.62% | 0.86% | 100.0% | 100.0% |

### filter:LONG_TERM_TREND_STRUCTURE.slow_sessions

| Value | Configs | Median signals | Median absolute expectancy | Median demeaned expectancy | Positive absolute configs | Positive demeaned configs |
|---|---:|---:|---:|---:|---:|---:|
| 180 | 27 | 13875 | 17.86% | 1.05% | 100.0% | 100.0% |
| 200 | 27 | 14007 | 17.75% | 0.92% | 100.0% | 100.0% |
| 220 | 27 | 13988 | 17.65% | 0.86% | 100.0% | 100.0% |

## Full results

Machine-readable table: `docs/SOURCE_ONEIL_TAIWAN_SWEEP.csv`.

Absolute and demeaned outcomes are reported side by side. The next valid step is robustness analysis over neighboring cells / calendar regimes. Do not infer a Taiwan-optimal parameter from the maximum cell.
