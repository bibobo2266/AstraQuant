# baseline_60d_breakout_v1 — local readiness after causal RAW v2

Status date: 2026-10-04  
Status: **CANONICAL SYNTHETIC WIRING COMPLETE / FORMAL DATA GATE BLOCKED / NOT BACKTESTED**

This document records owner-authorized engineering preparation for `baseline_60d_breakout_v1`. The exact baseline exit pair is now wired into the canonical simulator only through an explicit opt-in context and has synthetic end-to-end acceptance. Formal research remains blocked by the real PIT/data gate, no formal baseline run config is created, and no E1 strategy backtest or E2/E3 effect query is run.

## Reuse confirmed

| requirement | current reusable path | status |
| --- | --- | --- |
| 60-session first breakout | `N_SESSION_HIGH lookback=60` | implemented; AstraQuant strict first-cross `>` semantics retained |
| price at/above MA120 | hydrated `close_to_ma120` + `COLUMN_THRESHOLD min=0.0` | no `PRICE_ABOVE_MA` evaluator is needed |
| prior-20-session amount >= TWD 20m | causal RAW v2 `prior20_amount_twd` + `COLUMN_THRESHOLD min=20000000` | computation exists; real-data availability gate remains blocked |
| RAW next-open execution / tradability | canonical execution stack | exact baseline pending exits now use canonical EXIT/open execution in opt-in synthetic integration; formal data gate remains blocked |
| accounting / terminal lifecycle | canonical portfolio stack | unchanged |

The old `configs/drafts/baseline/baseline_livermore_v1.yaml` still contains `PRICE_ABOVE_MA`; it is a historical draft and is **not** promoted or reused as the executable baseline config.

## Exit-state module now implemented in isolation

The existing math-only helpers in `src/astraquant/research/baseline_60d_breakout.py` remain unchanged.

`src/astraquant/research/baseline_60d_exit_state.py` now implements the separately authorized state module for:

- one stock-specific bounded valid-observed-OHLC sequence shared by ATR14 and LOW20, retaining only current + prior 20 valid bars;
- ATR14 = SMA(TR,14), including current valid bar;
- LOW20 = minimum of the prior 20 valid observed closes, excluding current;
- explicit UNKNOWN during insufficient warmup or missing/invalid current observation;
- entry anchor from canonical `Fill.price`, excluding fees;
- approved simple cash/share technical-coordinate transform `P_post=(P_pre-c)/m` across entry anchor and the retained OHLC history;
- same-opening cash + share aggregation without per-event rounding;
- materialized CA batch validation, equal-ID dedupe, conflicting-ID rejection, and split-opening-batch blocking;
- duplicate-CA idempotency;
- sticky pending ATR / LOW20 / BOTH intent;
- next-session-or-later open eligibility only;
- blocked-open persistence plus report/intent/holding/session/full-liquidation validation;
- terminal precedence;
- ticker-level persistent technical BLOCKED state for successor/composite/unknown or otherwise unresolved CA mapping, including no-position/re-entry cases;
- multi-stock state isolation and period-end pending preservation;
- retired rolling-window prices excluded from later CA transform/availability decisions.

The interface and future wiring order are documented in `docs/BASELINE_60D_EXIT_STATE_INTERFACE.md`.

This is a state/intent module only. It never creates a Fill, never mutates canonical accounting, and does not make the baseline executable.

## Explicitly still blocked / not wired

1. The two baseline exit names are compiled only for the exact approved pair and parameters; no generic ATR-from-entry or N-day-low parameter surface is exposed.
2. CanonicalStrategySimulator consumes the baseline plan only when BaselineSimulationContext is explicitly supplied. Legacy runs remain on the existing stop/max-hold path.
3. FORMAL_RESEARCH is unconditionally blocked in this revision. FeaturePanelIntegrator verifies availability/manifest/epoch/artifact SHA256 during hydration, but there is no canonical evidence object bound to the exact PreparedResearchRun for the simulator to consume. Caller-declared VERIFIED/source text cannot unlock formal simulation.
4. CA technical approval is per-event evidence input with an explicit source. The simulator does not infer approval from accounting-layer event presence.
5. Successor/composite/unknown mappings remain technical BLOCKED and owned by canonical lifecycle; no new successor matcher or multi-leg strategy exit logic is added.
6. No formal baseline run config, real E1 run, E2/E3 query, workflow, scan, or strategy report is created by this integration.

## Local verification scope

State-module regressions remain in tests/test_baseline_60d_exit_state.py.

Canonical synthetic E2E is in tests/test_baseline_60d_simulator_integration.py and uses temporary synthetic configs plus parquet fixtures while exercising the real package path:

- ResearchConfigEngine prepare -> exact ExitCompiler -> prepared exit plan -> CanonicalStrategySimulator;
- ATR, LOW20 and BOTH close triggers -> next-open canonical sell;
- multi-day sell_blocked persistence;
- cash dividend and split technical-coordinate transforms alongside canonical quantity/cash accounting;
- opening terminal precedence over old pending strategy exit;
- successor lifecycle remains traceable BLOCKED;
- prior-close same-ticker signal cannot sell then re-buy at the same open;
- SideAwareBpsFeeModel + FixedBpsSlippage applied by the canonical fill factory once per fill;
- period-end pending/open holding preservation;
- legacy non-opt-in stop/max-hold path regression;
- FORMAL_RESEARCH enum and normalized string modes reject UNAVAILABLE/UNKNOWN and also reject caller-declared VERIFIED before market-data reads, order creation or holding mutation;
- null/unknown mode or availability input is rejected during context construction, while recognized synthetic strings normalize safely;
- exact compiler parameter/mix fail-closed regressions include non-boolean bool inputs, non-integer windows/periods, and NaN/Inf rejection.

These tests are software integration evidence only, not baseline effectiveness evidence.

## CI verification

- Prior preparation CI remains historical evidence only: GitHub `tests` workflow `37161695576` passed.
- The dependent integration branch requires its own `tests` workflow before Astra acceptance; the latest branch CI status is reported in Draft PR #4.
- Existing legacy breakout final-NAV boolean regression workflow `37161695551`: **success**.
- Strategy-effect publication/sensitivity workflows triggered by the D software commit were **skipped** by the `[no-effects]` guard.
- No baseline backtest, E2/E3 effect query, VCP Round 2, or other strategy scan was executed by this preparation step.
