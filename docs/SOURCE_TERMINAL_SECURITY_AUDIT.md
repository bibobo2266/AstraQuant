# Source Terminal Security Audit

- ticker: 4141
- target date: 2022-04-27

## finmind_suspended.parquet

- rows: 347
- columns: date, stock_id, suspension_time, resumption_date, resumption_time
- ticker rows: 1

TEXT_BEGIN
      date stock_id suspension_time resumption_date resumption_time
2021-12-21     4141            8:00      2021-12-22            8:00
TEXT_END

## universe.parquet

- rows: 3,149
- columns: stock_id, stock_name, industry_category, type, industry_fine, industry_all
- ticker rows: 1

TEXT_BEGIN
stock_id stock_name industry_category type industry_fine industry_all
    4141      龍燈-KY             生技醫療業 twse         生技醫療業 生技醫療業;化學生技醫療
TEXT_END

## RAW terminal span

- first RAW date: 2021-01-04
- last RAW date: 2022-04-26
- RAW rows: 316

### Last 10 RAW rows

TEXT_BEGIN
      date stock_id  open   max   min  close
2022-04-13     4141 26.00 26.10 26.00  26.10
2022-04-14     4141 26.05 26.10 26.05  26.10
2022-04-15     4141 26.10 26.10 26.05  26.05
2022-04-18     4141 26.05 26.10 26.05  26.05
2022-04-19     4141 26.05 26.10 26.05  26.10
2022-04-20     4141 26.10 26.10 26.05  26.05
2022-04-21     4141 26.05 26.10 26.05  26.10
2022-04-22     4141 26.10 26.10 26.05  26.05
2022-04-25     4141 26.10 26.15 26.05  26.10
2022-04-26     4141 26.10 26.15 26.10  26.10
TEXT_END

