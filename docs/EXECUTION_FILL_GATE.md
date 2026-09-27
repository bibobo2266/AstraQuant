# Execution Fill Gate

AstraQuant fill construction is gated by an executable RAW price decision.

## Canonical fill path

`ExecutionMarketData.resolve(...)`

→ returns `ExecutionPriceDecision`

→ `ExecutionFillFactory.create_fill(...)`

→ applies configured slippage

→ applies configured fees

→ creates `Fill`

A fill cannot be created through this factory when:

- RAW is missing or invalid;
- tradability is missing;
- the requested side is blocked;
- the price decision is for a non-fill use such as MARK or SIZING;
- the fill side differs from the approved price decision;
- the executable decision has no positive price.

## Fill-capable price uses

- ENTRY
- STOP_FILL
- EXIT

Stop observation, sizing, mark-to-market, and cash/P&L are not themselves fill-creation events.

## Scope

`PortfolioEngine.apply_fill` remains the low-level state mutation primitive and preserves the invariant that only fills mutate positions.

Higher-level backtest/execution orchestration must construct fills through `ExecutionFillFactory`; direct ad-hoc Fill construction is not the canonical execution path and will be tightened further when the accounting replay service is introduced.
