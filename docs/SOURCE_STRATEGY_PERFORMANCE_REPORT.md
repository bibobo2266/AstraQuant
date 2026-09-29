# Frozen Canonical Strategy Performance + Total-Return Benchmark Report

Status: **PASS**

This is descriptive in-sample evidence for the frozen canonical configuration. It is not OOS validation, parameter promotion, or an investment recommendation.

## Frozen configuration

- signal window: 2016-01-04 through 2026-06-30
- simulation/drain horizon: 2016-01-04 through 2026-07-07
- RAW strategy NAV sessions: 2,559
- starting capital: 10,000,000.00
- canonical signals supplied: 35,592
- PIT-unsafe CA tickers quarantined: 4
- signal rows removed by PIT CA quarantine: 76
- policy: 10% NAV target, max 10 positions, 12% RAW stop, 20-session re-entry gap, 250-session max hold, 1000-share lot, seed 0
- executable exit layer in this round: fixed stop + time/max-hold only
- strategy execution assumptions: zero explicit fees and zero slippage in this frozen descriptive run
- benchmark: FinMind TaiwanStockTotalReturnIndex (TAIEX), buy-and-hold, same starting capital and exact strategy trading dates, no benchmark transaction-cost deduction

## 一、單筆層（主表）

| Metric | Strategy |
|---|---:|
| Closed trades n | 206 |
| Win rate | 25.73% |
| Average win | 80.32% |
| Average loss | -12.83% |
| Payoff ratio | 6.262 |
| Expectancy per trade | 11.14% |

Open FIFO lots are reported separately and excluded from the table above: **9** open lots.

## 二、超額與代價

| Metric | Value |
|---|---:|
| Cumulative excess return (strategy - benchmark) | -295.91% |
| Daily-return correlation | 0.502 |
| Beta vs total-return benchmark | 0.676 |
| Max-drawdown difference (strategy - benchmark) | -7.87% |
| Closed trade count | 206 |
| Annualized gross turnover | 325.67% |
| Average holding days (calendar) | 170.0 |

## 三、組合層（附表）

| Metric | Strategy | Total-return benchmark |
|---|---:|---:|
| CAGR | 16.93% | 22.07% |
| MaxDD | -36.42% | -28.55% |
| Sharpe (daily, rf=0, sqrt(252)) | 0.794 | 1.245 |

## 判讀原則

輸給基準不是淘汰標準。本專案的目的是尋找 0050 以外的機會，評估重點是「超額有多大、代價是什麼、與大盤的相關性多低」。一條報酬較低但相關性低的策略，配置價值可能高於報酬較高但高度同向的策略。不得以「未跑贏大盤」為由停止研究某條訊號。

## Accounting/activity audit

- final strategy NAV: 51,696,620.30
- entries executed: 215
- RAW stop exits: 140
- RAW max-hold exits: 65
- blocked exit attempts: 19
- corporate actions applied: 14,260
- corporate-action cash payments settled: 12,037
- ending pending receivables: 328,865.268830
- ending pending payables: 0.000000

## Reproducibility gates

| Gate | Result |
|---|---|
| same_signal_window_as_long_horizon_probe | PASS |
| same_policy_configuration | PASS |
| raw_nav_series_complete | PASS |
| no_unsupported_ca_cash | PASS |
| pit_unsafe_ca_tickers_excluded | PASS |
| positive_nav_all_sessions | PASS |
| frozen_long_nav_exact_float_check | PASS |
| benchmark_same_trading_days | PASS |

Trade-level returns are reconstructed from canonical fills plus CA-aware FIFO events. Open lots are not mixed into closed-trade statistics. Portfolio-path metrics are secondary descriptive context.
