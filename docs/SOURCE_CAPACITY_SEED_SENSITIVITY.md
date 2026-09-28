# Capacity-Selection Seed Sensitivity

Status: **PASS**

Purpose: isolate how much the deterministic random tie-breaking used when eligible candidates exceed available portfolio slots changes the path of the frozen common-support breakout strategy.

## Design

- signal set is identical across runs: canonical 250-session breakout on common support.
- only PortfolioIntentPolicy.random_seed changes.
- prespecified seeds: 0, 1, 7, 42, 101, 999.
- all accounting, RAW execution, CA handling, sizing, stop, max-hold, re-entry, board-lot, and zero-friction assumptions remain fixed.

## Results

| Seed | Entries | Stop exits | Max-hold exits | Blocked exits | Final NAV | Total return | CAGR | Max DD | Sharpe | Final NAV vs seed0 | CAGR delta pp |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 215 | 140 | 65 | 15 | 63,265,479.54 | 532.65% | 19.20% | -49.54% | 0.895 | 0.00% | 0.00 |
| 1 | 202 | 126 | 66 | 17 | 48,932,730.77 | 389.33% | 16.32% | -28.39% | 0.825 | -22.65% | -2.88 |
| 7 | 221 | 142 | 68 | 12 | 57,412,423.75 | 474.12% | 18.10% | -39.44% | 0.905 | -9.25% | -1.10 |
| 42 | 219 | 144 | 65 | 20 | 44,004,710.06 | 340.05% | 15.15% | -36.77% | 0.778 | -30.44% | -4.05 |
| 101 | 211 | 132 | 69 | 14 | 66,657,066.38 | 566.57% | 19.79% | -32.43% | 0.983 | 5.36% | 0.59 |
| 999 | 201 | 124 | 67 | 16 | 50,746,272.85 | 407.46% | 16.72% | -38.69% | 0.867 | -19.79% | -2.48 |

## Dispersion summary

- CAGR range across seeds: 15.15% to 19.79%
- CAGR spread: 4.64 percentage points
- final NAV range: 44,004,710.06 to 66,657,066.38

## Operational gates

| Gate | Result |
|---|---|
| all_prespecified_seeds_complete | PASS |
| seed0_present | PASS |
| all_nav_positive | PASS |
| common_support_exclusion_active | PASS |

## Interpretation boundary

This is a path-dependence diagnostic. No seed is selected or promoted. Large dispersion means capacity tie-breaking is a material source of portfolio outcomes and must be separated from signal-specific evidence before any candidate freeze or OOS claim.
