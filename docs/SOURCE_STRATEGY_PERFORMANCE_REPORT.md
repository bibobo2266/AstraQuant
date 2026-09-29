# Canonical Config Strategy Performance + Total-Return Benchmark Report

Status: **PASS**

Epoch: **E1：歷史開發期**

This report is governed historical evidence. It is not parameter promotion, OOS unlock, or an investment recommendation.

## Run identity

- strategy_version: legacy_breakout_v1
- mode: legacy-breakout
- signal source: CANONICAL_SIMPLE_BREAKOUT_V1
- signal/effect window: 2016-01-04 through 2021-12-31
- simulation horizon: 2016-01-04 through 2021-12-30
- next-epoch drain: prohibited
- RAW strategy NAV sessions: 1,468
- starting capital: 10,000,000.00
- canonical candidates supplied: 19,391
- PIT-unsafe CA tickers quarantined: 3
- legacy signal rows removed by PIT CA quarantine: 28
- strategy execution assumptions: zero explicit fees and zero slippage in this descriptive run
- benchmark: FinMind TaiwanStockTotalReturnIndex (TAIEX), same starting capital and exact strategy trading dates
- closed FIFO trade table: `docs/SOURCE_STRATEGY_PERFORMANCE_REPORT_TRADES.csv`
- open FIFO lots table: `docs/SOURCE_STRATEGY_PERFORMANCE_REPORT_OPEN_LOTS.csv`

## 一、單筆層（主表）

| Metric | Strategy |
|---|---:|
| Closed trades n | 103 |
| Win rate | 28.16% |
| Average win | 56.38% |
| Average loss | -12.52% |
| Payoff ratio | 4.504 |
| Expectancy per trade | 6.88% |
| Closed trades involving UNVERIFIED_TERMINAL_CASHOUT | 0 (0.00%) |

Open FIFO lots are reported separately and excluded from the table above: **10** open lots.

## 二、超額與代價

| Metric | Value |
|---|---:|
| Cumulative excess return (strategy - benchmark) | -1.90% |
| Daily-return correlation | 0.432 |
| Beta vs total-return benchmark | 0.602 |
| Max-drawdown difference (strategy - benchmark) | 7.01% |
| Closed trade count | 103 |
| Annualized gross turnover | 288.51% |
| Average holding days (calendar) | 177.2 |

## 三、組合層（附表）

| Metric | Strategy | Total-return benchmark |
|---|---:|---:|
| CAGR | 18.72% | 18.86% |
| MaxDD | -21.54% | -28.55% |
| Sharpe (daily, rf=0, sqrt(252)) | 0.953 | 1.265 |

## 判讀原則

輸給基準不是淘汰標準。本專案的目的是尋找 0050 以外的機會，評估重點是「超額有多大、代價是什麼、與大盤的相關性多低」。一條報酬較低但相關性低的策略，配置價值可能高於報酬較高但高度同向的策略。不得以「未跑贏大盤」為由停止研究某條訊號。

## 期末未平倉揭露

- 未平倉 entry sources: 10
- 未平倉佔全部已觀察 entry sources: 8.85%
- 未平倉部位不強制平倉，且未讀取下一時期價格補完。

| Source fill | Current ticker | Entry date | Held days at period end |
|---|---|---|---:|
| fill:entry:2021-10-04:1604:0 | 1604 | 2021-10-04 | 87 |
| fill:entry:2021-04-15:2007:0 | 2007 | 2021-04-15 | 259 |
| fill:entry:2021-04-14:2606:0 | 2606 | 2021-04-14 | 260 |
| fill:entry:2021-05-14:2642:2 | 2642 | 2021-05-14 | 230 |
| fill:entry:2021-04-15:2855:1 | 2855 | 2021-04-15 | 259 |
| fill:entry:2021-06-09:3141:0 | 3141 | 2021-06-09 | 204 |
| fill:entry:2021-10-22:3661:0 | 3661 | 2021-10-22 | 69 |
| fill:entry:2021-10-06:4141:0 | 4141 | 2021-10-06 | 85 |
| fill:entry:2021-12-22:6205:0 | 6205 | 2021-12-22 | 8 |
| fill:entry:2021-04-16:6261:1 | 6261 | 2021-04-16 | 258 |

## Accounting/activity audit

- final strategy NAV: 27,946,159.57
- entries executed: 113
- RAW stop exits: 66
- RAW max-hold exits: 37
- blocked exit attempts: 13
- corporate actions applied: 7,143
- corporate-action cash payments settled: 6,103
- ending pending receivables: -0.000000
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
