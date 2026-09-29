# Canonical Config Strategy Performance + Total-Return Benchmark Report

Status: **PENDING_EPOCH_GATE**

> 於治理層上線前生成，含 E3 區間。治理層完成後以 E1 預設重跑取代；在此之前不得據此判讀。

This is descriptive in-sample evidence. It is not OOS validation, parameter promotion, or an investment recommendation.

## Run identity

- mode: config:configs/research/runs/vcp_all_liquid_stop12_time250.yaml
- signal source: CONFIG:vcp_breakout
- signal window: 2016-01-04 through 2026-06-30
- simulation/drain horizon: 2016-01-04 through 2026-07-07
- RAW strategy NAV sessions: 2,559
- starting capital: 10,000,000.00
- canonical candidates supplied: 9,663
- PIT-unsafe CA tickers quarantined: 4
- legacy signal rows removed by PIT CA quarantine: 0
- executable exit layer in this round remains limited to fixed stop + time/max-hold only
- execution/accounting and verified CA semantics remain unchanged; this round adds the documented conservative unverified-terminal cashout overlay
- strategy execution assumptions: zero explicit fees and zero slippage in this descriptive run
- benchmark: FinMind TaiwanStockTotalReturnIndex (TAIEX), buy-and-hold, same starting capital and exact strategy trading dates, no benchmark transaction-cost deduction
- closed FIFO trade table: `docs/SOURCE_VCP_ALL_LIQUID_STOP12_TIME250_STRATEGY_PERFORMANCE_TRADES.csv`
- open FIFO lots table: `docs/SOURCE_VCP_ALL_LIQUID_STOP12_TIME250_STRATEGY_PERFORMANCE_OPEN_LOTS.csv`

## 一、單筆層（主表）

| Metric | Strategy |
|---|---:|
| Closed trades n | 206 |
| Win rate | 26.21% |
| Average win | 48.39% |
| Average loss | -12.72% |
| Payoff ratio | 3.805 |
| Expectancy per trade | 3.30% |
| Closed trades involving UNVERIFIED_TERMINAL_CASHOUT | 0 (0.00%) |

Open FIFO lots are reported separately and excluded from the table above: **10** open lots.

## 二、超額與代價

| Metric | Value |
|---|---:|
| Cumulative excess return (strategy - benchmark) | -531.84% |
| Daily-return correlation | 0.579 |
| Beta vs total-return benchmark | 0.646 |
| Max-drawdown difference (strategy - benchmark) | -6.54% |
| Closed trade count | 206 |
| Annualized gross turnover | 334.93% |
| Average holding days (calendar) | 175.6 |

## 三、組合層（附表）

| Metric | Strategy | Total-return benchmark |
|---|---:|---:|
| CAGR | 10.34% | 22.07% |
| MaxDD | -35.09% | -28.55% |
| Sharpe (daily, rf=0, sqrt(252)) | 0.611 | 1.245 |

## 判讀原則

輸給基準不是淘汰標準。本專案的目的是尋找 0050 以外的機會，評估重點是「超額有多大、代價是什麼、與大盤的相關性多低」。一條報酬較低但相關性低的策略，配置價值可能高於報酬較高但高度同向的策略。不得以「未跑贏大盤」為由停止研究某條訊號。

## Accounting/activity audit

- final strategy NAV: 28,103,861.79
- entries executed: 216
- RAW stop exits: 139
- RAW max-hold exits: 66
- blocked exit attempts: 13
- corporate actions applied: 10,739
- corporate-action cash payments settled: 9,261
- ending pending receivables: 258,871.491200
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
