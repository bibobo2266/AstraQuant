# Canonical Config Strategy Performance + Total-Return Benchmark Report

Status: **PASS**

This is descriptive in-sample evidence. It is not OOS validation, parameter promotion, or an investment recommendation.

## Run identity

- mode: config:configs/research/runs/rsi_pullback_reclaim_all_liquid_stop12_time250.yaml
- signal source: CONFIG:rsi_pullback_reclaim
- signal window: 2016-01-04 through 2026-06-30
- simulation/drain horizon: 2016-01-04 through 2026-07-07
- RAW strategy NAV sessions: 2,559
- starting capital: 10,000,000.00
- canonical candidates supplied: 12,125
- PIT-unsafe CA tickers quarantined: 4
- legacy signal rows removed by PIT CA quarantine: 0
- executable exit layer in this round remains limited to fixed stop + time/max-hold only
- execution/accounting/CA/terminal lifecycle logic is unchanged
- strategy execution assumptions: zero explicit fees and zero slippage in this descriptive run
- benchmark: FinMind TaiwanStockTotalReturnIndex (TAIEX), buy-and-hold, same starting capital and exact strategy trading dates, no benchmark transaction-cost deduction
- closed FIFO trade table: `docs/SOURCE_RSI_STRATEGY_PERFORMANCE_TRADES.csv`
- open FIFO lots table: `docs/SOURCE_RSI_STRATEGY_PERFORMANCE_OPEN_LOTS.csv`

## 一、單筆層（主表）

| Metric | Strategy |
|---|---:|
| Closed trades n | 214 |
| Win rate | 26.17% |
| Average win | 59.21% |
| Average loss | -13.12% |
| Payoff ratio | 4.515 |
| Expectancy per trade | 5.81% |

Open FIFO lots are reported separately and excluded from the table above: **10** open lots.

## 二、超額與代價

| Metric | Value |
|---|---:|
| Cumulative excess return (strategy - benchmark) | -541.25% |
| Daily-return correlation | 0.597 |
| Beta vs total-return benchmark | 0.727 |
| Max-drawdown difference (strategy - benchmark) | -13.24% |
| Closed trade count | 214 |
| Annualized gross turnover | 346.88% |
| Average holding days (calendar) | 168.5 |

## 三、組合層（附表）

| Metric | Strategy | Total-return benchmark |
|---|---:|---:|
| CAGR | 9.98% | 22.07% |
| MaxDD | -41.79% | -28.55% |
| Sharpe (daily, rf=0, sqrt(252)) | 0.562 | 1.245 |

## 判讀原則

輸給基準不是淘汰標準。本專案的目的是尋找 0050 以外的機會，評估重點是「超額有多大、代價是什麼、與大盤的相關性多低」。一條報酬較低但相關性低的策略，配置價值可能高於報酬較高但高度同向的策略。不得以「未跑贏大盤」為由停止研究某條訊號。

## Accounting/activity audit

- final strategy NAV: 27,162,736.19
- entries executed: 224
- RAW stop exits: 145
- RAW max-hold exits: 69
- blocked exit attempts: 16
- corporate actions applied: 11,253
- corporate-action cash payments settled: 9,686
- ending pending receivables: 203,063.097270
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

Closed-trade statistics come from CA-aware FIFO reconstruction. Any entry with a remaining open FIFO lot is excluded from closed-trade statistics and reported separately.
CAGR / MaxDD / Sharpe are secondary portfolio-path context; the trade-level table is primary.
