# Accounting-Only Replay Gate

AstraQuant now has a deterministic accounting replay that deliberately ignores strategy performance.

## Purpose

The replay proves that the execution/accounting chain can move through:

declared signal source → RAW sizing → RAW entry → settlement → RAW stop observation → RAW mark → RAW exit → settlement → final cash/position reconciliation.

It uses zero fee and zero slippage models so the first acceptance criterion is accounting identity rather than performance realism.

## Required checks

A replay passes only when all of the following are true:

- signal source is explicitly declared;
- sizing decision is RAW/SIZING;
- entry decision is RAW/ENTRY;
- stop observation is RAW/STOP_OBSERVATION;
- exit decision is RAW/EXIT;
- mark is RAW/MARK;
- final share count reconciles;
- cash reconciles to the fill ledger;
- pending receivables/payables reconcile;
- pre-exit NAV reconciles from RAW market value plus cash state;
- no adjusted execution fallback is used.

## Scope

This first replay closes the core trade lifecycle only. Corporate-action cash receivables are already implemented and integrated with the portfolio engine, but a source-backed corporate-action replay remains a separate gate.

Performance metrics remain locked.
