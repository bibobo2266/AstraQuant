# baseline_60d_breakout_v1 — Exit-State Module Interface

Status: **SYNTHETICALLY TESTED STATE MODULE / NOT WIRED TO CANONICAL SIMULATOR / NOT A STRATEGY RUN**

Frozen implementation base: `4be871dd031f655b5453836f37eeb0d85c158340`.

This module implements only the owner-authorized TRANSLATED exit-state semantics for the 60-day breakout baseline. It does not register a runnable exit component, does not create orders or fills, does not mutate canonical accounting, and does not authorize any E1/E2/E3 strategy-effect run.

## Module

Implementation:

- `src/astraquant/research/baseline_60d_exit_state.py`
- state owner: `Baseline60DExitState`

The existing math-only helpers in `baseline_60d_breakout.py` remain unchanged.

## Canonical-facing inputs

The state module consumes objects compatible with existing canonical boundaries:

1. **entry fill**
   - existing `portfolio.models.Fill`;
   - must be a canonical BUY fill;
   - `entry_anchor = fill.price`;
   - `fill.fees` is audit-only and never added to the technical anchor.

2. **valid-bar observation**
   - `BaselineBarInput`;
   - caller supplies a trusted `session_index`;
   - the module does not infer a complete exchange calendar from ticker rows;
   - only observed, valid, finite, positive OHLC with valid geometry enters the rolling sequence.

3. **approved corporate action batch**
   - wraps existing `HistoricalCorporateActionInstruction`;
   - the iterable is materialized before validation, so list and generator inputs have the same semantics;
   - caller must explicitly set `approved_for_technical_transform=True`;
   - equal duplicate event IDs are deduplicated; conflicting definitions for the same ID reject the call before any transform;
   - `known_at`, source declaration, effective time, and caller-supplied decision cutoff are checked before use;
   - all simple cash/share events for one ticker/opening must be supplied in one complete batch. A later new event for the same finalized opening is BLOCKED as `OPENING_CA_BATCH_ALREADY_FINALIZED`; it is not silently applied as a second coordinate transform.

4. **open execution result**
   - `BaselineOpenExecutionResult` binds `report_id`, pending `intent_id`, entry `fill_id`, session date/index, and the canonical before/after position quantity;
   - SELL_BLOCKED / NO_VALID_OPEN / NOT_EXECUTABLE retain the original pending intent;
   - only a matching canonical SELL `Fill` whose quantity equals canonical pre-fill quantity and whose canonical post-fill quantity is zero clears the technical holding;
   - partial fill/remaining position is unsupported in this module and is rejected without changing pending state or attempt counters;
   - duplicate and stale execution reports are explicit errors.

5. **terminal/lifecycle result**
   - `BaselineTerminalResult`;
   - EXTINGUISHED clears technical holding state and archives any pending strategy reason as superseded;
   - successor/composite/unknown mapping uses CANONICAL_LIFECYCLE_REQUIRED and preserves holding/pending identity.

## Rolling observation contract

ATR14 and LOW20 share one stock-specific **bounded** valid-observed-bar sequence. The technical window retains at most 21 valid bars: current + prior 20. This is sufficient for LOW20 and for ATR14 including the predecessor close needed by the retained ATR window.

- suspension/no observation: no bar added;
- invalid OHLC: no bar added;
- no forward fill;
- TR uses the previous valid observed close; the first retained observation uses high-low;
- ATR14 is SMA(TR,14), including the current valid bar;
- LOW20 is min(close) over the previous 20 valid bars, excluding current;
- LOW20 uses strict `close < reference`;
- ATR uses `close <= entry_anchor - 3*ATR14`;
- insufficient observations remain UNKNOWN.

The active-window audit keeps:
- valid observation count;
- trusted-session span;
- skipped-session count inside the rolling window;
- retained gap reasons.

Bars retired beyond the 21-bar technical window are reduced to a separate count-only audit. Retired prices never participate in later ATR/LOW20 evaluation, CA price transformation, or technical availability decisions.

Therefore “20 observations” is not reported as “20 consecutive trading sessions”.

## CA technical-coordinate contract

For simple approved cash/share economics applied at the opening:

`P_post = (P_pre - c) / m`

where:
- `c` is the sum of approved same-opening cash-per-share components;
- `m` is the product of approved same-opening share multipliers.

