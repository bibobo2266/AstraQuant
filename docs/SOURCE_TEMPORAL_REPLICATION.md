# Frozen Canonical Temporal Replication

Status: **PASS**

Purpose: rerun the exact audited strategy configuration from fresh capital in non-overlapping historical eras. No strategy parameter is re-estimated or tuned between eras. This is temporal replication evidence, not locked future OOS.

## Frozen configuration

- parent signal horizon: 2016-01-04 through 2026-06-30
- each era starts from TWD 10,000,000 fresh capital
- policy unchanged: 10% NAV target, max 10 positions, 12% RAW stop, 20-session re-entry gap, 250-session max hold, 1000-share lot, seed 0
- execution assumptions unchanged: zero explicit fees and zero slippage
- normalized CA, PIT quarantine, payment settlement, terminal-security rules unchanged

## Era results

| Era | Simulation dates | Signals | Entries | Stop exits | Max-hold exits | Final NAV | Total return | CAGR | Max DD | Sharpe | Positive sessions |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| era_2016_2019 | 2016-01-04→2020-01-08 | 11,360 | 70 | 33 | 27 | 16,925,933.50 | 69.26% | 14.02% | -20.74% | 1.005 | 49.14% |
| era_2020_2022 | 2020-01-02→2023-01-09 | 9,834 | 92 | 64 | 18 | 11,195,910.35 | 11.96% | 3.81% | -34.85% | 0.280 | 53.72% |
| era_2023_2026H1 | 2023-01-03→2026-07-07 | 14,448 | 72 | 44 | 18 | 36,235,540.69 | 262.36% | 44.35% | -24.89% | 1.600 | 54.74% |

## Source-quality/activity counts

| Era | PIT-unsafe tickers quarantined | Signal rows removed | Blocked exits | CA applied | CA payments settled |
|---|---:|---:|---:|---:|---:|
| era_2016_2019 | 3 | 21 | 8 | 4,292 | 3,626 |
| era_2020_2022 | 0 | 0 | 5 | 3,341 | 2,946 |
| era_2023_2026H1 | 1 | 5 | 2 | 4,256 | 3,514 |

## Operational gate

- all non-overlapping era runs completed under the frozen canonical path: PASS

## Interpretation boundary

The era statistics are reported without choosing a winning period or changing parameters. Temporal differences are evidence to investigate, not a basis for retrospective tuning. Formal OOS remains locked until a future period is reserved and not iterated on.
