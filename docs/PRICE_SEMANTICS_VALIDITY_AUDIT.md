# Price Semantics Validity Audit

Status: **FAIL**

Purpose: verify that RAW price anomalies are explicitly blocked by the tradability layer and that adjusted OHLC is internally valid.

Frozen execution-readiness gate: READY — historical TWSE/TPEx eligible adjusted stock-day coverage=100.0000% (4,893,591/4,893,591); missing=0

## RAW vs tradability

| Year | Numeric RAW rows | Any OHLC null | Calculated invalid OHLC | Missing tradability row | Validity disagreement | Null but buy allowed | Null but sell allowed | Invalid but buy allowed |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2015 | 399,549 | 5,762 | 17,030 | 0 | 0 | 0 | 0 | 0 |
| 2016 | 419,225 | 6,835 | 22,007 | 0 | 0 | 0 | 0 | 0 |
| 2017 | 430,347 | 5,477 | 18,394 | 0 | 0 | 0 | 0 | 0 |
| 2018 | 438,560 | 7,047 | 20,082 | 0 | 0 | 0 | 0 | 0 |
| 2019 | 433,863 | 6,848 | 17,585 | 0 | 0 | 0 | 0 | 0 |
| 2020 | 443,642 | 5,269 | 16,000 | 0 | 0 | 0 | 0 | 0 |
| 2021 | 447,262 | 3,837 | 13,036 | 0 | 0 | 0 | 0 | 0 |
| 2022 | 457,845 | 5,679 | 15,721 | 0 | 0 | 0 | 0 | 0 |
| 2023 | 451,760 | 3,660 | 11,685 | 0 | 0 | 0 | 0 | 0 |
| 2024 | 468,841 | 2,574 | 10,215 | 0 | 0 | 0 | 0 | 0 |
| 2025 | 480,661 | 4,907 | 11,096 | 0 | 0 | 0 | 0 | 0 |
| 2026 | 350,738 | 2,957 | 3,951 | 0 | 0 | 0 | 0 | 0 |

## Adjusted OHLC intrinsic validity

| Year | Numeric ADJ rows | Any OHLC null | Invalid OHLC |
|---:|---:|---:|---:|
| 2015 | 256,533 | 0 | 14,773 |
| 2016 | 429,836 | 0 | 21,182 |
| 2017 | 445,585 | 0 | 19,926 |
| 2018 | 458,599 | 0 | 21,145 |
| 2019 | 458,783 | 0 | 19,916 |
| 2020 | 473,564 | 0 | 22,001 |
| 2021 | 483,027 | 0 | 20,839 |
| 2022 | 500,965 | 0 | 23,608 |
| 2023 | 499,544 | 0 | 21,450 |
| 2024 | 525,012 | 0 | 23,074 |
| 2025 | 547,471 | 0 | 25,362 |
| 2026 | 409,964 | 0 | 17,656 |

## Gate

PASS requires:
- every numeric RAW row has a matching tradability row;
- independently calculated RAW OHLC validity agrees with tradability.valid_ohlc;
- RAW null/invalid OHLC rows are blocked from buying (and null rows are blocked from selling);
- adjusted numeric-stock OHLC has no null or invalid geometry in this scope.

This does not yet prove corporate-action accounting correctness or PIT safety of adjusted history.

## Next small task

Audit reference/PIT datasets (industry, corporate actions, tradability) for key uniqueness, required temporal fields, nulls, and ordering constraints.
