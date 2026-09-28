# Source Terminal Security Audit

- ticker: 5305
- target date: 2020-11-24

## finmind_suspended.parquet

- rows: 347
- columns: date, stock_id, suspension_time, resumption_date, resumption_time
- ticker rows: 0

## universe.parquet

- rows: 3,149
- columns: stock_id, stock_name, industry_category, type, industry_fine, industry_all
- ticker rows: 1

TEXT_BEGIN
stock_id stock_name industry_category type industry_fine industry_all
    5305         敦南              半導體業 twse          半導體業    半導體業;電子工業
TEXT_END

## RAW terminal span

- first RAW date: 2019-01-02
- last RAW date: 2020-11-23
- RAW rows: 459

### Last 10 RAW rows

TEXT_BEGIN
      date stock_id  open   max   min  close
2020-11-10     5305 42.25 42.30 42.20  42.25
2020-11-11     5305 42.25 42.25 42.20  42.20
2020-11-12     5305 42.25 42.25 42.20  42.25
2020-11-13     5305 42.25 42.30 42.25  42.30
2020-11-16     5305 42.30 42.35 42.25  42.25
2020-11-17     5305 42.35 42.35 42.25  42.30
2020-11-18     5305 42.30 42.30 42.25  42.30
2020-11-19     5305 42.30 42.30 42.25  42.25
2020-11-20     5305 42.30 42.35 42.25  42.25
2020-11-23     5305 42.35 42.35 42.30  42.30
TEXT_END

