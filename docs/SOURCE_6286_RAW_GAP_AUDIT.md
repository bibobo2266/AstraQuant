# SOURCE 6286 RAW Gap Audit

Status: **BLOCKER_CONFIRMED — TERMINAL_CASH_CONVERSION_NOT_MODELED**

## Trigger

The first config-driven canonical VCP run failed at opening NAV on 2016-04-21:

```text
RAW mark for 6286 is not available: RAW_MISSING_OR_NONUNIQUE
```

The simulator correctly refused adjusted-price fallback, stale marking, or silent ticker exclusion.

## Read-only source audit

The source repository remains read-only.

`data/reference/tradability_coverage.csv` records:

```text
6286,2015-01-05,2016-04-20,313,312,1,1,0.9968051118210862
```

Therefore 2016-04-20 is the final canonical tradability date for 6286. The missing 2016-04-21 RAW mark is not an ordinary interior tape gap.

Public exchange/MOPS-derived disclosures state:

- last trading date: 2016-04-20;
- trading suspended from: 2016-04-21;
- delisting / share-conversion effective date: 2016-04-29;
- cash consideration: TWD 195 per share;
- expected payment date: 2016-05-05.

Sources:

- https://tw.stock.yahoo.com/news/%E5%80%8B%E8%82%A1-%E7%AB%8B%E9%8C%A1-6286-%E8%87%AA105%E5%B9%B44%E6%9C%8821%E6%97%A5%E5%81%9C%E6%AD%A2%E8%B2%B7%E8%B3%A3-4%E6%9C%8829%E6%97%A5%E7%B5%82%E6%AD%A2%E4%B8%8A%E5%B8%82-062307701.html
- https://news.cnyes.com/news/id/748023
- https://www.mediatek.com/hubfs/MediaTek%20Assets/Pdfs/Financial%20Reports/2016/%E7%AC%AC2%E5%AD%A3-%E5%90%88%E5%B9%B6%E8%B4%A2%E5%8A%A1%E6%8A%A5%E5%91%8A.pdf

## Remediation

No execution, accounting, corporate-action, valuation, or terminal-lifecycle algorithm is changed.

The existing generic terminal cash-conversion mechanism is populated with the audited 6286 event:

- `known_at = 2016-04-06 14:40`
- `terminal_stale_from = 2016-04-21`
- `effective_at = 2016-04-29`
- `payment_at = 2016-05-05`
- `cash_per_share = 195.0`

This is source-fact completion, not a fallback. The candidate universe, P2-060 exclusion set, signal definitions, and locked OOS governance remain unchanged.

## Required rerun

1. frozen breakout long-horizon regression must remain exactly 51,696,620.29773994;
2. VCP config run must pass canonical RAW/CA/FIFO reporting;
3. RSI config run must pass canonical RAW/CA/FIFO reporting;
4. all three reports must include the reusable total-return benchmark comparison.