The transform is applied once, with no per-event rounding, to:
- entry anchor when the position predates the event;
- every retained OHLC value;
- therefore the previous-valid-close relation, ATR true-range state, and LOW20 history all remain on one coordinate.

The module does **not** mutate canonical quantity, receivable, cash, avg-cost, or successor accounting.

Fail closed / BLOCKED:
- missing or late `known_at`;
- undeclared source;
- technical transform not explicitly approved;
- non-finite / non-positive transformed technical prices;
- successor, composite conversion, extinguishment instruction, RIGHTS, MERGER, OTHER, or another non-unique mapping.

Duplicate event IDs are audit-idempotent and are not transformed twice. The input contract is transactional at each ticker/opening: a conflicting event-ID definition is rejected before mutation, and a simple cash/share transform is planned in full before the retained rolling state or entry anchor is replaced.

## Persistent ticker technical availability

A technical BLOCKED state belongs to the ticker's technical history, not only to the current holding.

- a blocked CA/lifecycle mapping is retained even if no position exists;
- a later entry inherits the existing technical block;
- strategy exit, terminal extinguishment, or rebuilding a holding does not automatically clear the block;
- while blocked, new bars are not appended to the technical rolling window and existing pending intent is preserved;
- this module defines no recovery/unblock operation. Recovery requires a separately approved canonical resolution contract.

## Pending exit contract

At a valid close:
- ATR true + LOW20 true on the same close -> one pending intent with reason BOTH;
- ATR true only -> ATR;
- LOW20 true only -> LOW20;
- if a rule is not warm, that rule remains UNKNOWN;
- once any rule establishes an exit, the pending intent is sticky;
- later recovery never cancels it;
- a later secondary trigger never rewrites the original reason to BOTH.

A trigger on the entry session is allowed. The earliest executable session index is trigger index + 1.

The module emits/retains intent state only. It never manufactures an execution fill.

## Required opening order for future simulator wiring

The canonical historical runner already establishes settlement -> opening CA -> trades. The current `CanonicalStrategySimulator` establishes settlement -> opening CA -> opening entries, but has no generic pending-close-exit stage.

Future baseline wiring must insert the new state transition without changing existing accounting order:

1. settlement / due CA cash;
2. opening canonical CA/lifecycle application;
3. update baseline technical CA coordinate;
4. if terminal already extinguished the position, terminal wins;
5. attempt existing baseline pending exit through canonical RAW open execution;
6. only after that process prior-close entry intents;
7. at close, ingest the valid observed bar and evaluate ATR/LOW20;
8. close-applied terminal lifecycle may supersede a newly-created pending strategy intent.

This repository change does not perform that wiring.

## Successor boundary

This module intentionally does **not** implement successor remapping, multi-leg allocation, or rolling-state reset/re-warm.

On successor/composite/unknown mapping:
- the original ticker holding identity is retained inside this module;
- pending reason is retained;
- technical evaluation is BLOCKED with CANONICAL_LIFECYCLE_REQUIRED;
- canonical lifecycle remains responsible for economic mutation;
- no position is silently extinguished and no strategy sell is fabricated.

## Synthetic acceptance

`tests/test_baseline_60d_exit_state.py` covers:

- ATR14 SMA/current inclusion;
- LOW20 prior-20 exclusion and strict equality boundary;
- warmup UNKNOWN;
- suspension and invalid-OHLC gaps;
- cash dividend, split, and same-opening cash+share coordinate transforms;
- entry fee separation;
- duplicate CA idempotency, same-ID conflict rejection, list/generator equivalence, and split-opening-batch blocking;
- entry-session close trigger / next-session earliest execution;
- sticky pending through repeated blocked opens;
- BOTH immutability and later-secondary-trigger immutability;
- canonical SELL full-liquidation report as the only strategy-exit clear signal;
- pending/holding/session binding, partial-fill rejection, duplicate/stale execution-report handling;
- terminal precedence;
- successor and unknown-CA BLOCKED states;
- late-known and non-positive CA failure;
- ticker-level BLOCKED persistence across no-position/entry/terminal/re-entry;
- bounded 21-bar rolling state and retirement of old prices before later CA transforms;
- multi-stock isolation;
- period-end pending preservation.

These are synthetic software acceptance tests only. They are not PIT validation, strategy-effect evidence, or a baseline backtest.
