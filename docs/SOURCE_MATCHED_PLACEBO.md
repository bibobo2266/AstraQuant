# Date-Count-Matched Random-Control Diagnostic

Status: **PASS**

Purpose: test whether the breakout stock selection adds information beyond simply owning same-day names from the same top-25%-turnover eligible universe. Each random control preserves the exact number of signal candidates on every signal date.

## Design

- baseline: canonical 250-session breakout candidates on common support.
- controls: same-date random non-breakout names from the same eligible top-25%-turnover universe.
- random seeds fixed before this run: 101, 202, 303.
- each control preserves baseline candidate count on every signal date.
- accounting, RAW execution, portfolio policy, CA handling, PIT exclusions, board lot, and zero-friction assumptions are unchanged.

## Results

| Scenario | Signals | Entries | Stop exits | Max-hold exits | Blocked exits | Final NAV | CAGR | Max DD | Sharpe | Final NAV vs baseline | CAGR delta pp |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline_common_support | 35,569 | 215 | 140 | 65 | 15 | 63,265,479.54 | 19.20% | -49.54% | 0.895 | 0.00% | 0.00 |
| matched_random_seed101 | 35,569 | 216 | 139 | 67 | 24 | 42,771,560.33 | 14.84% | -38.19% | 0.792 | -32.39% | -4.36 |
| matched_random_seed202 | 35,569 | 216 | 138 | 68 | 16 | 69,946,521.38 | 20.34% | -36.50% | 1.019 | 10.56% | 1.14 |
| matched_random_seed303 | 35,569 | 208 | 135 | 63 | 37 | 74,544,560.28 | 21.07% | -38.54% | 0.989 | 17.83% | 1.88 |

## Control summary

- random-control CAGR range: 14.84% to 21.07%
- baseline CAGR: 19.20%
- random controls above baseline CAGR: 2 / 3

## Operational gates

| Gate | Result |
|---|---|
| all_prespecified_runs_complete | PASS |
| per_date_signal_counts_matched | PASS |
| common_support_exclusion_active | PASS |
| all_nav_positive | PASS |

## Interpretation boundary

This is a diagnostic, not a promotion rule. If matched random controls perform similarly to or better than the breakout baseline, that is adverse evidence for breakout-specific information under the present portfolio policy. No control result is used to select or retune the strategy.
