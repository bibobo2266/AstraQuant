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
- declared Cartesian combinations: 432
- structurally invalid combinations skipped by preregistered constraints: 156
- evaluated parameter combinations: 276
- feature-cache hits / misses: 1,641 / 15

## Parameter-surface summary

- combinations with at least one valid forward outcome: 276/276
- total signal candidates across combinations: 3,773,858
- median absolute-outcome coverage: 99.87%
- median demeaned-outcome coverage: 99.87%
- absolute expectancy q10 / median / q90 across combinations: 4.38% / 4.67% / 4.97%
- demeaned expectancy q10 / median / q90 across combinations: 0.73% / 1.00% / 1.27%
- fraction of combinations with positive absolute expectancy: 100.00%
- fraction of combinations with positive demeaned expectancy: 100.00%

## Marginal parameter summaries

These are medians across the other declared axes; they are descriptive and are not winner selection.

### trigger.hold_floor

| Value | Configs | Median signals | Median absolute expectancy | Median demeaned expectancy | Positive absolute configs | Positive demeaned configs |
|---|---:|---:|---:|---:|---:|---:|
| 45 | 108 | 19194 | 4.52% | 0.88% | 100.0% | 100.0% |
| 50 | 108 | 11494 | 4.84% | 1.14% | 100.0% | 100.0% |
| 55 | 60 | 5170 | 4.79% | 1.10% | 100.0% | 100.0% |

### trigger.pullback_ceiling

| Value | Configs | Median signals | Median absolute expectancy | Median demeaned expectancy | Positive absolute configs | Positive demeaned configs |
|---|---:|---:|---:|---:|---:|---:|
| 55 | 96 | 12043 | 4.60% | 0.94% | 100.0% | 100.0% |
| 58 | 108 | 13264 | 4.70% | 1.00% | 100.0% | 100.0% |
| 60 | 72 | 15305 | 4.75% | 1.08% | 100.0% | 100.0% |

### trigger.pullback_window

| Value | Configs | Median signals | Median absolute expectancy | Median demeaned expectancy | Positive absolute configs | Positive demeaned configs |
|---|---:|---:|---:|---:|---:|---:|
| 3 | 92 | 14624 | 4.57% | 0.91% | 100.0% | 100.0% |
| 6 | 92 | 13651 | 4.69% | 1.00% | 100.0% | 100.0% |
| 9 | 92 | 11494 | 4.71% | 1.05% | 100.0% | 100.0% |

### trigger.reclaim_level

| Value | Configs | Median signals | Median absolute expectancy | Median demeaned expectancy | Positive absolute configs | Positive demeaned configs |
|---|---:|---:|---:|---:|---:|---:|
| 58 | 24 | 13098 | 4.56% | 0.87% | 100.0% | 100.0% |
| 60 | 60 | 13292 | 4.68% | 0.96% | 100.0% | 100.0% |
| 62 | 96 | 14266 | 4.78% | 1.10% | 100.0% | 100.0% |
| 65 | 96 | 12310 | 4.59% | 0.93% | 100.0% | 100.0% |

### trigger.volume_multiplier

| Value | Configs | Median signals | Median absolute expectancy | Median demeaned expectancy | Positive absolute configs | Positive demeaned configs |
|---|---:|---:|---:|---:|---:|---:|
| 1.0 | 69 | 16102 | 4.72% | 1.03% | 100.0% | 100.0% |
| 1.2 | 69 | 14475 | 4.66% | 1.00% | 100.0% | 100.0% |
| 1.5 | 69 | 12884 | 4.68% | 1.01% | 100.0% | 100.0% |
| 2.0 | 69 | 10012 | 4.55% | 0.95% | 100.0% | 100.0% |

## Full results

Machine-readable table: `docs/SOURCE_RSI_DAILY_SWEEP.csv`.

Absolute and demeaned outcomes are reported side by side. The next valid step is robustness analysis over neighboring cells / calendar regimes. Do not infer a Taiwan-optimal parameter from the maximum cell.
