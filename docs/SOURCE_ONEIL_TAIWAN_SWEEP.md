# Source-backed Config Sweep

Status: **PASS**

## Research boundary

- This is a candidate-level research screen, not executable portfolio evidence.
- Outcome: long-direction adjusted close-to-close return 250 source sessions after the signal date.
- No RAW fill, capacity, corporate-action path, FIFO path, stop execution, or portfolio sequencing is represented here.
- The sweep does not select or promote a winning parameter combination.
- Locked OOS remains locked.

## Frozen gates

- P2-060 exclusion SHA: 379d58f6a8aa06b1e020d56911930f4bc01861d3eeca109613d9e5b1e490d134
- eligible-universe distinct tickers: 1,986 (expected 1,986)
- signal window: 2016-01-04 through 2026-06-30
- parameter combinations: 81
- feature-cache hits / misses: 236 / 7

## Parameter-surface summary

- combinations with at least one valid forward outcome: 81/81
- total signal candidates across combinations: 2,127,579
- median outcome coverage: 87.76%
- expectancy q10 / median / q90 across combinations: 17.20% / 17.39% / 17.57%
- fraction of combinations with positive expectancy: 100.00%

## Marginal parameter summaries

These are medians across the other declared axes; they are descriptive and are not winner selection.

### filter:LONG_TERM_TREND_STRUCTURE.fast_sessions

| Value | Configs | Median signals | Median expectancy | Positive expectancy configs |
|---|---:|---:|---:|---:|
| 40 | 27 | 27275 | 17.46% | 100.0% |
| 50 | 27 | 26946 | 17.40% | 100.0% |
| 60 | 27 | 26490 | 17.35% | 100.0% |

### filter:LONG_TERM_TREND_STRUCTURE.min_fast_slow_spread

| Value | Configs | Median signals | Median expectancy | Positive expectancy configs |
|---|---:|---:|---:|---:|
| 0.0 | 27 | 27988 | 17.36% | 100.0% |
| 0.02 | 27 | 26753 | 17.43% | 100.0% |
| 0.05 | 27 | 24102 | 17.44% | 100.0% |

### filter:LONG_TERM_TREND_STRUCTURE.slope_lookback_sessions

| Value | Configs | Median signals | Median expectancy | Positive expectancy configs |
|---|---:|---:|---:|---:|
| 5 | 27 | 27395 | 17.44% | 100.0% |
| 10 | 27 | 26946 | 17.43% | 100.0% |
| 20 | 27 | 26388 | 17.28% | 100.0% |

### filter:LONG_TERM_TREND_STRUCTURE.slow_sessions

| Value | Configs | Median signals | Median expectancy | Positive expectancy configs |
|---|---:|---:|---:|---:|
| 180 | 27 | 26710 | 17.49% | 100.0% |
| 200 | 27 | 26825 | 17.39% | 100.0% |
| 220 | 27 | 26967 | 17.32% | 100.0% |

## Full results

Machine-readable table: `docs/SOURCE_ONEIL_TAIWAN_SWEEP.csv`.

The next valid step is robustness analysis over neighboring cells / calendar regimes. Do not infer a Taiwan-optimal parameter from the maximum cell.
