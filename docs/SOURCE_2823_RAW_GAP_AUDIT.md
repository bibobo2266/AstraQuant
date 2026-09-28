# 2823 RAW Gap / Terminal-Semantics Audit

Status: **BLOCKER_CONFIRMED — TERMINAL_MULTI_LEG_CONVERSION_NOT_MODELED**

Purpose: investigate the P2-062 blocker without adjusted-price fallback or silent ticker exclusion. The observed failure was an unavailable canonical RAW mark for 2823 on 2021-12-20 while the reverse breakout-strength rule held the security.

## RAW rows

| date                |   stock_id |   open |   max |   min |   close |   Trading_money |
|:--------------------|-----------:|-------:|------:|------:|--------:|----------------:|
| 2021-12-01 00:00:00 |       2823 |  30.45 | 30.6  | 30.4  |   30.55 |     1.99782e+08 |
| 2021-12-02 00:00:00 |       2823 |  30.5  | 30.6  | 30.4  |   30.5  |     3.38038e+08 |
| 2021-12-03 00:00:00 |       2823 |  30.5  | 30.75 | 30.5  |   30.65 |     2.76314e+08 |
| 2021-12-06 00:00:00 |       2823 |  30.7  | 30.8  | 30.45 |   30.7  |     2.25583e+08 |
| 2021-12-07 00:00:00 |       2823 |  30.7  | 30.85 | 30.6  |   30.85 |     2.899e+08   |
| 2021-12-08 00:00:00 |       2823 |  30.9  | 30.95 | 30.65 |   30.7  |     3.04125e+08 |
| 2021-12-09 00:00:00 |       2823 |  30.75 | 30.9  | 30.7  |   30.8  |     2.6798e+08  |
| 2021-12-10 00:00:00 |       2823 |  30.8  | 31    | 30.75 |   30.8  |     3.39913e+08 |
| 2021-12-13 00:00:00 |       2823 |  30.85 | 31    | 30.85 |   30.95 |     3.53139e+08 |
| 2021-12-14 00:00:00 |       2823 |  30.9  | 30.9  | 30.7  |   30.85 |     2.80495e+08 |
| 2021-12-15 00:00:00 |       2823 |  30.8  | 30.85 | 30.5  |   30.6  |     7.85178e+08 |
| 2021-12-16 00:00:00 |       2823 |  30.65 | 30.8  | 30.4  |   30.5  |     1.07314e+09 |
| 2021-12-17 00:00:00 |       2823 |  30.5  | 31    | 30.45 |   30.55 |     3.80846e+09 |

## Adjusted rows (diagnostic only; never execution fallback)

| date                |   stock_id |   open |   max |   min |   close |   Trading_money |
|:--------------------|-----------:|-------:|------:|------:|--------:|----------------:|
| 2021-12-01 00:00:00 |       2823 |  30.45 | 30.6  | 30.4  |   30.55 |       199782053 |
| 2021-12-02 00:00:00 |       2823 |  30.5  | 30.6  | 30.4  |   30.5  |       338037765 |
| 2021-12-03 00:00:00 |       2823 |  30.5  | 30.75 | 30.5  |   30.65 |       276313656 |
| 2021-12-06 00:00:00 |       2823 |  30.7  | 30.8  | 30.45 |   30.7  |       225583401 |
| 2021-12-07 00:00:00 |       2823 |  30.7  | 30.85 | 30.6  |   30.85 |       289900458 |
| 2021-12-08 00:00:00 |       2823 |  30.9  | 30.95 | 30.65 |   30.7  |       304125489 |
| 2021-12-09 00:00:00 |       2823 |  30.75 | 30.9  | 30.7  |   30.8  |       267979911 |
| 2021-12-10 00:00:00 |       2823 |  30.8  | 31    | 30.75 |   30.8  |       339912960 |
| 2021-12-13 00:00:00 |       2823 |  30.85 | 31    | 30.85 |   30.95 |       353138692 |
| 2021-12-14 00:00:00 |       2823 |  30.9  | 30.9  | 30.7  |   30.85 |       280494689 |
| 2021-12-15 00:00:00 |       2823 |  30.8  | 30.85 | 30.5  |   30.6  |       785178353 |
| 2021-12-16 00:00:00 |       2823 |  30.65 | 30.8  | 30.4  |   30.5  |      1073136849 |
| 2021-12-17 00:00:00 |       2823 |  30.5  | 31    | 30.45 |   30.55 |      3808460425 |

## Tradability rows

