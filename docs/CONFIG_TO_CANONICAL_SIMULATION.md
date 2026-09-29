# Config-to-Canonical Simulation Contract

Status: **IMPLEMENTED CORE BRIDGE**

## Purpose

ResearchConfigEngine no longer stops at candidate preparation. A prepared config run can be passed directly to CanonicalStrategySimulator through one candidate contract while preserving the existing execution/accounting/CA stack.

## Canonical candidate interface

Required fields:

- `signal_date`
- `stock_id`
- `signal_source`
- `signal_price_semantics`
- `available_at`

Optional capacity-attribution fields remain supported:

- `turnover_value`
- `breakout_excess`

The frozen breakout DataFrame is adapted into this interface without changing its candidate dates or tickers. Config-engine candidates use the same contract.

For current daily config signals, `available_at` defaults conservatively to the end of the signal calendar day. The simulator still executes eligible entries at the next canonical session open. A candidate whose `available_at` is not before that next-session entry point hard-fails.

## Engine flow

```text
UniverseConfig + SignalConfig + ExitConfig
        ↓
ResearchConfigEngine.prepare()
        ↓
PreparedResearchRun.candidates
        ↓
ResearchConfigEngine.simulate_prepared()
        ↓
CanonicalStrategySimulator
        ↓
unchanged RAW execution / settlement / CA / NAV accounting
        ↓
CA-aware FIFO reconstruction
        ↓
trade-level report
```

## Trade-level reporting

The reporting layer reconstructs trades from the actual canonical fills and the actual corporate-action ledgers held by PortfolioEngine.

Main statistics:

- closed trade count
- win rate
- average winner
- average loser
- payoff ratio
- expectancy per closed trade
- average holding days

A source entry fill is counted as a closed trade only when all FIFO fragments originating from that entry are closed. Open lots are listed separately and are never mixed into the closed-trade statistics.

## Portfolio metrics

CAGR, maximum drawdown, and Sharpe remain descriptive portfolio-path metrics and are secondary to the trade-level table.

## Exit limitation for this round

This bridge does **not** expand the exit layer. Canonical executable config runs remain limited to the currently implemented:

- fixed percentage stop; and
- time / max-hold exit.

Other exit families already present in the architecture schema remain non-executable until separately implemented and tested.

## Non-changes

This work does not change:

- RAW execution price resolution;
- fill construction;
- settlement;
- corporate-action accounting;
- terminal-security lifecycle handling;
- P2-060 common-support exclusions;
- candidate-universe rules;
- locked OOS governance.
