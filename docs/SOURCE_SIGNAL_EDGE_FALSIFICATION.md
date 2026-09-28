# Conditional 500-Permutation Signal-Edge Falsification

Status: **PASS**

Purpose: test breakout-specific cross-sectional information without portfolio-capacity randomization. Controls are sampled only from same-day actually-tradable names in the same top-25%-turnover eligible universe, preserving the baseline valid candidate count on every signal date.

## Design

- permutations: 500
- seed range: 170001 through 170500
- primary forward horizon: 250 market sessions after next-session entry
- entry outcome coordinate: next-market-session adjusted research open
- exit outcome coordinate: adjusted research close exactly 250 market sessions after entry
- adjusted prices are used here only for research/falsification outcome measurement; they are not execution/accounting prices
- control pool: same signal date, observed_trade=True, valid_ohlc=True, valid price geometry, positive turnover, top 25% turnover, common-support exclusions applied
- baseline breakout pairs are excluded from the same-day control pool
- no portfolio max-position rule, capacity lottery, cash sizing, or random slot selection is used in this diagnostic

## Baseline candidate-level statistics

- raw baseline signal pairs: 35,569
- valid fixed-horizon outcomes: 31,503
- valid-outcome coverage: 88.57%
- per-candidate expectancy: 18.6076%
- median return: 3.0683%
- win rate: 53.67%
- mean winner: 53.7248%
- mean loser: -22.0892%
- payoff ratio: 2.4322

## Empirical null distribution

- expectancy percentile of baseline: 100.00%
- 0 / 500 null permutations reached or exceeded baseline expectancy; with the finite-sample +1 convention the reported one-sided empirical p estimate is 1/501 = 0.0020, which is the resolution floor of this 500-permutation run rather than evidence that the exact p-value equals 0.0020
- win-rate percentile of baseline: 100.00%
- 0 / 500 null permutations reached or exceeded baseline win rate; with the finite-sample +1 convention the reported one-sided empirical p estimate is 1/501 = 0.0020, which is the resolution floor of this 500-permutation run rather than evidence that the exact p-value equals 0.0020

| Quantile | Expectancy | Win rate | Payoff ratio |
|---:|---:|---:|---:|
| 1% | 12.9645% | 49.85% | 2.1273 |
| 5% | 13.0997% | 50.11% | 2.1432 |
| 50% | 13.6755% | 50.56% | 2.1863 |
| 95% | 14.2007% | 50.94% | 2.2368 |
| 99% | 14.4519% | 51.13% | 2.2529 |

## Operational gates

| Gate | Result |
|---|---|
| 500_prespecified_permutations_complete | PASS |
| same_day_candidate_counts_preserved | PASS |
| same_day_tradable_top_turnover_pool_used | PASS |
| baseline_pairs_excluded_from_control_pool | PASS |
| common_support_exclusion_active | PASS |
| baseline_valid_outcomes_nonempty | PASS |

## Interpretation boundary

This diagnostic isolates candidate-level signal information and deliberately removes the portfolio-capacity lottery that confounded the earlier single-permutation portfolio placebo. It does not reproduce stop-loss, cash, settlement, or path-dependent portfolio mechanics and therefore is not an executable performance estimate. Portfolio-level seed sensitivity remains a separate diagnostic.
