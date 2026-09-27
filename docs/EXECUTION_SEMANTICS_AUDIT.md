# Execution Semantics Audit

Status: INITIAL STATIC AUDIT

Source repository: `bibobo2266/minervini_picks` (READ ONLY)  
AstraQuant repository: writable

## Scope

This audit inspects active source code and workflow wiring only. It does not modify the source repository and does not yet execute the backtest.

## Active portfolio workflow

`.github/workflows/portfolio_backtest.yaml` actively executes:

`python scripts/portfolio_backtest.py`

Therefore violations inside `scripts/portfolio_backtest.py` are live execution-path issues, not dead-code concerns.

## Static findings

### Signal coordinate

`scripts/portfolio_backtest.py` sets:

`DATA_DIR = "data/adj"`

and builds close/high/low/open matrices from `prices_adj_*.parquet`.

Signal calculations such as moving averages, RS, breakout, trend/breadth, and relative ATR therefore use the adjusted research coordinate.

Status: **EXPECTED for signal-space calculations**, subject to feature semantic declarations and consistent adjustment within lookback windows.

### Entry price

The simulated entry price is sourced from the adjusted open matrix:

`entry_px = o[t, j]`

where `O` comes from adjusted parquet data.

Status: **FAIL**

Required contract: entry execution price must be RAW.

### Stop observation and stop fill

The intraday low matrix `L` is built from adjusted parquet data. Stop triggering therefore observes adjusted intraday lows.

When a stop triggers, the code uses adjusted open or the adjusted stop level.

Status: **FAIL**

Required contract: stop observation and fill simulation must use RAW execution coordinates.

### Exit and mark-to-market

Time/dead-money/other exits use `C`, which is the adjusted close matrix.

Portfolio market value is calculated using adjusted close:

`shares * adjusted_close`

with adjusted entry price as fallback.

Status: **FAIL**

Required contract: exit and mark-to-market must use RAW prices, with economic continuity handled by the corporate-action event engine.

### Position sizing

The script constructs:

`RAW = C / F`

where `C` is adjusted close and `F` is a self-constructed dividend factor derived from `dividend_events.parquet`.

This derived `RAW` is then used for lot affordability and price filters.

Status: **FAIL**

Reason:
- true RAW history now exists and has a READY gate;
- adjusted-to-RAW reverse engineering is no longer an acceptable execution source;
- dividend-only factors do not establish complete corporate-action economic semantics.

### Cash and realized P&L

Cash debits/credits and realized returns are calculated from adjusted entry/exit prices.

Status: **FAIL**

Required contract: cash and realized P&L use actual RAW tradable prices plus explicit fees/taxes and corporate-action economic mutations.

### Corporate-action handling

The script uses adjusted prices as an implicit total-return representation and a dividend factor to estimate actual price for sizing. It does not use the canonical corporate-action ledger as the economic event engine for share-count changes, receivables, cash distributions, security mappings, reductions, rights, splits, or mergers.

Status: **FAIL / INCOMPLETE**

### Legacy adjusted builder

`scripts/build_adj.py` remains in the source repository and explicitly implements backward price adjustment from dividend-result ratios while leaving volume unadjusted.

This file is a legacy data-production path. Its existence is not itself an AstraQuant failure, but AstraQuant must never infer adjusted-data semantics from this script or rely on it as the canonical execution/accounting path.

## Current accounting gate

| Check | Status |
|---|---|
| entry = RAW | FAIL |
| stop observation = RAW | FAIL |
| exit = RAW | FAIL |
| sizing = RAW | FAIL |
| mark = RAW | FAIL |
| signal source declared | PARTIAL |
| share count reconciles | NOT_TESTED |
| cash reconciles | NOT_TESTED |
| receivables reconcile | NOT_TESTED |
| corporate actions reconcile | NOT_TESTED |
| NAV reconciles | NOT_TESTED |
| no adjusted execution fallback | FAIL |

## Decision

Do not interpret portfolio performance from the current active `portfolio_backtest.py` as accounting-valid.

Do not patch one line at a time. The next implementation batch should replace the execution coordinate systematically:

1. load RAW OHLC as the execution coordinate;
2. retain adjusted series only for declared signal features;
3. remove adjusted-to-RAW reverse engineering;
4. hard-fail when an intended fill lacks RAW;
5. introduce explicit corporate-action economic mutations;
6. reconcile cash, receivables, shares, and NAV before unlocking performance metrics.

## Limitation

This is a static code-path audit. Runtime parquet-level verification is still blocked in the Astra environment because the required checkout/mount is absent.
