# Frozen Canonical Falsification / Placebo Diagnostic

Status: **PASS**

Purpose: keep the canonical execution/accounting/policy fixed while deliberately breaking the stock-date relationship in the breakout signals. This is a falsification diagnostic, not an OOS test and not a strategy-selection exercise.

## Prespecified runs

- baseline_common_support: canonical 250-session breakout signals, with PIT exclusions plus 2823 common-support exclusion.
- placebo_permute_tickers_seed1729: preserve signal dates and ticker marginal counts but deterministically permute ticker assignments.
- placebo_permute_dates_seed31415: preserve ticker identities and date marginal counts but deterministically permute signal dates.
- policy remains 10% NAV target, max 10 positions, 12% RAW stop, 20-session re-entry gap, 250-session max hold, 1000-share lot, seed 0.
- execution remains zero explicit fees / zero slippage to isolate signal falsification.

## Results

| Scenario | Signals | Entries | Stop exits | Max-hold exits | Final NAV | Total return | CAGR | Max DD | Sharpe | Final NAV vs baseline | CAGR delta pp |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline_common_support | 35,569 | 215 | 140 | 65 | 63,265,479.54 | 532.65% | 19.20% | -49.54% | 0.895 | 0.00% | 0.00 |
| placebo_permute_tickers_seed1729 | 35,159 | 172 | 88 | 75 | 159,705,927.32 | 1497.06% | 30.18% | -37.42% | 1.394 | 152.44% | 10.98 |
| placebo_permute_dates_seed31415 | 35,140 | 169 | 85 | 74 | 120,994,531.23 | 1109.95% | 26.79% | -28.70% | 1.380 | 91.25% | 7.59 |

## Operational gates

| Gate | Result |
|---|---|
| all_prespecified_runs_complete | PASS |
| base_signals_nonempty | PASS |
| placebos_nonempty | PASS |
| common_support_exclusion_active | PASS |

## Interpretation boundary

A placebo result is informative only as a falsification diagnostic. No pass/fail threshold for economic superiority was preregistered before observing these results, so this report does not claim that the strategy has formally survived falsification. It records whether breaking the stock-date mapping materially changes the descriptive path.
