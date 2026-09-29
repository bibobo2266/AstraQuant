# Canonical Config Strategy Performance + Total-Return Benchmark Report

Status: **PENDING_EPOCH_GATE**

> 於治理層上線前生成，含 E3 區間。治理層完成後以 E1 預設重跑取代；在此之前不得據此判讀。

This is descriptive in-sample evidence. It is not OOS validation, parameter promotion, or an investment recommendation.

## Run identity

- mode: legacy-breakout-regression
- signal source: CANONICAL_SIMPLE_BREAKOUT_V1
- signal window: 2016-01-04 through 2026-06-30
- simulation/drain horizon: 2016-01-04 through 2026-07-07
- RAW strategy NAV sessions: 2,559
- starting capital: 10,000,000.00
- canonical candidates supplied: 35,592
- PIT-unsafe CA tickers quarantined: 4
- legacy signal rows removed by PIT CA quarantine: 76
- executable exit layer in this round remains limited to fixed stop + time/max-hold only
- execution/accounting and verified CA semantics remain unchanged; this round adds the documented conservative unverified-terminal cashout overlay
- strategy execution assumptions: zero explicit fees and zero slippage in this descriptive run
- benchmark: FinMind TaiwanStockTotalReturnIndex (TAIEX), buy-and-hold, same starting capital and exact strategy trading dates, no benchmark transaction-cost deduction
- closed FIFO trade table: `docs/SOURCE_STRATEGY_PERFORMANCE_REPORT_TRADES.csv`
- open FIFO lots table: `docs/SOURCE_STRATEGY_PERFORMANCE_REPORT_OPEN_LOTS.csv`

## 一、單筆層（主表）

| Metric | Strategy |
|---|---:|
| Closed trades n | 206 |
| Win rate | 25.73% |
| Average win | 80.32% |
| Average loss | -12.83% |
| Payoff ratio | 6.262 |
| Expectancy per trade | 11.14% |
| Closed trades involving UNVERIFIED_TERMINAL_CASHOUT | 0 (0.00%) |

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
- corporate actions applied: 14,283
- corporate-action cash payments settled: 12,060
- ending pending receivables: 328,865.268830
- ending pending payables: 0.000000

## Reproducibility gates

| Gate | Result |
|---|---|
| same_signal_window_as_long_horizon_probe | PASS |
| simulation_ends_on_2026_07_07 | PASS |
| raw_nav_series_complete | PASS |
| no_unsupported_ca_cash | PASS |
| pit_unsafe_ca_tickers_excluded | PASS |
| candidate_signal_ids_four_digit_only | PASS |
| positive_nav_all_sessions | PASS |
| benchmark_same_trading_days | PASS |
| fifo_trade_table_written | PASS |
| open_lots_table_written | PASS |
| frozen_long_nav_exact_float_check | PASS |

Closed-trade statistics come from CA-aware FIFO reconstruction. Any entry with a remaining open FIFO lot is excluded from closed-trade statistics and reported separately.
CAGR / MaxDD / Sharpe are secondary portfolio-path context; the trade-level table is primary.
