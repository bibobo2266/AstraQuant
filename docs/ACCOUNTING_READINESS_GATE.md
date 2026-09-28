# Accounting Readiness Gate

Status: **UNLOCKED FOR THE AUDITED CANONICAL STRATEGY CONFIGURATION**

AstraQuant permits performance metrics only for a simulation that satisfies every accounting invariant below and runs through the canonical AstraQuant RAW execution/accounting path. This is a scoped unlock for the audited canonical breakout configuration and its declared source-quality exclusions. It is not a blanket approval for the legacy `minervini_picks` backtest or for arbitrary future strategies.

## Current evidence

| Gate | Status | Evidence |
|---|---|---|
| signal source declared | PASS | canonical breakout signal declaration + strategy simulator |
| entry = RAW | PASS | canonical execution service + source strategy integration smoke |
| stop observation/fill = RAW | PASS | RAW stop semantics + long-horizon probe |
| exit = RAW | PASS | canonical execution service + long-horizon probe |
| sizing = RAW | PASS | canonical execution service + long-horizon probe |
| mark = RAW | PASS | RAW current/stale/terminal mark policies |
| share count reconciles | PASS | split, capital reduction, stock dividend, terminal extinguishment tests |
| cash reconciles | PASS | canonical settlements + CA receivable/payment paths |
| receivables reconcile | PASS | ex-date accrual + declared payment-date settlement |
| corporate actions reconcile | PASS WITH DECLARED SOURCE LIMITS | normalized dividend view, explicit non-dividend CA rows, terminal-security lifecycle |
| NAV reconciles | PASS | 2,559-session canonical long-horizon RAW NAV sequence |
| no adjusted execution fallback | PASS | execution-coordinate guards + source probes |
| canonical execution path active | PASS | canonical signal → intent → RAW fill → ledger → settlement → RAW NAV |
| normalized CA view active | PASS | `docs/SOURCE_NORMALIZED_CA_VIEW_AUDIT.md` |
| declared CA payment dates settle | PASS | strategy simulator payment-date settlement + regression test |
| PIT-unsafe CA rows excluded | PASS | source-quality quarantine in long-horizon run |
| terminal-security lifecycle active | PASS | 4141 suspension/merger/delisting regression |
| required long-horizon canonical probe | PASS | `docs/SOURCE_STRATEGY_LONG_HORIZON_PROBE.md` |

## Long-horizon canonical strategy/accounting evidence

`docs/SOURCE_STRATEGY_LONG_HORIZON_PROBE.md` now passes for:

- signal window: 2016-01-04 through 2026-06-30;
- simulation/drain horizon: 2016-01-04 through 2026-07-07;
- 2,559 RAW NAV snapshots;
- 35,592 canonical signal candidates supplied after source-quality quarantine;
- 215 entries executed;
- 140 RAW stop exits;
- 65 RAW max-hold exits;
- 14,257 supported corporate-action components applied;
- 12,036 corporate-action cash payments settled;
- zero adjusted execution fallback;
- zero negative settled cash / receivable / payable gate failures.

These counts are accounting/integration evidence, not strategy-quality conclusions.

## Corporate-action evidence

The performance unlock relies on the AstraQuant normalized corporate-action view rather than the legacy FinMind ledger date/unit assumptions.

Current source-backed behavior includes:

- cash dividends use `CashExDividendTradingDate`;
- stock dividends use `StockExDividendTradingDate`;
- statutory-surplus components are included where present;
- source-specific stock-distribution units are explicit;
- `known_at` is retained;
- declared `CashDividendPaymentDate` moves receivables into settled cash;
- 7 source components whose `known_at` occurs after their effective date are not allowed to leak into the simulated eligible universe;
- unmatched official ↔ FinMind date joins remain explicit source limitations rather than guessed merges.

Evidence: `docs/SOURCE_DIVIDEND_SEMANTICS_AUDIT.md` and `docs/SOURCE_NORMALIZED_CA_VIEW_AUDIT.md`.

## Terminal-security evidence

Ticker 4141 exposed a terminal RAW-history case rather than an ordinary stale-price gap.

AstraQuant now has an explicit lifecycle:

last RAW trade → declared terminal suspension window → valuation-only last RAW carry → merger/delisting cash entitlement on opening shares → explicit position extinguishment → payment-date settlement.

No synthetic sell fill and no adjusted-price fallback are used.

Evidence: `docs/TERMINAL_SECURITY_LIFECYCLE.md` and `docs/SOURCE_TERMINAL_SECURITY_AUDIT.md`.

## Scope of the performance unlock

Performance metrics may now be computed for the **audited canonical breakout simulation configuration** that uses:

- canonical adjusted-research signal construction;
- PIT/source-quality exclusions documented by the long-horizon probe;
- canonical RAW execution and valuation;
- normalized CA handling;
- canonical settlement/accounting;
- the declared deterministic portfolio policy.

This unlock does **not** mean:

- the strategy is good;
- parameters are validated or promoted;
- robustness/OOS gates are passed;
- the legacy `minervini_picks/scripts/portfolio_backtest.py` is valid;
- future strategies may bypass this accounting gate.

Performance numbers produced next are descriptive backtest statistics only. They remain below the research validation ladder and cannot be treated as OOS/robustness evidence.

## Remaining source limitations

- official ↔ FinMind corporate-action date joins are incomplete and are never guessed;
- a small set of PIT-unsafe corporate-action rows is quarantined;
- terminal-security economics require explicit source-backed lifecycle facts; missing RAW alone is not enough to infer delisting/merger terms;
- rights-subscription economics remain unsupported unless explicitly modeled;
- adjusted prices remain research-only.

## Next task

Compute a frozen **descriptive performance report** for the exact audited canonical long-horizon configuration, with no parameter tuning, no strategy promotion, and clear separation between accounting-valid descriptive statistics and later OOS/robustness validation.
