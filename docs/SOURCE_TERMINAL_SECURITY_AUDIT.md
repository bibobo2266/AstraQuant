# Source Terminal Security Audit

- ticker: 2823
- target date: 2021-12-20

## finmind_suspended.parquet

- rows: 347
- columns: date, stock_id, suspension_time, resumption_date, resumption_time
- ticker rows: 1

TEXT_BEGIN
      date stock_id suspension_time resumption_date resumption_time
2017-10-19     2823            8:00      2017-10-20            8:00
TEXT_END

## universe.parquet

- rows: 3,149
- columns: stock_id, stock_name, industry_category, type, industry_fine, industry_all
- ticker rows: 1

TEXT_BEGIN
stock_id stock_name industry_category type industry_fine industry_all
    2823         中壽              金融保險 twse          金融保險         金融保險
TEXT_END

## RAW terminal span

- first RAW date: 2020-01-02
- last RAW date: 2021-12-17
- RAW rows: 480

### Last 10 RAW rows

TEXT_BEGIN
      date stock_id  open   max   min  close
2021-12-06     2823 30.70 30.80 30.45  30.70
2021-12-07     2823 30.70 30.85 30.60  30.85
2021-12-08     2823 30.90 30.95 30.65  30.70
2021-12-09     2823 30.75 30.90 30.70  30.80
2021-12-10     2823 30.80 31.00 30.75  30.80
2021-12-13     2823 30.85 31.00 30.85  30.95
2021-12-14     2823 30.90 30.90 30.70  30.85
2021-12-15     2823 30.80 30.85 30.50  30.60
2021-12-16     2823 30.65 30.80 30.40  30.50
2021-12-17     2823 30.50 31.00 30.45  30.55
TEXT_END

