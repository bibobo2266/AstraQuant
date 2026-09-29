# Total-Return Benchmark Layer

Status: **IMPLEMENTED**

AstraQuant benchmark comparisons use the canonical FinMind `TaiwanStockTotalReturnIndex` series for `TAIEX` from `data/futures/index_tri.parquet`.

The price-only TAIEX series is not permitted for strategy-excess reporting because it omits dividends and would systematically overstate excess performance relative to an investable equity benchmark.

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

The comparison module is reusable and is not tied to the breakout report.
