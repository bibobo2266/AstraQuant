# Source Terminal Security Audit

- ticker: 6251
- target date: 2022-08-15

## finmind_suspended.parquet

- rows: 347
- columns: date, stock_id, suspension_time, resumption_date, resumption_time
- ticker rows: 1

TEXT_BEGIN
      date stock_id suspension_time resumption_date resumption_time
2019-10-18     6251            8:00      2019-10-21            8:00
TEXT_END

## universe.parquet

- rows: 3,149
- columns: stock_id, stock_name, industry_category, type, industry_fine, industry_all
- ticker rows: 1

TEXT_BEGIN
stock_id stock_name industry_category type industry_fine industry_all
    6251         定穎            電子零組件業 twse        電子零組件業  電子零組件業;電子工業
TEXT_END

## RAW terminal span

- first RAW date: 2021-01-04
- last RAW date: 2022-08-12
- RAW rows: 385

### Last 10 RAW rows

TEXT_BEGIN
      date stock_id  open   max   min  close
2022-08-01     6251 20.60 20.65 20.00  20.15
2022-08-02     6251 20.00 20.15 19.70  19.95
2022-08-03     6251 20.05 20.10 19.60  19.85
2022-08-04     6251 19.90 19.90 19.00  19.20
2022-08-05     6251 19.60 20.10 19.60  19.90
2022-08-08     6251 19.75 19.85 19.40  19.75
2022-08-09     6251 19.75 20.00 19.50  19.85
2022-08-10     6251 19.65 20.65 19.65  20.40
2022-08-11     6251 20.75 20.85 20.20  20.20
2022-08-12     6251 20.25 20.35 20.10  20.30
TEXT_END

