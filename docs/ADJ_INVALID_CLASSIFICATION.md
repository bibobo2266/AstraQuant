# Adjusted Invalid OHLC Classification

Status: **PASS_CANONICAL_MASK_REQUIRED**

Purpose: determine whether invalid adjusted OHLC rows are source defects or rows already excluded by execution/tradability semantics.

| Year | Numeric ADJ rows | Invalid ADJ | Any nonpositive | Close nonpositive | Geometry bad | Missing tradability | Buy blocked | Sell blocked | observed_trade=False | Tradability says valid |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2015 | 256,533 | 14,773 | 5 | 0 | 14,773 | 3,579 | 11,194 | 11,194 | -25,967 | 0 |
| 2016 | 429,836 | 21,182 | 13 | 0 | 21,182 | 6,165 | 15,017 | 15,017 | -36,199 | 0 |
| 2017 | 445,585 | 19,926 | 16 | 0 | 19,926 | 7,274 | 12,652 | 12,652 | -32,578 | 0 |
| 2018 | 458,599 | 21,145 | 21 | 0 | 21,145 | 8,338 | 12,807 | 12,807 | -33,952 | 0 |
| 2019 | 458,783 | 19,916 | 23 | 0 | 19,916 | 9,468 | 10,448 | 10,448 | -30,364 | 0 |
| 2020 | 473,564 | 22,001 | 19 | 0 | 22,001 | 11,399 | 10,602 | 10,602 | -32,603 | 0 |
| 2021 | 483,027 | 20,839 | 38 | 0 | 20,839 | 11,716 | 9,123 | 9,123 | -29,962 | 0 |
| 2022 | 500,965 | 23,608 | 40 | 0 | 23,608 | 13,696 | 9,912 | 9,912 | -33,520 | 0 |
| 2023 | 499,544 | 21,450 | 54 | 0 | 21,450 | 13,477 | 7,973 | 7,973 | -29,423 | 0 |
| 2024 | 525,012 | 23,074 | 94 | 0 | 23,074 | 15,493 | 7,581 | 7,581 | -30,655 | 0 |
| 2025 | 547,471 | 25,362 | 80 | 0 | 25,362 | 19,343 | 6,019 | 6,019 | -31,381 | 0 |
| 2026 | 409,964 | 17,656 | 18 | 0 | 17,656 | 16,678 | 978 | 978 | -18,634 | 0 |

## Decision rule

- If invalid adjusted rows are never marked valid by tradability, do not reopen source remediation solely for these rows.
- Canonical research construction must mask/exclude invalid or non-tradable stock-days before technical-feature computation.
- Rows lacking tradability coverage remain excluded from execution and require explicit research-universe handling.

## Next small task

Audit PIT/reference datasets for temporal keys and null/order constraints.
