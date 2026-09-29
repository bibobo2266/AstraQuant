# Source-backed Config Sweep

Status: **PASS**

## Research boundary

- This is a candidate-level research screen, not executable portfolio evidence.
- Absolute outcome: long-direction adjusted close-to-close return 60 source sessions after the signal date.
- Demeaned outcome: stock forward return minus the same-date P2-060 common-support cross-sectional mean, then direction-adjusted.
- Demean cross-section requires four-digit numeric IDs, frozen P2-060 exclusions removed, observed_trade AND valid_ohlc, and at least 200 valid names on that date.
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
- total signal candidates across combinations: 186,219
- median absolute-outcome coverage: 99.73%
- median demeaned-outcome coverage: 99.73%
- absolute expectancy q10 / median / q90 across combinations: 4.16% / 4.38% / 5.53%
- demeaned expectancy q10 / median / q90 across combinations: 0.57% / 0.79% / 2.05%
- fraction of combinations with positive absolute expectancy: 100.00%
- fraction of combinations with positive demeaned expectancy: 100.00%

## Marginal parameter summaries

These are medians across the other declared axes; they are descriptive and are not winner selection.

### trigger.max_chase_pct

| Value | Configs | Median signals | Median absolute expectancy | Median demeaned expectancy | Positive absolute configs | Positive demeaned configs |
|---|---:|---:|---:|---:|---:|---:|
| 0.03 | 9 | 7494 | 4.43% | 0.83% | 100.0% | 100.0% |
| 0.05 | 9 | 9163 | 4.32% | 0.74% | 100.0% | 100.0% |

### trigger.max_dryup_volume_ratio

| Value | Configs | Median signals | Median absolute expectancy | Median demeaned expectancy | Positive absolute configs | Positive demeaned configs |
|---|---:|---:|---:|---:|---:|---:|
| 0.5 | 6 | 2934 | 4.63% | 1.04% | 100.0% | 100.0% |
| 0.7 | 6 | 8800 | 4.22% | 0.67% | 100.0% | 100.0% |
| 0.9 | 6 | 17027 | 4.29% | 0.65% | 100.0% | 100.0% |

### trigger.pivot_lookback

| Value | Configs | Median signals | Median absolute expectancy | Median demeaned expectancy | Positive absolute configs | Positive demeaned configs |
|---|---:|---:|---:|---:|---:|---:|
| 10 | 6 | 16640 | 4.20% | 0.58% | 100.0% | 100.0% |
| 20 | 6 | 8800 | 4.30% | 0.73% | 100.0% | 100.0% |
| 40 | 6 | 3408 | 5.43% | 2.02% | 100.0% | 100.0% |

## Full results

Machine-readable table: `docs/SOURCE_VCP_DAILY_SWEEP.csv`.

Absolute and demeaned outcomes are reported side by side. The next valid step is robustness analysis over neighboring cells / calendar regimes. Do not infer a Taiwan-optimal parameter from the maximum cell.
