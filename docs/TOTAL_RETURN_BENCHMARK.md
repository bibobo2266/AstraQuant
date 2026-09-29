# Total-Return Benchmark Layer

Status: **IMPLEMENTED**

AstraQuant benchmark comparisons use the canonical FinMind `TaiwanStockTotalReturnIndex` series for `TAIEX` from `data/futures/index_tri.parquet`.

The price-only TAIEX series is not permitted for strategy-excess reporting because it omits dividends and would systematically overstate excess performance relative to an investable equity benchmark.

## Source provenance

The canonical source file is `data/futures/index_tri.parquet`, produced in the read-only source repository by `scripts/build_futures.py` from FinMind dataset `TaiwanStockTotalReturnIndex` with `data_id=TAIEX`. The source builder separately stores `TaiwanStockPrice` as `index_taiex.parquet`; that price-only series is not accepted for excess-return reporting.

The frozen long-window strategy currently uses a signal window ending 2026-06-30 plus drain sessions, producing a RAW NAV/benchmark comparison window of **2016-01-04 through 2026-07-07**. Benchmark alignment is always driven by the actual strategy NAV index rather than by independently chosen benchmark dates.

## Alignment contract

- strategy and benchmark use exactly the same trading dates;
- benchmark starts with the same initial capital as the strategy;
- benchmark is buy-and-hold with no benchmark transaction-cost deduction;
- strategy keeps its existing canonical execution-cost assumptions;
- missing benchmark dates hard-fail rather than forward-fill;
- the strategy NAV remains the canonical RAW-accounting NAV.

## Report order

Every benchmark-aware strategy report presents:

1. **Trade level (primary)** — closed-trade count, win rate, average winner, average loser, payoff ratio, expectancy. Open lots are separate.
2. **Excess and cost** — cumulative excess return, daily-return correlation, beta, drawdown difference, trade count, annualized gross turnover, average holding days.
3. **Portfolio level (appendix)** — CAGR, MaxDD, Sharpe for strategy and total-return benchmark.

## Interpretation

輸給基準不是淘汰標準。本專案的目的是尋找 0050 以外的機會，評估重點是「超額有多大、代價是什麼、與大盤的相關性多低」。一條報酬較低但相關性低的策略，配置價值可能高於報酬較高但高度同向的策略。不得以「未跑贏大盤」為由停止研究某條訊號。

The comparison module is reusable and is not tied to the breakout report. `render_benchmark_report_sections()` owns the governed three-block report ordering so future signal reports do not reimplement benchmark presentation logic.
