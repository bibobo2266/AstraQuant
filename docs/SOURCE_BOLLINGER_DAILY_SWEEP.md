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
- declared Cartesian combinations: 81
- structurally invalid combinations skipped by preregistered constraints: 0
- evaluated parameter combinations: 81
- feature-cache hits / misses: 316 / 8

## Parameter-surface summary

- combinations with at least one valid forward outcome: 81/81
- total signal candidates across combinations: 908,192
- median absolute-outcome coverage: 99.85%
- median demeaned-outcome coverage: 99.85%
- absolute expectancy q10 / median / q90 across combinations: 2.77% / 3.25% / 3.79%
- demeaned expectancy q10 / median / q90 across combinations: -0.42% / -0.03% / 0.37%
- fraction of combinations with positive absolute expectancy: 100.00%
- fraction of combinations with positive demeaned expectancy: 43.21%

## Marginal parameter summaries

These are medians across the other declared axes; they are descriptive and are not winner selection.

### trigger.max_bandwidth_percentile

| Value | Configs | Median signals | Median absolute expectancy | Median demeaned expectancy | Positive absolute configs | Positive demeaned configs |
|---|---:|---:|---:|---:|---:|---:|
| 0.1 | 27 | 7298 | 2.90% | -0.33% | 100.0% | 3.7% |
| 0.2 | 27 | 10839 | 3.25% | -0.03% | 100.0% | 33.3% |
| 0.3 | 27 | 14067 | 3.54% | 0.24% | 100.0% | 92.6% |

### trigger.stddev

| Value | Configs | Median signals | Median absolute expectancy | Median demeaned expectancy | Positive absolute configs | Positive demeaned configs |
|---|---:|---:|---:|---:|---:|---:|
| 1.5 | 27 | 10839 | 3.29% | -0.08% | 100.0% | 40.7% |
| 2.0 | 27 | 12651 | 3.32% | -0.02% | 100.0% | 48.1% |
| 2.5 | 27 | 9064 | 3.19% | -0.03% | 100.0% | 40.7% |

### trigger.volume_multiplier

| Value | Configs | Median signals | Median absolute expectancy | Median demeaned expectancy | Positive absolute configs | Positive demeaned configs |
|---|---:|---:|---:|---:|---:|---:|
| 1.2 | 27 | 12353 | 3.37% | 0.01% | 100.0% | 55.6% |
| 1.5 | 27 | 10611 | 3.31% | -0.05% | 100.0% | 48.1% |
| 2.0 | 27 | 9131 | 3.07% | -0.26% | 100.0% | 25.9% |

### trigger.window

| Value | Configs | Median signals | Median absolute expectancy | Median demeaned expectancy | Positive absolute configs | Positive demeaned configs |
|---|---:|---:|---:|---:|---:|---:|
| 10 | 27 | 10710 | 3.42% | 0.11% | 100.0% | 59.3% |
| 14 | 27 | 11083 | 3.09% | -0.21% | 100.0% | 29.6% |
| 20 | 27 | 10467 | 3.23% | -0.10% | 100.0% | 40.7% |

## Full results

Machine-readable table: `docs/SOURCE_BOLLINGER_DAILY_SWEEP.csv`.

Absolute and demeaned outcomes are reported side by side. The next valid step is robustness analysis over neighboring cells / calendar regimes. Do not infer a Taiwan-optimal parameter from the maximum cell.
