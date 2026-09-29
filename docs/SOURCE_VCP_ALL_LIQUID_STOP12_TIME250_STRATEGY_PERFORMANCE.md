# Canonical Config Strategy Performance + Total-Return Benchmark Report

Status: **PASS**

Epoch: **E1：歷史開發期**

This report is governed historical evidence. It is not parameter promotion, OOS unlock, or an investment recommendation.

## Run identity

- strategy_version: vcp_all_liquid_stop12_time250
- mode: config:configs/research/runs/vcp_all_liquid_stop12_time250.yaml
- signal source: CONFIG:vcp_breakout
- signal/effect window: 2016-01-04 through 2021-12-31
- simulation horizon: 2016-01-04 through 2021-12-30
- next-epoch drain: prohibited
- RAW strategy NAV sessions: 1,468
- starting capital: 10,000,000.00
- canonical candidates supplied: 5,135
- PIT-unsafe CA tickers quarantined: 3
- legacy signal rows removed by PIT CA quarantine: 0
- strategy execution assumptions: zero explicit fees and zero slippage in this descriptive run
- benchmark: FinMind TaiwanStockTotalReturnIndex (TAIEX), same starting capital and exact strategy trading dates
- closed FIFO trade table: `docs/SOURCE_VCP_ALL_LIQUID_STOP12_TIME250_STRATEGY_PERFORMANCE_TRADES.csv`
- open FIFO lots table: `docs/SOURCE_VCP_ALL_LIQUID_STOP12_TIME250_STRATEGY_PERFORMANCE_OPEN_LOTS.csv`

## 一、單筆層（主表）

| Metric | Strategy |
|---|---:|
| Closed trades n | 110 |
| Win rate | 29.09% |
| Average win | 34.45% |
| Average loss | -12.44% |
| Payoff ratio | 2.769 |
| Expectancy per trade | 1.20% |
| Closed trades involving UNVERIFIED_TERMINAL_CASHOUT | 0 (0.00%) |

Open FIFO lots are reported separately and excluded from the table above: **10** open lots.

## 二、超額與代價

| Metric | Value |
|---|---:|
| Cumulative excess return (strategy - benchmark) | -144.21% |
| Daily-return correlation | 0.564 |
| Beta vs total-return benchmark | 0.707 |
| Max-drawdown difference (strategy - benchmark) | -1.82% |
| Closed trade count | 110 |
| Annualized gross turnover | 311.88% |
| Average holding days (calendar) | 180.4 |

## 三、組合層（附表）

| Metric | Strategy | Total-return benchmark |
|---|---:|---:|
| CAGR | 5.42% | 18.86% |
| MaxDD | -30.38% | -28.55% |
| Sharpe (daily, rf=0, sqrt(252)) | 0.384 | 1.265 |

## 判讀原則

輸給基準不是淘汰標準。本專案的目的是尋找 0050 以外的機會，評估重點是「超額有多大、代價是什麼、與大盤的相關性多低」。一條報酬較低但相關性低的策略，配置價值可能高於報酬較高但高度同向的策略。不得以「未跑贏大盤」為由停止研究某條訊號。

## 期末未平倉揭露

- 未平倉 entry sources: 10
- 未平倉佔全部已觀察 entry sources: 8.33%
- 未平倉部位不強制平倉，且未讀取下一時期價格補完。

| Source fill | Current ticker | Entry date | Held days at period end |
|---|---|---|---:|
| fill:entry:2021-06-02:2354:0 | 2354 | 2021-06-02 | 211 |
| fill:entry:2021-11-30:2608:0 | 2608 | 2021-11-30 | 30 |
| fill:entry:2021-10-05:2731:0 | 2731 | 2021-10-05 | 86 |
| fill:entry:2021-11-12:2883:1 | 2883 | 2021-11-12 | 48 |
| fill:entry:2021-07-26:3045:0 | 3045 | 2021-07-26 | 157 |
| fill:entry:2021-10-14:3048:0 | 3048 | 2021-10-14 | 77 |
| fill:entry:2021-06-03:3213:0 | 3213 | 2021-06-03 | 210 |
| fill:entry:2021-06-01:3605:1 | 3605 | 2021-06-01 | 212 |
| fill:entry:2021-06-08:6706:0 | 6706 | 2021-06-08 | 205 |
| fill:entry:2021-12-02:8097:0 | 8097 | 2021-12-02 | 28 |

## Accounting/activity audit

- final strategy NAV: 13,714,586.96
- entries executed: 120
- RAW stop exits: 71
- RAW max-hold exits: 38
- blocked exit attempts: 9
- corporate actions applied: 5,035
- corporate-action cash payments settled: 4,405
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
