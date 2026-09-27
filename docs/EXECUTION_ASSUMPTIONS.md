# Execution Assumptions

Execution realism is part of validation, not a cosmetic afterthought.

AstraQuant keeps fee, slippage, timing, liquidity, price-limit, partial-fill, and settlement assumptions explicit and versionable.

## Core rule

A research result must not silently inherit execution assumptions from unrelated code.

Each backtest or simulation should identify an execution-assumption configuration containing at least:

- price source
- decision-to-order timing
- order-to-fill timing
- fee model
- slippage model
- liquidity constraints
- price-limit handling
- partial-fill handling
- settlement rule

## Current state

Only interfaces and generic models are implemented.

Taiwan-specific tax, commission, tick-size, daily price-limit, odd-lot, liquidity, and settlement rules are intentionally not hard-coded yet. Those rules will be frozen only after the source data and execution scope are finalized.
