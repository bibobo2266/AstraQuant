# Canonical Parquet Inventory

Status: **DONE — metadata inventory only**

This inventory is generated from a transient, read-only checkout of the frozen source repository.
It reads parquet footers/metadata only. It does not perform null, duplicate, or unique-ticker scans.

## Family summary

| Family | Parquet files | Total rows (sum of file metadata) | Size MiB | Distinct schema hashes |
|---|---:|---:|---:|---:|
| raw | 12 | 5,905,898 | 101.84 | 1 |
| adj | 13 | 6,279,698 | 162.72 | 3 |
| reference | 9 | 7,117,398 | 89.14 | 6 |
| fundamentals | 29 | 23,401,426 | 158.62 | 7 |
| inst | 14 | 33,683,482 | 224.51 | 3 |
| kbar | 8 | 21,453,337 | 127.14 | 1 |

## File inventory

| Family | File | Size MiB | Rows | Row groups | Columns | Schema hash | Date field | Min | Max | PIT fields | Provenance fields |
|---|---|---:|---:|---:|---:|---|---|---|---|---|---|
| raw | raw/prices_raw_2015.parquet | 7.08 | 413,367 | 1 | 11 | 545720821c39 | date | 2015-01-05 00:00:00 | 2015-12-31 00:00:00 | NONE OBSERVED | source |
| raw | raw/prices_raw_2016.parquet | 7.5 | 436,698 | 1 | 11 | 545720821c39 | date | 2016-01-04 00:00:00 | 2016-12-30 00:00:00 | NONE OBSERVED | source |
| raw | raw/prices_raw_2017.parquet | 7.94 | 457,479 | 1 | 11 | 545720821c39 | date | 2017-01-03 00:00:00 | 2017-12-29 00:00:00 | NONE OBSERVED | source |
| raw | raw/prices_raw_2018.parquet | 8.2 | 477,096 | 1 | 11 | 545720821c39 | date | 2018-01-02 00:00:00 | 2018-12-28 00:00:00 | NONE OBSERVED | source |
| raw | raw/prices_raw_2019.parquet | 8.29 | 490,775 | 1 | 11 | 545720821c39 | date | 2019-01-02 00:00:00 | 2019-12-31 00:00:00 | NONE OBSERVED | source |
| raw | raw/prices_raw_2020.parquet | 8.64 | 511,972 | 1 | 11 | 545720821c39 | date | 2020-01-02 00:00:00 | 2020-12-31 00:00:00 | NONE OBSERVED | source |
| raw | raw/prices_raw_2021.parquet | 8.94 | 518,635 | 1 | 11 | 545720821c39 | date | 2021-01-04 00:00:00 | 2021-12-30 00:00:00 | NONE OBSERVED | source |
| raw | raw/prices_raw_2022.parquet | 9.07 | 533,447 | 1 | 11 | 545720821c39 | date | 2022-01-03 00:00:00 | 2022-12-30 00:00:00 | NONE OBSERVED | source |
| raw | raw/prices_raw_2023.parquet | 9.06 | 526,898 | 1 | 11 | 545720821c39 | date | 2023-01-03 00:00:00 | 2023-12-29 00:00:00 | NONE OBSERVED | source |
| raw | raw/prices_raw_2024.parquet | 9.6 | 548,690 | 1 | 11 | 545720821c39 | date | 2024-01-02 00:00:00 | 2024-12-31 00:00:00 | NONE OBSERVED | source |
| raw | raw/prices_raw_2025.parquet | 9.9 | 568,953 | 1 | 11 | 545720821c39 | date | 2025-01-02 00:00:00 | 2025-12-31 00:00:00 | NONE OBSERVED | source |
| raw | raw/prices_raw_2026.parquet | 7.62 | 421,888 | 1 | 11 | 545720821c39 | date | 2026-01-02 00:00:00 | 2026-09-24 00:00:00 | NONE OBSERVED | source |
| adj | adj/dividend_events.parquet | 0.29 | 14,591 | 1 | 10 | ca40699ea952 | date | 2017-01-10 | 2026-08-28 | NONE OBSERVED | NONE OBSERVED |
| adj | adj/prices_adj_2015.parquet | 8.42 | 269,798 | 1 | 8 | 2f2e09090813 | date | 2015-06-01 | 2015-12-31 | NONE OBSERVED | NONE OBSERVED |
| adj | adj/prices_adj_2016.parquet | 12.07 | 455,344 | 1 | 8 | 2f2e09090813 | date | 2016-01-04 | 2016-12-30 | NONE OBSERVED | NONE OBSERVED |
| adj | adj/prices_adj_2017.parquet | 12.46 | 480,938 | 1 | 8 | 2f2e09090813 | date | 2017-01-03 | 2017-12-29 | NONE OBSERVED | NONE OBSERVED |
| adj | adj/prices_adj_2018.parquet | 13.18 | 505,260 | 1 | 8 | 2f2e09090813 | date | 2018-01-02 | 2018-12-28 | NONE OBSERVED | NONE OBSERVED |
| adj | adj/prices_adj_2019.parquet | 13.13 | 522,786 | 1 | 8 | 2f2e09090813 | date | 2019-01-02 | 2019-12-31 | NONE OBSERVED | NONE OBSERVED |
| adj | adj/prices_adj_2020.parquet | 14.75 | 554,451 | 1 | 8 | 2f2e09090813 | date | 2020-01-02 | 2020-12-31 | NONE OBSERVED | NONE OBSERVED |
| adj | adj/prices_adj_2021.parquet | 14.74 | 561,939 | 1 | 8 | 2f2e09090813 | date | 2021-01-04 | 2021-12-30 | NONE OBSERVED | NONE OBSERVED |
| adj | adj/prices_adj_2022.parquet | 15.07 | 583,849 | 1 | 8 | 2f2e09090813 | date | 2022-01-03 | 2022-12-30 | NONE OBSERVED | NONE OBSERVED |
| adj | adj/prices_adj_2023.parquet | 14.83 | 582,674 | 1 | 8 | 2f2e09090813 | date | 2023-01-03 | 2023-12-29 | NONE OBSERVED | NONE OBSERVED |
| adj | adj/prices_adj_2024.parquet | 15.74 | 616,320 | 1 | 8 | 2f2e09090813 | date | 2024-01-02 | 2024-12-31 | NONE OBSERVED | NONE OBSERVED |
| adj | adj/prices_adj_2025.parquet | 16.1 | 643,323 | 1 | 8 | 2f2e09090813 | date | 2025-01-02 | 2025-12-31 | NONE OBSERVED | NONE OBSERVED |
| adj | adj/prices_adj_2026.parquet | 11.94 | 488,425 | 1 | 8 | 3c01dd0876d9 | date | 2026-01-02 | 2026-09-24 | NONE OBSERVED | NONE OBSERVED |
| reference | reference/corporate_actions_ledger.parquet | 0.32 | 41,224 | 1 | 13 | ce30d3db078f | known_date | 2013-12-20 00:00:00 | 2026-09-24 00:00:00 | known_date | source_url, source_name |
| reference | reference/finmind_suspended.parquet | 0.01 | 347 | 1 | 5 | 27a1ad39150a | date | 2015-03-30 00:00:00 | 2026-08-13 00:00:00 | NONE OBSERVED | NONE OBSERVED |
| reference | reference/industry_monthly_snapshots.parquet | 0.1 | 252,239 | 1 | 10 | 4241f0ff7ba3 | available_date | 2015-01-14 00:00:00 | 2026-09-14 00:00:00 | available_date | source_url, source_name |
| reference | reference/industry_pit.parquet | 0.02 | 1,990 | 1 | 8 | 654243579899 | NONE | N/A | N/A | NONE OBSERVED | source_url |
| reference | reference/price_limit_2015.parquet | 1.33 | 255,524 | 1 | 5 | 437dae48a8a5 | date | 2015-06-01 00:00:00 | 2015-12-31 00:00:00 | NONE OBSERVED | NONE OBSERVED |
| reference | reference/price_limit_2016.parquet | 2.27 | 428,124 | 1 | 5 | 437dae48a8a5 | date | 2016-01-04 00:00:00 | 2016-12-30 00:00:00 | NONE OBSERVED | NONE OBSERVED |
| reference | reference/price_limit_2017.parquet | 2.36 | 444,061 | 1 | 5 | 437dae48a8a5 | date | 2017-01-03 00:00:00 | 2017-12-29 00:00:00 | NONE OBSERVED | NONE OBSERVED |
| reference | reference/price_limit_2018.parquet | 2.42 | 457,099 | 1 | 5 | 437dae48a8a5 | date | 2018-01-02 00:00:00 | 2018-12-28 00:00:00 | NONE OBSERVED | NONE OBSERVED |
| reference | reference/tradability.parquet | 80.31 | 5,236,790 | 5 | 20 | 2f04f9d3472e | date | 2015-01-05 00:00:00 | 2026-09-24 00:00:00 | NONE OBSERVED | source |
| fundamentals | fundamentals/balance_sheet.parquet | 32.75 | 6,386,271 | 7 | 5 | fc36b6a17333 | date | 2015-06-30 | 2026-06-30 | NONE OBSERVED | NONE OBSERVED |
| fundamentals | fundamentals/dividend.parquet | 0.45 | 18,557 | 1 | 23 | 8d84e5285868 | date | 2014-01-03 | 2026-11-11 | available_date | NONE OBSERVED |
| fundamentals | fundamentals/financials.parquet | 6.35 | 1,408,596 | 2 | 6 | 3dd37256228d | date | 2014-03-31 | 2026-06-30 | available_date | NONE OBSERVED |
| fundamentals | fundamentals/margin.parquet | 49.48 | 4,856,840 | 5 | 17 | b0a3466b7387 | date | 2014-01-02 | 2026-09-24 | available_date | NONE OBSERVED |
| fundamentals | fundamentals/market_value_2015.parquet | 1.7 | 235,440 | 1 | 3 | 3218c19ff0af | date | 2015-06-01 | 2015-12-31 | NONE OBSERVED | NONE OBSERVED |
| fundamentals | fundamentals/market_value_2016.parquet | 2.72 | 394,827 | 1 | 3 | 3218c19ff0af | date | 2016-01-04 | 2016-12-30 | NONE OBSERVED | NONE OBSERVED |
| fundamentals | fundamentals/market_value_2017.parquet | 2.87 | 421,119 | 1 | 3 | 3218c19ff0af | date | 2017-01-03 | 2017-12-29 | NONE OBSERVED | NONE OBSERVED |
| fundamentals | fundamentals/market_value_2018.parquet | 3.19 | 451,306 | 1 | 3 | 3218c19ff0af | date | 2018-01-02 | 2018-12-28 | NONE OBSERVED | NONE OBSERVED |
| fundamentals | fundamentals/market_value_2019.parquet | 3.23 | 466,631 | 1 | 3 | 3218c19ff0af | date | 2019-01-02 | 2019-12-31 | NONE OBSERVED | NONE OBSERVED |
| fundamentals | fundamentals/market_value_2020.parquet | 3.64 | 483,521 | 1 | 3 | 3218c19ff0af | date | 2020-01-02 | 2020-12-31 | NONE OBSERVED | NONE OBSERVED |
| fundamentals | fundamentals/market_value_2021.parquet | 3.65 | 486,856 | 1 | 3 | 3218c19ff0af | date | 2021-01-04 | 2021-12-30 | NONE OBSERVED | NONE OBSERVED |
| fundamentals | fundamentals/market_value_2022.parquet | 3.66 | 518,763 | 1 | 3 | 3218c19ff0af | date | 2022-01-03 | 2022-12-30 | NONE OBSERVED | NONE OBSERVED |
| fundamentals | fundamentals/market_value_2023.parquet | 3.88 | 565,152 | 1 | 3 | 3218c19ff0af | date | 2023-01-03 | 2023-12-29 | NONE OBSERVED | NONE OBSERVED |
| fundamentals | fundamentals/market_value_2024.parquet | 4.21 | 596,334 | 1 | 3 | 3218c19ff0af | date | 2024-01-02 | 2024-12-31 | NONE OBSERVED | NONE OBSERVED |
| fundamentals | fundamentals/market_value_2025.parquet | 4.46 | 627,301 | 1 | 3 | 3218c19ff0af | date | 2025-01-02 | 2025-12-31 | NONE OBSERVED | NONE OBSERVED |
| fundamentals | fundamentals/market_value_2026.parquet | 3.22 | 441,838 | 1 | 3 | 3218c19ff0af | date | 2026-01-02 | 2026-09-07 | NONE OBSERVED | NONE OBSERVED |
| fundamentals | fundamentals/month_revenue.parquet | 1.36 | 267,093 | 1 | 8 | d2958967e98f | date | 2014-01-01 | 2026-09-01 | available_date | NONE OBSERVED |
| fundamentals | fundamentals/stock_per_2015.parquet | 1.34 | 232,249 | 1 | 5 | 5a890583a1d2 | date | 2015-06-01 | 2015-12-31 | NONE OBSERVED | NONE OBSERVED |
| fundamentals | fundamentals/stock_per_2016.parquet | 2.24 | 388,490 | 1 | 5 | 5a890583a1d2 | date | 2016-01-04 | 2016-12-30 | NONE OBSERVED | NONE OBSERVED |
| fundamentals | fundamentals/stock_per_2017.parquet | 2.23 | 400,616 | 1 | 5 | 5a890583a1d2 | date | 2017-01-03 | 2017-12-29 | NONE OBSERVED | NONE OBSERVED |
| fundamentals | fundamentals/stock_per_2018.parquet | 2.37 | 411,734 | 1 | 5 | 5a890583a1d2 | date | 2018-01-02 | 2018-12-28 | NONE OBSERVED | NONE OBSERVED |
| fundamentals | fundamentals/stock_per_2019.parquet | 2.35 | 411,840 | 1 | 5 | 5a890583a1d2 | date | 2019-01-02 | 2019-12-31 | NONE OBSERVED | NONE OBSERVED |
| fundamentals | fundamentals/stock_per_2020.parquet | 2.43 | 420,274 | 1 | 5 | 5a890583a1d2 | date | 2020-01-02 | 2020-12-31 | NONE OBSERVED | NONE OBSERVED |
| fundamentals | fundamentals/stock_per_2021.parquet | 2.48 | 423,655 | 1 | 5 | 5a890583a1d2 | date | 2021-01-04 | 2021-12-30 | NONE OBSERVED | NONE OBSERVED |
| fundamentals | fundamentals/stock_per_2022.parquet | 2.55 | 432,902 | 1 | 5 | 5a890583a1d2 | date | 2022-01-03 | 2022-12-30 | NONE OBSERVED | NONE OBSERVED |
| fundamentals | fundamentals/stock_per_2023.parquet | 2.5 | 427,075 | 1 | 5 | 5a890583a1d2 | date | 2023-01-03 | 2023-12-29 | NONE OBSERVED | NONE OBSERVED |
| fundamentals | fundamentals/stock_per_2024.parquet | 2.63 | 443,882 | 1 | 5 | 5a890583a1d2 | date | 2024-01-02 | 2024-12-31 | NONE OBSERVED | NONE OBSERVED |
| fundamentals | fundamentals/stock_per_2025.parquet | 2.72 | 460,672 | 1 | 5 | 5a890583a1d2 | date | 2025-01-02 | 2025-12-31 | NONE OBSERVED | NONE OBSERVED |
| fundamentals | fundamentals/stock_per_2026.parquet | 1.96 | 321,592 | 1 | 5 | 5a890583a1d2 | date | 2026-01-02 | 2026-09-07 | NONE OBSERVED | NONE OBSERVED |
| inst | inst/futures_inst.parquet | 0.58 | 12,150 | 1 | 11 | 29948f7645e3 | date | 2018-06-05 | 2026-09-24 | NONE OBSERVED | NONE OBSERVED |
| inst | inst/stock_inst_2015.parquet | 1.74 | 197,406 | 1 | 8 | 6eaf2eba0ada | date | 2015-06-01 | 2015-12-31 | NONE OBSERVED | NONE OBSERVED |
| inst | inst/stock_inst_2016.parquet | 3.09 | 349,327 | 1 | 8 | 6eaf2eba0ada | date | 2016-01-04 | 2016-12-30 | NONE OBSERVED | NONE OBSERVED |
| inst | inst/stock_inst_2017.parquet | 4.56 | 581,461 | 1 | 8 | 6eaf2eba0ada | date | 2017-01-03 | 2017-12-29 | NONE OBSERVED | NONE OBSERVED |
| inst | inst/stock_inst_2018.parquet | 13.95 | 2,256,040 | 3 | 8 | 6eaf2eba0ada | date | 2018-01-02 | 2018-12-28 | NONE OBSERVED | NONE OBSERVED |
| inst | inst/stock_inst_2019.parquet | 13.79 | 2,268,002 | 3 | 8 | 6eaf2eba0ada | date | 2019-01-02 | 2019-12-31 | NONE OBSERVED | NONE OBSERVED |
| inst | inst/stock_inst_2020.parquet | 15.01 | 2,494,423 | 3 | 8 | 6eaf2eba0ada | date | 2020-01-02 | 2020-12-31 | NONE OBSERVED | NONE OBSERVED |
| inst | inst/stock_inst_2021.parquet | 24.38 | 3,829,637 | 4 | 8 | 6eaf2eba0ada | date | 2021-01-04 | 2021-12-30 | NONE OBSERVED | NONE OBSERVED |
| inst | inst/stock_inst_2022.parquet | 25.63 | 3,877,582 | 4 | 8 | 6eaf2eba0ada | date | 2022-01-03 | 2022-12-30 | NONE OBSERVED | NONE OBSERVED |
| inst | inst/stock_inst_2023.parquet | 27.6 | 4,138,089 | 4 | 8 | 6eaf2eba0ada | date | 2023-01-03 | 2023-12-29 | NONE OBSERVED | NONE OBSERVED |
| inst | inst/stock_inst_2024.parquet | 35.57 | 5,322,179 | 6 | 8 | 6eaf2eba0ada | date | 2024-01-02 | 2024-12-31 | NONE OBSERVED | NONE OBSERVED |
| inst | inst/stock_inst_2025.parquet | 32.0 | 4,613,008 | 5 | 8 | 6eaf2eba0ada | date | 2025-01-02 | 2025-12-31 | NONE OBSERVED | NONE OBSERVED |
| inst | inst/stock_inst_2026.parquet | 26.33 | 3,728,223 | 4 | 8 | 6eaf2eba0ada | date | 2026-01-02 | 2026-09-24 | NONE OBSERVED | NONE OBSERVED |
| inst | inst/total_inst.parquet | 0.28 | 15,955 | 1 | 4 | 05ea3614afcb | date | 2015-06-01 | 2026-09-24 | NONE OBSERVED | NONE OBSERVED |
| kbar | kbar/kbar_2019.parquet | 9.98 | 1,861,043 | 2 | 8 | 036e10b0db8d | date | 2019-01-02 | 2019-12-31 | NONE OBSERVED | NONE OBSERVED |
| kbar | kbar/kbar_2020.parquet | 18.31 | 3,111,146 | 3 | 8 | 036e10b0db8d | date | 2020-01-02 | 2020-12-31 | NONE OBSERVED | NONE OBSERVED |
| kbar | kbar/kbar_2021.parquet | 19.25 | 3,201,243 | 4 | 8 | 036e10b0db8d | date | 2021-01-04 | 2021-12-30 | NONE OBSERVED | NONE OBSERVED |
| kbar | kbar/kbar_2022.parquet | 11.84 | 1,986,292 | 2 | 8 | 036e10b0db8d | date | 2022-01-03 | 2022-12-30 | NONE OBSERVED | NONE OBSERVED |
| kbar | kbar/kbar_2023.parquet | 13.94 | 2,455,096 | 3 | 8 | 036e10b0db8d | date | 2023-01-03 | 2023-12-29 | NONE OBSERVED | NONE OBSERVED |
| kbar | kbar/kbar_2024.parquet | 16.3 | 2,831,734 | 3 | 8 | 036e10b0db8d | date | 2024-01-02 | 2024-12-31 | NONE OBSERVED | NONE OBSERVED |
| kbar | kbar/kbar_2025.parquet | 14.16 | 2,479,834 | 3 | 8 | 036e10b0db8d | date | 2025-01-02 | 2025-12-31 | NONE OBSERVED | NONE OBSERVED |
| kbar | kbar/kbar_2026.parquet | 23.36 | 3,526,949 | 4 | 8 | 036e10b0db8d | date | 2026-01-02 | 2026-09-18 | NONE OBSERVED | NONE OBSERVED |

## Interpretation limits

- Row totals are metadata sums, not deduplicated logical row counts.
- Date ranges depend on parquet statistics; NO_METADATA_STATS means a later targeted scan is required.
- Schema hashes detect structural differences but do not prove semantic compatibility.
- Nulls, duplicate keys, ticker coverage, PIT ordering, and cross-file reconciliation are separate tasks.

## Next small task

Run targeted key/null/duplicate checks by family, beginning with RAW and adjusted daily price files.
