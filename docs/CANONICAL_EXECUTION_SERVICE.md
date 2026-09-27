# Canonical Execution Service

AstraQuant now has a single governed execution service for simulated or approved intents.

## Boundary

Signal generation remains outside the execution service. Every signal entering the service must carry an explicit `SignalDeclaration` with:

- source
- price semantics

Economic actions then use only RAW market data.

## Canonical path

`OrderIntent`

→ resolve RAW execution price

→ enforce tradability

→ create Fill through `ExecutionFillFactory`

→ create/submit order

→ apply Fill through `PortfolioEngine`

→ schedule settlement

If RAW/tradability blocks execution, the service raises `NotExecutableError` **before** creating an order or mutating positions/cash.

## RAW observation helpers

The same service exposes governed RAW decisions for:

- sizing
- stop observation
- mark-to-market

These remain separate from fill creation.

## Scope

This service is the required economic path for the future AstraQuant portfolio simulator. It does not generate strategy signals and does not inspect performance metrics.
