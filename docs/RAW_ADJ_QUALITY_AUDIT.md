# RAW / Adjusted Daily Price Quality Audit

Status: **PASS_WITH_SCOPE_LIMITATION**

Scope: targeted intrinsic quality checks for yearly RAW and adjusted daily price parquet files.
This task does not validate corporate-action economics or decide whether RAW and adjusted universes must be identical.

## Intrinsic file checks

| Kind | Year | Rows | Unique tickers | Numeric-stock rows | Key-null rows | Duplicate (date,stock_id) | Off-year rows | open null | high/max null | low/min null | close null |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| RAW | 2015 | 413,367 | 1,787 | 399,549 | 0 | 0 | 0 | 6895 | 6895 | 6895 | 6895 |
| RAW | 2016 | 436,698 | 1,851 | 419,225 | 0 | 0 | 0 | 8221 | 8221 | 8221 | 8221 |
| RAW | 2017 | 457,479 | 1,923 | 430,347 | 0 | 0 | 0 | 7334 | 7334 | 7334 | 7334 |
| RAW | 2018 | 477,096 | 1,998 | 438,560 | 0 | 0 | 0 | 9304 | 9304 | 9304 | 9304 |
| RAW | 2019 | 490,775 | 2,100 | 433,863 | 0 | 0 | 0 | 9425 | 9425 | 9425 | 9425 |
| RAW | 2020 | 511,972 | 2,143 | 443,642 | 0 | 0 | 0 | 8435 | 8435 | 8435 | 8435 |
| RAW | 2021 | 518,635 | 2,178 | 447,262 | 0 | 0 | 0 | 8180 | 8180 | 8180 | 8180 |
| RAW | 2022 | 533,447 | 2,221 | 457,845 | 0 | 0 | 0 | 10134 | 10134 | 10134 | 10134 |
| RAW | 2023 | 526,898 | 2,257 | 451,760 | 0 | 0 | 0 | 7186 | 7186 | 7186 | 7186 |
| RAW | 2024 | 548,690 | 2,330 | 468,841 | 0 | 0 | 0 | 5776 | 5776 | 5776 | 5776 |
| RAW | 2025 | 568,953 | 2,387 | 480,661 | 0 | 0 | 0 | 8451 | 8451 | 8451 | 8451 |
| RAW | 2026 | 421,888 | 2,414 | 350,738 | 0 | 0 | 0 | 4826 | 4826 | 4826 | 4826 |
| ADJ | 2015 | 269,798 | 1,842 | 256,533 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ADJ | 2016 | 455,344 | 1,930 | 429,836 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ADJ | 2017 | 480,938 | 2,023 | 445,585 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ADJ | 2018 | 505,260 | 2,118 | 458,599 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ADJ | 2019 | 522,786 | 2,244 | 458,783 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ADJ | 2020 | 554,451 | 2,340 | 473,564 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ADJ | 2021 | 561,939 | 2,370 | 483,027 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ADJ | 2022 | 583,849 | 2,441 | 500,965 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ADJ | 2023 | 582,674 | 2,534 | 499,544 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ADJ | 2024 | 616,320 | 2,654 | 525,012 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ADJ | 2025 | 643,323 | 2,734 | 547,471 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ADJ | 2026 | 488,425 | 2,850 | 409,964 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

## Numeric 4-digit stock key overlap

This table is descriptive. Differences can be legitimate because the two coordinates may have different historical coverage/universe rules.

| Year | RAW keys | ADJ keys | Intersection | ADJ keys missing RAW | RAW keys missing ADJ |
|---:|---:|---:|---:|---:|---:|
| 2015 | 399549 | 256533 | 247499 | 9034 | 152050 |
| 2016 | 419225 | 429836 | 412857 | 16979 | 6368 |
| 2017 | 430347 | 445585 | 425600 | 19985 | 4747 |
| 2018 | 438560 | 458599 | 435544 | 23055 | 3016 |
| 2019 | 433863 | 458783 | 432617 | 26166 | 1246 |
| 2020 | 443642 | 473564 | 443406 | 30158 | 236 |
| 2021 | 447262 | 483027 | 447256 | 35771 | 6 |
| 2022 | 457845 | 500965 | 457822 | 43143 | 23 |
| 2023 | 451760 | 499544 | 451726 | 47818 | 34 |
| 2024 | 468841 | 525012 | 468839 | 56173 | 2 |
| 2025 | 480661 | 547471 | 480661 | 66810 | 0 |
| 2026 | 350738 | 409964 | 350710 | 59254 | 28 |

## Hard-gate definition for this task

- key-null rows must be 0
- duplicate (date, stock_id) rows must be 0
- yearly files must not contain off-year dates

Price null/nonpositive counts are reported separately and require semantic interpretation before becoming hard failures.
RAW/ADJ key-set mismatch is not automatically a failure; execution eligibility is governed by the frozen historical-eligibility gate.

## Next small task

If intrinsic keys pass, audit price-value validity and RAW/ADJ overlap semantics on the eligible stock-day denominator before moving to reference/fundamental quality checks.
