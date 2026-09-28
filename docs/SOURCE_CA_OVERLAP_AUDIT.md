# Source Corporate-Action Overlap Audit

Status: **PASS_WITH_DEDUP_REQUIRED**

Purpose: determine whether dividend and official ex_right_dividend rows can represent the same economic event and would therefore double-count cash/share effects if consumed independently.

- total ledger rows: 41,224
- same ticker/date groups containing both event types: 3
- overlap groups with cash populated on both representations: 0
- cash values agreeing within 1e-6: 0
- cash values conflicting: 0
- overlap groups containing TPEx exDailyQ official rows: 0
- overlap groups in 2026-01-02 through 2026-04-02: 0

## Sample overlap groups

| Ticker | Date | dividend cash | ex_right cash | dividend rights_ratio | ex_right multiplier | dividend source | ex_right source |
|---|---|---|---|---|---|---|---|
| 1219 | 2024-07-03 | [0.5] | [] | [0.0] | [] | FinMind TaiwanStockDividend | TWSE TWT49U |
| 2636 | 2021-09-03 | [0.0] | [] | [0.0] | [] | FinMind TaiwanStockDividend | TWSE TWT49U |
| 3056 | 2022-06-29 | [1.5] | [] | [0.0] | [] | FinMind TaiwanStockDividend | TWSE TWT49U |

## Consumer implication

Rows that describe the same ticker/date dividend/ex-right event must be normalized into one economic event before portfolio accounting. They must not be independently accrued.

Official exchange values should be preferred for economic cash/share fields when populated. FinMind dividend rows may supply known/announcement timing and detailed fields where the exchange row lacks them, but that provenance merge must not duplicate the economic event.
