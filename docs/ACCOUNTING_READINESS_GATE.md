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
| corporate actions reconcile | PASS for tested split and cash-dividend components; broader event coverage remains limited | `docs/SOURCE_CA_SHARE_REPLAY.md`, `docs/SOURCE_CA_CASH_REPLAY.md` |
| NAV reconciles | PASS in RAW accounting replay | `docs/SOURCE_ACCOUNTING_SMOKE_REPLAY.md` |
| no adjusted execution fallback | PASS in canonical components | coordinate guard + execution gateway tests |
| canonical execution path active for portfolio backtest | **FAIL / NOT YET** | legacy source backtest still executes adjusted-price accounting |

## Performance lock

The active legacy `minervini_picks/scripts/portfolio_backtest.py` remains read-only and is not accounting-valid. AstraQuant will not modify that repository.

Therefore performance remains locked even though the new AstraQuant accounting components pass their targeted tests.

The unlock condition is:

> run the portfolio simulation through an AstraQuant-owned canonical execution path that uses RAW execution prices, explicit tradability, explicit corporate-action accounting, and RAW NAV reconciliation.

## Source limitations retained

- canonical CA ledger has no payment-date field;
- unknown CA known dates stay unknown;
- only CA event components with explicit economic fields are replayable;
- adjusted research prices remain research-only and require canonical masking.

## Next task

Build an AstraQuant-owned execution/replay service that can consume declared signals while routing every economic action through the canonical RAW accounting path. Strategy performance remains hidden until that service passes the accounting gate.
