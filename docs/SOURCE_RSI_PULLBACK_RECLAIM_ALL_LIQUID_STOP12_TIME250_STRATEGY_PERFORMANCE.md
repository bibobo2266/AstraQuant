# Canonical Config Strategy Performance + Total-Return Benchmark Report

Status: **PASS**

Epoch: **E1：歷史開發期**

This report is governed historical evidence. It is not parameter promotion, OOS unlock, or an investment recommendation.

## Run identity

- strategy_version: rsi_pullback_reclaim_all_liquid_stop12_time250
- mode: config:configs/research/runs/rsi_pullback_reclaim_all_liquid_stop12_time250.yaml
- signal source: CONFIG:rsi_pullback_reclaim
- signal/effect window: 2016-01-04 through 2021-12-31
- simulation horizon: 2016-01-04 through 2021-12-30
- next-epoch drain: prohibited
- RAW strategy NAV sessions: 1,468
- starting capital: 10,000,000.00
- canonical candidates supplied: 6,533
- PIT-unsafe CA tickers quarantined: 3
- legacy signal rows removed by PIT CA quarantine: 0
- strategy execution assumptions: zero explicit fees and zero slippage in this descriptive run
- benchmark: FinMind TaiwanStockTotalReturnIndex (TAIEX), same starting capital and exact strategy trading dates
- closed FIFO trade table: `docs/SOURCE_RSI_PULLBACK_RECLAIM_ALL_LIQUID_STOP12_TIME250_STRATEGY_PERFORMANCE_TRADES.csv`
- open FIFO lots table: `docs/SOURCE_RSI_PULLBACK_RECLAIM_ALL_LIQUID_STOP12_TIME250_STRATEGY_PERFORMANCE_OPEN_LOTS.csv`

## 一、單筆層（主表）

| Metric | Strategy |
|---|---:|
| Closed trades n | 122 |
| Win rate | 26.23% |
| Average win | 48.68% |
| Average loss | -13.12% |
| Payoff ratio | 3.710 |
| Expectancy per trade | 3.09% |
| Closed trades involving UNVERIFIED_TERMINAL_CASHOUT | 0 (0.00%) |

Open FIFO lots are reported separately and excluded from the table above: **10** open lots.

## 二、超額與代價

| Metric | Value |
|---|---:|
| Cumulative excess return (strategy - benchmark) | -145.99% |
| Daily-return correlation | 0.582 |
| Beta vs total-return benchmark | 0.746 |
| Max-drawdown difference (strategy - benchmark) | -13.24% |
| Closed trade count | 122 |
| Annualized gross turnover | 355.64% |
| Average holding days (calendar) | 162.9 |

## 三、組合層（附表）

| Metric | Strategy | Total-return benchmark |
|---|---:|---:|
| CAGR | 5.19% | 18.86% |
| MaxDD | -41.79% | -28.55% |
| Sharpe (daily, rf=0, sqrt(252)) | 0.368 | 1.265 |

## 判讀原則

輸給基準不是淘汰標準。本專案的目的是尋找 0050 以外的機會，評估重點是「超額有多大、代價是什麼、與大盤的相關性多低」。一條報酬較低但相關性低的策略，配置價值可能高於報酬較高但高度同向的策略。不得以「未跑贏大盤」為由停止研究某條訊號。

## 期末未平倉揭露

- 未平倉 entry sources: 10
- 未平倉佔全部已觀察 entry sources: 7.58%
- 未平倉部位不強制平倉，且未讀取下一時期價格補完。

| Source fill | Current ticker | Entry date | Held days at period end |
|---|---|---|---:|
| fill:entry:2021-04-19:1609:0 | 1609 | 2021-04-19 | 255 |
| fill:entry:2021-11-30:1760:0 | 1760 | 2021-11-30 | 30 |
| fill:entry:2021-05-19:2347:0 | 2347 | 2021-05-19 | 225 |
| fill:entry:2021-05-28:2886:0 | 2886 | 2021-05-28 | 216 |
| fill:entry:2021-06-09:3264:0 | 3264 | 2021-06-09 | 204 |
| fill:entry:2021-10-05:3551:0 | 3551 | 2021-10-05 | 86 |
| fill:entry:2021-10-13:4938:0 | 4938 | 2021-10-13 | 78 |
| fill:entry:2021-10-07:5243:0 | 5243 | 2021-10-07 | 84 |
| fill:entry:2021-08-12:6409:0 | 6409 | 2021-08-12 | 140 |
| fill:entry:2021-10-22:6504:0 | 6504 | 2021-10-22 | 69 |

## Accounting/activity audit

- final strategy NAV: 13,536,784.87
- entries executed: 132
- RAW stop exits: 84
- RAW max-hold exits: 38
- blocked exit attempts: 6
- corporate actions applied: 5,298
- corporate-action cash payments settled: 4,638
- ending pending receivables: 0.000000
- ending pending payables: 0.000000

## Reproducibility gates

| Gate | Result |
|---|---|
| governed_epoch_start | PASS |
| governed_epoch_end | PASS |
| no_next_epoch_drain | PASS |
| raw_nav_series_complete | PASS |
| no_unsupported_ca_cash | PASS |
| pit_unsafe_ca_tickers_excluded | PASS |
| candidate_signal_ids_four_digit_only | PASS |
| positive_nav_all_sessions | PASS |
| benchmark_same_trading_days | PASS |
| fifo_trade_table_written | PASS |
| open_lots_table_written | PASS |

Closed-trade statistics and period-end open-lot disclosure are reported separately; open lots are not forced closed.
CAGR / MaxDD / Sharpe are secondary portfolio-path context; the trade-level table is primary.
