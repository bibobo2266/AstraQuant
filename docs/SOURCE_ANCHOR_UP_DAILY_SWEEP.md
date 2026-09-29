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
- declared Cartesian combinations: 18
- structurally invalid combinations skipped by preregistered constraints: 0
- evaluated parameter combinations: 18
- feature-cache hits / misses: 0 / 0

## Parameter-surface summary

- combinations with at least one valid forward outcome: 18/18
- total signal candidates across combinations: 1,094,010
- median outcome coverage: 99.89%
- expectancy q10 / median / q90 across combinations: 3.92% / 4.10% / 4.25%
- fraction of combinations with positive expectancy: 100.00%

## Marginal parameter summaries

These are medians across the other declared axes; they are descriptive and are not winner selection.

### trigger.left_confirm_sessions

| Value | Configs | Median signals | Median expectancy | Positive expectancy configs |
|---|---:|---:|---:|---:|
| 3 | 6 | 79326 | 4.22% | 100.0% |
| 5 | 6 | 61657 | 4.15% | 100.0% |
| 10 | 6 | 39581 | 3.98% | 100.0% |

### trigger.required_closes

| Value | Configs | Median signals | Median expectancy | Positive expectancy configs |
|---|---:|---:|---:|---:|
| 1 | 9 | 65737 | 4.09% | 100.0% |
| 2 | 9 | 57464 | 4.11% | 100.0% |

### trigger.right_confirm_sessions

| Value | Configs | Median signals | Median expectancy | Positive expectancy configs |
|---|---:|---:|---:|---:|
| 1 | 6 | 67122 | 4.22% | 100.0% |
| 2 | 6 | 61600 | 4.15% | 100.0% |
| 3 | 6 | 58088 | 3.97% | 100.0% |

## Full results

Machine-readable table: `docs/SOURCE_ANCHOR_UP_DAILY_SWEEP.csv`.

The next valid step is robustness analysis over neighboring cells / calendar regimes. Do not infer a Taiwan-optimal parameter from the maximum cell.
