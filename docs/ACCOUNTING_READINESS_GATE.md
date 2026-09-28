# Accounting Readiness Gate

Status: **NOT YET UNLOCKED FOR PERFORMANCE**

AstraQuant now has an explicit accounting-readiness gate. Performance metrics may be inspected only when every accounting invariant passes **and** the active portfolio simulation runs through the canonical AstraQuant execution path.

## Current evidence

| Gate | Current status | Evidence |
|---|---|---|
| signal source declared | PASS in accounting replay | `docs/SOURCE_ACCOUNTING_SMOKE_REPLAY.md` |
| entry = RAW | PASS | `docs/SOURCE_ACCOUNTING_SMOKE_REPLAY.md` |
| stop observation = RAW | PASS | `docs/SOURCE_ACCOUNTING_SMOKE_REPLAY.md` |
| exit = RAW | PASS | `docs/SOURCE_ACCOUNTING_SMOKE_REPLAY.md` |
| sizing = RAW | PASS | `docs/SOURCE_ACCOUNTING_SMOKE_REPLAY.md` |
| mark = RAW | PASS | `docs/SOURCE_ACCOUNTING_SMOKE_REPLAY.md` |
| share count reconciles | PASS for plain lifecycle and source split replay | `docs/SOURCE_ACCOUNTING_SMOKE_REPLAY.md`, `docs/SOURCE_CA_SHARE_REPLAY.md` |
| cash reconciles | PASS | `docs/SOURCE_ACCOUNTING_SMOKE_REPLAY.md` |
| receivables reconcile | PASS for cash-dividend accrual with unknown payment retained | `docs/SOURCE_CA_CASH_REPLAY.md` |
| corporate actions reconcile | PASS for tested split, cash-dividend, and capital-reduction share+cash components; broader event/security-mapping coverage remains limited | `docs/SOURCE_CA_SHARE_REPLAY.md`, `docs/SOURCE_CA_CASH_REPLAY.md`, `docs/SOURCE_CAPITAL_REDUCTION_REPLAY.md` |
| NAV reconciles | PASS in RAW accounting replay | `docs/SOURCE_ACCOUNTING_SMOKE_REPLAY.md` |
| no adjusted execution fallback | PASS in canonical components | coordinate guard + execution gateway tests |
| canonical execution path active for portfolio backtest | **PARTIAL / NOT YET** | canonical historical runner now passes a 2015–2026 full-history accounting probe, but the legacy strategy's actual signal/order-intent generation has not yet been migrated into that runner |

## Latest integration evidence

- `docs/SOURCE_CANONICAL_EXECUTION_SMOKE.md` — real-source canonical execution service path passes.
- `docs/SOURCE_MULTI_EVENT_REPLAY.md` — continuous real-source split + dividend replay passes.
- `docs/SOURCE_CAPITAL_REDUCTION_REPLAY.md` — real-source capital-reduction share+cash accounting passes with source limitations.

## Full-history evidence

`docs/SOURCE_FULL_HISTORY_PROBE.md` passes a 2,859-session 2015–2026 RAW accounting replay for 2330 with daily RAW NAV snapshots and 28 canonical cash-dividend events. This proves the canonical historical runtime/accounting path can span the full frozen history range.

## Latest strategy-path integration evidence

- `docs/SOURCE_STRATEGY_INTEGRATION_SMOKE.md` — real canonical breakout candidates now pass through the causal RAW strategy simulator for the 2026-01-02 through 2026-04-02 integration window, including corporate actions and RAW NAV snapshots.
- Calendar mapping and combined ex-right/dividend opening-share entitlement are explicit; no adjusted execution fallback is used.

## Performance lock

The active legacy `minervini_picks/scripts/portfolio_backtest.py` remains read-only and is not accounting-valid. AstraQuant will not modify that repository.

The AstraQuant canonical service, event-driven replay, and a 2015–2026 full-history accounting probe now pass real-source integration tests. Performance nevertheless remains locked until the legacy strategy's actual signal/order-intent generation is migrated into this canonical path under declared PIT signal semantics.

The canonical strategy path now passes a real-source integration smoke. The remaining unlock condition is:

> run the required historical strategy/accounting horizon through the AstraQuant-owned canonical path, preserve all accounting/calendar/CA gates, freeze the resulting audit evidence, and only then permit performance metrics.

## Source limitations retained

- canonical CA ledger has no payment-date field;
- unknown CA known dates stay unknown;
- only CA event components with explicit economic fields are replayable;
- adjusted research prices remain research-only and require canonical masking.

## Next task

Build an AstraQuant-owned execution/replay service that can consume declared signals while routing every economic action through the canonical RAW accounting path. Strategy performance remains hidden until that service passes the accounting gate.
