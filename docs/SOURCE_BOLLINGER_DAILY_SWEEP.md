# Source-backed Config Sweep

Status: **PASS**

## Research boundary

- This is a candidate-level research screen, not executable portfolio evidence.
- Outcome: long-direction adjusted close-to-close return 60 source sessions after the signal date.
- No RAW fill, capacity, corporate-action path, FIFO path, stop execution, or portfolio sequencing is represented here.
- The sweep does not select or promote a winning parameter combination.
- Locked OOS remains locked.

## Frozen gates

- P2-060 exclusion SHA: 379d58f6a8aa06b1e020d56911930f4bc01861d3eeca109613d9e5b1e490d134
- eligible-universe distinct tickers: 1,986 (expected 1,986)
- signal window: 2016-01-04 through 2026-06-30
- declared Cartesian combinations: 81
- structurally invalid combinations skipped by preregistered constraints: 0
- evaluated parameter combinations: 81
- feature-cache hits / misses: 316 / 8

## Parameter-surface summary

- combinations with at least one valid forward outcome: 81/81
- total signal candidates across combinations: 908,192
- median outcome coverage: 99.85%
- expectancy q10 / median / q90 across combinations: 2.77% / 3.25% / 3.79%
- fraction of combinations with positive expectancy: 100.00%

## Marginal parameter summaries

These are medians across the other declared axes; they are descriptive and are not winner selection.

### trigger.max_bandwidth_percentile

| Value | Configs | Median signals | Median expectancy | Positive expectancy configs |
|---|---:|---:|---:|---:|
| 0.1 | 27 | 7298 | 2.90% | 100.0% |
| 0.2 | 27 | 10839 | 3.25% | 100.0% |
| 0.3 | 27 | 14067 | 3.54% | 100.0% |

### trigger.stddev

| Value | Configs | Median signals | Median expectancy | Positive expectancy configs |
|---|---:|---:|---:|---:|
| 1.5 | 27 | 10839 | 3.29% | 100.0% |
| 2.0 | 27 | 12651 | 3.32% | 100.0% |
| 2.5 | 27 | 9064 | 3.19% | 100.0% |

### trigger.volume_multiplier

| Value | Configs | Median signals | Median expectancy | Positive expectancy configs |
|---|---:|---:|---:|---:|
| 1.2 | 27 | 12353 | 3.37% | 100.0% |
| 1.5 | 27 | 10611 | 3.31% | 100.0% |
| 2.0 | 27 | 9131 | 3.07% | 100.0% |

### trigger.window

| Value | Configs | Median signals | Median expectancy | Positive expectancy configs |
|---|---:|---:|---:|---:|
| 10 | 27 | 10710 | 3.42% | 100.0% |
| 14 | 27 | 11083 | 3.09% | 100.0% |
| 20 | 27 | 10467 | 3.23% | 100.0% |

## Full results

Machine-readable table: `docs/SOURCE_BOLLINGER_DAILY_SWEEP.csv`.

The next valid step is robustness analysis over neighboring cells / calendar regimes. Do not infer a Taiwan-optimal parameter from the maximum cell.
