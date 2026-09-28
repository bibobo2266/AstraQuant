# Frozen Canonical Starting-Capital Sensitivity

Status: **PASS**

Purpose: rerun the exact audited canonical strategy with different starting capital while keeping all strategy, board-lot, execution, accounting, CA, PIT, and random-seed rules fixed.

## Frozen rules

- signal window: 2016-01-04 through 2026-06-30
- simulation/drain horizon: 2016-01-04 through 2026-07-07
- signals supplied: 35,592
- PIT-unsafe CA tickers quarantined: 4
- signal rows removed by PIT quarantine: 76
- position target remains 10% of NAV
- max positions remains 10
- board lot remains 1,000 shares
- stop remains 12%
- re-entry gap remains 20 sessions
- max hold remains 250 sessions
- zero explicit fees / zero slippage for comparability with the descriptive baseline

## Results

| Starting capital | Final NAV | Total return | CAGR | Max DD | Sharpe | Entries | Stop exits | Max-hold exits | Blocked exits | Open positions | Ending payables |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 300,000 | 2,337,150.11 | 679.05% | 21.58% | -34.99% | 1.035 | 204 | 126 | 67 | 8 | 10 | 0.000000000 |
| 500,000 | 4,158,958.56 | 731.79% | 22.34% | -41.13% | 1.047 | 214 | 137 | 66 | 17 | 10 | 0.000000000 |
| 1,000,000 | 5,730,138.86 | 473.01% | 18.08% | -37.72% | 0.912 | 183 | 102 | 71 | 12 | 10 | -0.000000000 |
| 10,000,000 | 51,696,620.30 | 416.97% | 16.93% | -36.42% | 0.794 | 215 | 140 | 65 | 19 | 9 | 0.000000000 |

## Interpretation boundary

This is a capital/lot-size sensitivity test. With a fixed 1,000-share board lot and a 10% NAV target, smaller accounts can be unable to buy otherwise eligible signals. Therefore percentage returns need not scale linearly with starting capital.

## Gates

| Gate | Result |
|---|---|
| all_capital_scenarios_complete | PASS |
| all_final_nav_positive | PASS |
| all_pending_payables_nonnegative_with_float_tolerance | PASS |
| pit_unsafe_ca_tickers_excluded | PASS |
| baseline_10m_present | PASS |
