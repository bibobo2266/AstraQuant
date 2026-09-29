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
- parameter combinations: 18
- feature-cache hits / misses: 0 / 0

## Parameter-surface summary

- combinations with at least one valid forward outcome: 18/18
- total signal candidates across combinations: 186,219
- median outcome coverage: 99.73%
- expectancy q10 / median / q90 across combinations: 4.16% / 4.38% / 5.53%
- fraction of combinations with positive expectancy: 100.00%

## Marginal parameter summaries

These are medians across the other declared axes; they are descriptive and are not winner selection.

### trigger.max_chase_pct

| Value | Configs | Median signals | Median expectancy | Positive expectancy configs |
|---|---:|---:|---:|---:|
| 0.03 | 9 | 7494 | 4.43% | 100.0% |
| 0.05 | 9 | 9163 | 4.32% | 100.0% |

### trigger.max_dryup_volume_ratio

| Value | Configs | Median signals | Median expectancy | Positive expectancy configs |
|---|---:|---:|---:|---:|
| 0.5 | 6 | 2934 | 4.63% | 100.0% |
| 0.7 | 6 | 8800 | 4.22% | 100.0% |
| 0.9 | 6 | 17027 | 4.29% | 100.0% |

### trigger.pivot_lookback

| Value | Configs | Median signals | Median expectancy | Positive expectancy configs |
|---|---:|---:|---:|---:|
| 10 | 6 | 16640 | 4.20% | 100.0% |
| 20 | 6 | 8800 | 4.30% | 100.0% |
| 40 | 6 | 3408 | 5.43% | 100.0% |

## Full results

Machine-readable table: `docs/SOURCE_VCP_DAILY_SWEEP.csv`.

The next valid step is robustness analysis over neighboring cells / calendar regimes. Do not infer a Taiwan-optimal parameter from the maximum cell.