| date                |   stock_id |   open |   max |   min |   close | observed_trade   | valid_ohlc   | buy_blocked   | sell_blocked   | reason   |
|:--------------------|-----------:|-------:|------:|------:|--------:|:-----------------|:-------------|:--------------|:---------------|:---------|
| 2021-12-01 00:00:00 |       2823 |  30.45 | 30.6  | 30.4  |   30.55 | True             | True         | False         | False          | OBSERVED |
| 2021-12-02 00:00:00 |       2823 |  30.5  | 30.6  | 30.4  |   30.5  | True             | True         | False         | False          | OBSERVED |
| 2021-12-03 00:00:00 |       2823 |  30.5  | 30.75 | 30.5  |   30.65 | True             | True         | False         | False          | OBSERVED |
| 2021-12-06 00:00:00 |       2823 |  30.7  | 30.8  | 30.45 |   30.7  | True             | True         | False         | False          | OBSERVED |
| 2021-12-07 00:00:00 |       2823 |  30.7  | 30.85 | 30.6  |   30.85 | True             | True         | False         | False          | OBSERVED |
| 2021-12-08 00:00:00 |       2823 |  30.9  | 30.95 | 30.65 |   30.7  | True             | True         | False         | False          | OBSERVED |
| 2021-12-09 00:00:00 |       2823 |  30.75 | 30.9  | 30.7  |   30.8  | True             | True         | False         | False          | OBSERVED |
| 2021-12-10 00:00:00 |       2823 |  30.8  | 31    | 30.75 |   30.8  | True             | True         | False         | False          | OBSERVED |
| 2021-12-13 00:00:00 |       2823 |  30.85 | 31    | 30.85 |   30.95 | True             | True         | False         | False          | OBSERVED |
| 2021-12-14 00:00:00 |       2823 |  30.9  | 30.9  | 30.7  |   30.85 | True             | True         | False         | False          | OBSERVED |
| 2021-12-15 00:00:00 |       2823 |  30.8  | 30.85 | 30.5  |   30.6  | True             | True         | False         | False          | OBSERVED |
| 2021-12-16 00:00:00 |       2823 |  30.65 | 30.8  | 30.4  |   30.5  | True             | True         | False         | False          | OBSERVED |
| 2021-12-17 00:00:00 |       2823 |  30.5  | 31    | 30.45 |   30.55 | True             | True         | False         | False          | OBSERVED |

## Corporate-action ledger rows

_none_

## Decision boundary

This audit does not authorize excluding 2823 and does not authorize using adjusted prices as RAW marks. If the source shows a terminal/security-conversion event that AstraQuant has not modeled, that event must be accounted explicitly and then P2-062 rerun on the unchanged frozen common-support policy.

## Source interpretation

The source-backed audit establishes that canonical RAW, adjusted, and tradability observations for 2823 stop after 2021-12-17, while the canonical corporate-action ledger has no 2823 row in the audited window. This is consistent with public TWSE/MOPS-derived disclosure that 2823 stopped trading on 2021-12-20 and was converted/delisted on 2021-12-30.

Public disclosure states a three-leg economic consideration per 2823 common share: 0.80 share of 2883 common, 0.73 share of 2883 preferred, plus TWD 11.5 cash. AstraQuant currently models at most one successor security plus optional cash entitlement. Therefore this event cannot be represented faithfully by the existing single-successor conversion path.

References:
- MoneyDJ/MOPS disclosure: https://www.moneydj.com/kmdj/news/newsviewer.aspx?a=60ed45a4-aa0e-4e7a-b598-f78ada4a5488
- TWSE-derived delisting disclosure: https://www.moneydj.com/kmdj/news/newsviewer.aspx?a=f97ffc94-afa8-4dc4-bf06-b87562bac3d4

## Required remediation before P2-062 can resume

1. Freeze an explicit source-backed representation for all three consideration legs, including the exact successor identifier and RAW/mark semantics for the preferred-share leg.
2. Extend canonical portfolio accounting and FIFO reconstruction to support one predecessor converting into multiple successor securities plus cash without fabricating market fills.
3. Add regression coverage for quantity/cost-basis allocation and subsequent RAW valuation/exit of every successor leg.
4. Rerun P2-062 on the unchanged P2-060 common-support universe. Do not exclude 2823 merely because the reverse rule selected it.

Until those conditions are met, P2-062 remains blocked. No adjusted-price fallback, stale-price substitution, or silent ticker exclusion is permitted.

## Remediation implementation

AstraQuant now has a generic composite-conversion model rather than a 2823-specific bypass. The declared 2823 terms are 0.80 share of 2883 common, 0.73 share of 2883B preferred, plus TWD 11.5 cash per predecessor share. Successor/cash value weights are frozen from the disclosed deal-value inputs: 0.8 x 13.69 for common, 0.73 x 10.0 for preferred, and 11.5 cash, normalized across the three consideration legs. These weights preserve total predecessor basis and aggregate residual stop value; they are not fitted to backtest results.

Implementation still requires CI and a source-backed P2-062 rerun to prove that canonical RAW/tradability for both successor legs is available when needed. Until that passes, P2-062 is not DONE and locked OOS remains closed.
