# baseline_60d_breakout_v1 — local readiness after causal RAW v2

Status date: 2026-10-04  
Status: **PARTIAL LOCAL PREP / NOT EXECUTABLE / NOT BACKTESTED**

This document records only the work allowed by the existing `baseline_60d_breakout_v1` specification and the owner-authorized local-preparation scope. It does not freeze any rule that the baseline spec still marks as pending review, does not run an E1 strategy backtest, and does not query E2/E3 effects.

## Reuse confirmed

| requirement | current reusable path | status |
| --- | --- | --- |
| 60-session first breakout | `N_SESSION_HIGH lookback=60` | implemented; AstraQuant strict first-cross `>` semantics retained |
| price at/above MA120 | hydrated `close_to_ma120` + `COLUMN_THRESHOLD min=0.0` | no `PRICE_ABOVE_MA` evaluator is needed |
| prior-20-session amount >= TWD 20m | causal RAW v2 `prior20_amount_twd` + `COLUMN_THRESHOLD min=20000000` | computation exists; real-data availability gate remains blocked |
| RAW next-open execution / tradability | canonical execution stack | already implemented; no baseline-specific execution path added |
| accounting / terminal lifecycle | canonical portfolio stack | unchanged |

The old `configs/drafts/baseline/baseline_livermore_v1.yaml` still contains `PRICE_ABOVE_MA`; it is a historical draft and is **not** promoted or reused as the executable baseline config.

## Frozen exit math now isolated

`src/astraquant/research/baseline_60d_breakout.py` adds math-only helpers for the pieces whose numerical semantics are already fixed:

- ATR period = 14;
- ATR smoothing = rolling **SMA**, not Wilder;
- ATR stop level = `entry_anchor - 3 * ATR14_t`;
- ATR trigger comparator = `close_t <= stop_level_t`;
- 20-day-low trigger comparator = strict `close_t < prior_low_reference_t`;
- missing comparator inputs remain unknown (`pd.NA`), not `False`.

The helper deliberately accepts an already-approved true-range sequence / prior-low reference. It does **not** choose the unresolved corporate-action price transform, valid-observed-bar sequence, pending-exit persistence, or event ordering.

## Explicitly still blocked / not wired

1. `ATR_FROM_ENTRY_STOP` and `BREAK_N_DAY_LOW` remain **unregistered** in the default `ExitCompiler`; attempting to compile them still raises `UnsupportedComponentError`. This prevents a registry name from being mistaken for runnable behavior.
2. `ResearchConfigEngine.simulate_prepared()` still passes candidates and corporate actions only; it does not pass `prepared.exit_plan.close_exit_rules` into the canonical simulator.
3. `CanonicalStrategySimulator` still executes its existing RAW fixed-stop and max-hold lifecycle. No generic close-rule pending-next-open state was added.
4. The baseline spec still marks the CA-normalized technical state / successor handling and close-exit event ordering as pending review. Those behaviors were not inferred here.
5. The exact 20D reference observation basis remains pending in the baseline spec. Only the strict comparator is implemented here.
6. causal RAW v2 real E1 input availability remains blocked by the item-5 gate. Synthetic tests are not substituted for real-data validation.

## Local verification scope

The dedicated tests lock:

- ATR14 rolling SMA differs from Wilder after the seed;
- the entry-anchor threshold can move up or down solely because ATR updates and never uses a high-watermark input;
- `<=` for ATR and strict `<` for prior-low;
- MA120 and prior20 amount reuse `COLUMN_THRESHOLD` at the frozen thresholds;
- both not-yet-wired exit component names remain fail-closed in `ExitCompiler`.

A formal baseline run config, simulator close-rule wiring, real E1 run, and strategy report remain outside this preparation step.