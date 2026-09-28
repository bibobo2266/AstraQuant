# Source 2823 Share-Conversion Audit

Purpose: verify successor-security RAW/tradability coverage around the 2823 -> 2883 + 2883B + cash conversion.

## RAW observations

      date stock_id  open   max   min  close
2021-12-15     2823 30.80 30.85 30.50  30.60
2021-12-16     2823 30.65 30.80 30.40  30.50
2021-12-17     2823 30.50 31.00 30.45  30.55
2021-12-15     2883 16.55 16.65 16.45  16.55
2021-12-16     2883 16.65 16.65 16.45  16.50
2021-12-17     2883 16.50 17.00 16.50  16.85
2021-12-20     2883 16.85 16.95 16.55  16.55
2021-12-21     2883 16.50 16.75 16.45  16.60
2021-12-22     2883 16.65 16.70 16.50  16.65
2021-12-23     2883 16.65 16.75 16.55  16.70
2021-12-24     2883 16.75 16.95 16.70  16.85
2021-12-27     2883 16.90 16.95 16.85  16.90
2021-12-28     2883 16.95 17.10 16.90  17.10
2021-12-29     2883 17.20 17.60 17.15  17.60
2021-12-30     2883 17.55 17.60 17.35  17.50
2022-01-03     2883 17.50 17.50 17.00  17.15
2022-01-04     2883 17.05 17.20 17.00  17.10
2022-01-05     2883 17.05 17.35 17.00  17.20
2022-01-06     2883 17.15 17.35 17.10  17.25
2022-01-07     2883 17.30 17.45 17.20  17.30
2021-12-30    2883B  9.39  9.68  9.22   9.59
2022-01-03    2883B  9.50  9.52  9.36   9.39
2022-01-04    2883B  9.39  9.43  9.32   9.36
2022-01-05    2883B  9.30  9.33  9.23   9.24
2022-01-06    2883B  9.19  9.21  9.12   9.15
2022-01-07    2883B  9.10  9.14  9.00   9.03

## Tradability observations

      date stock_id  observed_trade  valid_ohlc  buy_blocked  sell_blocked   reason
2021-12-15     2823            True        True        False         False OBSERVED
2021-12-16     2823            True        True        False         False OBSERVED
2021-12-17     2823            True        True        False         False OBSERVED
2021-12-15     2883            True        True        False         False OBSERVED
2021-12-16     2883            True        True        False         False OBSERVED
2021-12-17     2883            True        True        False         False OBSERVED
2021-12-20     2883            True        True        False         False OBSERVED
2021-12-21     2883            True        True        False         False OBSERVED
2021-12-22     2883            True        True        False         False OBSERVED
2021-12-23     2883            True        True        False         False OBSERVED
2021-12-24     2883            True        True        False         False OBSERVED
2021-12-27     2883            True        True        False         False OBSERVED
2021-12-28     2883            True        True        False         False OBSERVED
2021-12-29     2883            True        True        False         False OBSERVED
2021-12-30     2883            True        True        False         False OBSERVED
2022-01-03     2883            True        True        False         False OBSERVED
2022-01-04     2883            True        True        False         False OBSERVED
2022-01-05     2883            True        True        False         False OBSERVED
2022-01-06     2883            True        True        False         False OBSERVED
2022-01-07     2883            True        True        False         False OBSERVED

## 2823 summary

- RAW rows in window: 3
- first RAW date: 2021-12-15
- last RAW date: 2021-12-17

## 2883 summary

- RAW rows in window: 17
- first RAW date: 2021-12-15
- last RAW date: 2022-01-07

## 2883B summary

- RAW rows in window: 6
- first RAW date: 2021-12-30
- last RAW date: 2022-01-07
