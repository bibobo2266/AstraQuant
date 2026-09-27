# Source Full-History Canonical Accounting Probe

Status: **PASS**

Scope: 2330 observed/valid RAW sessions from 2015 through 2026.
Purpose: exercise the chronological AstraQuant canonical runner across the full frozen history range.
This is not a strategy backtest and no return/risk statistic is an acceptance criterion.

## Historical span

- first replay session: 2015-01-05
- final replay session: 2026-09-24
- sessions replayed / RAW NAV snapshots: 2,859
- entry: 2015-01-05 RAW open
- exit: 2026-09-22 RAW close
- starting shares: 100.0
- cumulative explicit share multiplier: 1.0
- exit shares: 100.0
- cash-dividend events applied: 28
- share-multiplier events applied: 0
- total corporate actions applied: 28

## Sessions by year

| Year | Sessions / RAW snapshots |
|---:|---:|
| 2015 | 244 |
| 2016 | 244 |
| 2017 | 246 |
| 2018 | 247 |
| 2019 | 242 |
| 2020 | 245 |
| 2021 | 244 |
| 2022 | 246 |
| 2023 | 239 |
| 2024 | 242 |
| 2025 | 243 |
| 2026 | 177 |

## Gates

| Gate | Result |
|---|---|
| calendar_starts_2015 | PASS |
| calendar_ends_2026 | PASS |
| all_years_present | PASS |
| session_snapshots_complete | PASS |
| entry_and_exit_executed | PASS |
| all_corporate_actions_applied | PASS |
| trade_settlements_completed | PASS |
| position_flat_final | PASS |
| pending_payables_zero | PASS |
| final_market_value_zero | PASS |
| raw_only_execution | PASS |
| canonical_historical_runner_used | PASS |

## Final accounting state

- settled cash: 10231950.0
- pending receivables: 9699.934878
- pending payables: 0.0
- final RAW market value: 0.0
- final NAV: 10241649.934878

Dividend receivables can remain outstanding because the canonical source ledger does not provide payment dates. They are retained in NAV and never converted to settled cash using guessed dates.

## Limitation

This full-history probe validates the canonical accounting/runtime path on one continuously held source security. It does not migrate the legacy strategy's signal-generation logic. Performance remains locked until strategy intents are fed through this canonical historical runner under declared PIT signal semantics.
