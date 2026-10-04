# baseline_60d_breakout_v1 — local readiness after causal RAW v2

Status date: 2026-10-04  
Status: **EXIT-STATE MODULE COMPLETE / CANONICAL SIMULATOR NOT WIRED / NOT EXECUTABLE / NOT BACKTESTED**

This document records only the owner-authorized engineering preparation for `baseline_60d_breakout_v1`. The exit-state semantics listed below were explicitly authorized for this module, but the module is not registered as an executable strategy exit and is not wired into the canonical simulator. No E1 strategy backtest or E2/E3 effect query is run.

## Reuse confirmed

| requirement | current reusable path | status |
| --- | --- | --- |
| 60-session first breakout | `N_SESSION_HIGH lookback=60` | implemented; AstraQuant strict first-cross `>` semantics retained |
| price at/above MA120 | hydrated `close_to_ma120` + `COLUMN_THRESHOLD min=0.0` | no `PRICE_ABOVE_MA` evaluator is needed |
| prior-20-session amount >= TWD 20m | causal RAW v2 `prior20_amount_twd` + `COLUMN_THRESHOLD min=20000000` | computation exists; real-data availability gate remains blocked |
| RAW next-open execution / tradability | canonical execution stack | already implemented; no baseline-specific execution path added |
| accounting / terminal lifecycle | canonical portfolio stack | unchanged |

The old `configs/drafts/baseline/baseline_livermore_v1.yaml` still contains `PRICE_ABOVE_MA`; it is a historical draft and is **not** promoted or reused as the executable baseline config.

## Exit-state module now implemented in isolation

The existing math-only helpers in `src/astraquant/research/baseline_60d_breakout.py` remain unchanged.

`src/astraquant/research/baseline_60d_exit_state.py` now implements the separately authorized state module for:

- one stock-specific valid-observed-OHLC sequence shared by ATR14 and LOW20;
- ATR14 = SMA(TR,14), including current valid bar;
- LOW20 = minimum of the prior 20 valid observed closes, excluding current;
- explicit UNKNOWN during insufficient warmup or missing/invalid current observation;
- entry anchor from canonical `Fill.price`, excluding fees;
- approved simple cash/share technical-coordinate transform `P_post=(P_pre-c)/m` across entry anchor and the retained OHLC history;
- same-opening cash + share aggregation without per-event rounding;
- duplicate-CA idempotency;
- sticky pending ATR / LOW20 / BOTH intent;
- next-session-or-later open eligibility only;
- blocked-open persistence;
- terminal precedence;
- successor/composite/unknown mapping as `CANONICAL_LIFECYCLE_REQUIRED` without local remapping or position destruction;
- multi-stock state isolation and period-end pending preservation.

The interface and future wiring order are documented in `docs/BASELINE_60D_EXIT_STATE_INTERFACE.md`.

This is a state/intent module only. It never creates a Fill, never mutates canonical accounting, and does not make the baseline executable.

## Explicitly still blocked / not wired

1. `ATR_FROM_ENTRY_STOP` and `BREAK_N_DAY_LOW` remain **unregistered** in the default `ExitCompiler`; the new state module is not a registry declaration of executable strategy behavior.
2. `ResearchConfigEngine.simulate_prepared()` still does not pass a baseline close-exit state contract into the canonical simulator.
3. `CanonicalStrategySimulator` is unchanged and still runs its existing RAW fixed-stop / max-hold lifecycle. The baseline pending-close-exit state is **not wired**.
4. Opening successor/composite handling remains owned by the canonical lifecycle. The baseline module returns an explicit blocked/lifecycle-required state and performs no successor remapping.
5. causal RAW v2 real E1 input availability remains blocked by the item-5 gate. Synthetic state tests are not substituted for real-data validation.
6. No formal baseline run config, E1 baseline run, E2/E3 effect query, or strategy report is created by this change.

## Local verification scope

Existing math-preparation tests remain in place. New synthetic acceptance is in `tests/test_baseline_60d_exit_state.py` and covers:

- ATR14 SMA/current inclusion and LOW20 prior-window/equality semantics;
- warmup, suspension, invalid OHLC, retained gap reason/session-span audit;
- cash dividend, split, and same-opening cash+share coordinate transforms;
- entry fee separation and duplicate-CA idempotency;
- entry-session close trigger with next-session earliest execution;
- sticky pending through sell-blocked / missing-open attempts;
- BOTH immutability and later secondary-trigger non-rewrite;
- terminal precedence without duplicate strategy exit;
- successor and unknown-CA fail-closed behavior;
- multi-stock isolation;
- period-end pending preservation.

A formal baseline run config, simulator wiring, real E1 run, and strategy report remain outside this preparation step.

## CI verification

- Prior preparation CI remains historical evidence only: GitHub `tests` workflow `37161695576` passed.
- This branch requires its own `tests` workflow before Astra acceptance; branch CI status is reported in the PR.
- Existing legacy breakout final-NAV boolean regression workflow `37161695551`: **success**.
- Strategy-effect publication/sensitivity workflows triggered by the D software commit were **skipped** by the `[no-effects]` guard.
- No baseline backtest, E2/E3 effect query, VCP Round 2, or other strategy scan was executed by this preparation step.
