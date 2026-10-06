# baseline_60d_breakout_v1 — Exit-State Module Interface

Status: **SYNTHETIC CANONICAL INTEGRATION / FORMAL DATA GATE BLOCKED / NOT A STRATEGY RUN**

Frozen implementation base: `4be871dd031f655b5453836f37eeb0d85c158340`.

This interface describes the owner-authorized TRANSLATED exit-state semantics and the dependent synthetic integration into the canonical simulator. The state module still does not manufacture fills or mutate canonical accounting. The simulator integration is opt-in and uses canonical RAW execution. Formal baseline research remains fail-closed behind the existing PIT/data gate; no E1/E2/E3 strategy-effect run is authorized.

## Module

Implementation:

- `src/astraquant/research/baseline_60d_exit_state.py`
- state owner: `Baseline60DExitState`

The existing math-only helpers in `baseline_60d_breakout.py` remain unchanged.

## Compiled baseline contract and opt-in boundary

The default ExitCompiler now recognizes the two baseline names only under one exact fixed contract:

- ATR_FROM_ENTRY_STOP: period=14, multiplier=3.0, smoothing=SMA, trigger_field=CLOSE, execution=NEXT_OPEN, observation_basis=VALID_OBSERVED_OHLC.
- BREAK_N_DAY_LOW: window=20, field=CLOSE, exclude_current=true, strict=true, execution=NEXT_OPEN, observation_basis=VALID_OBSERVED_OHLC.
- both rules are required together;
- first_trigger_wins must be false so a same-close dual trigger can be classified BOTH;
- fixed-stop, TIME_EXIT, ATR_TRAILING, MA_BREAK, or another close rule cannot be mixed into this baseline plan.

Exact scalar validation is non-lossy:
- boolean parameters must be actual YAML/Python booleans; strings such as "false" and integers such as 1 are rejected;
- integer parameters must be actual integers; floats such as 14.0 or 20.9 are rejected;
- numeric multiplier values may be integer or float only, must be finite, and must equal the frozen value;
- string enum-like parameters must be strings and are normalized only by trim + uppercase before exact comparison;
- NaN/Inf and unsupported values are rejected.

A compiled exact pair causes apply_to_policy() to disable legacy stop_fraction and max_hold_sessions. Non-baseline exit plans retain their existing behavior.

ResearchConfigEngine passes PreparedResearchRun.exit_plan to CanonicalStrategySimulator. The baseline path is activated only when the exact compiled pair is accompanied by an explicit BaselineSimulationContext.

BaselineSimulationContext separates:
- SYNTHETIC_FIXTURE: the only executable mode in this revision, for software acceptance only;
- FORMAL_RESEARCH: unconditionally fail-closed in this revision.

Mode and availability inputs are normalized only from their enum instances or recognized case-insensitive strings. Null, blank, unknown, or non-string/non-enum values are rejected during context construction; they cannot fall through to synthetic behavior.

The existing FeaturePanelIntegrator already validates declared availability, manifest identity, epoch and artifact SHA256 during hydration. However, it does not currently return a canonical simulator-verifiable eligibility object bound to the exact PreparedResearchRun. Therefore caller-supplied VERIFIED plus free-form source text is not accepted as formal evidence. FORMAL_RESEARCH remains blocked until a separately reviewed canonical handoff exists; this integration does not create a parallel gate.

Corporate-action technical transforms also require an event-specific BaselineCATechnicalApproval with an explicit source. Presence of a canonical accounting event never auto-approves the technical transform.

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

## Canonical opt-in event order now implemented for synthetic integration

The canonical historical runner already establishes settlement -> opening CA -> trades. The current `CanonicalStrategySimulator` establishes settlement -> opening CA -> opening entries, but has no generic pending-close-exit stage.

The opt-in baseline path now uses the following order without changing canonical accounting:

1. settlement / due CA cash;
2. opening canonical CA/lifecycle application;
3. update baseline technical CA coordinate;
4. if terminal already extinguished the position, terminal wins;
5. attempt existing baseline pending exit through canonical RAW open execution;
6. only after that process prior-close entry intents;
7. at close, ingest the valid observed bar and evaluate ATR/LOW20;
8. close-applied terminal lifecycle may supersede a newly-created pending strategy intent.

The integration uses CanonicalExecutionService for pending EXIT/open fills. Non-executable open attempts retain the original pending state. Only the canonical post-fill position quantity of zero permits the state module to clear a strategy holding.

## Same-ticker re-entry boundary

For the opt-in baseline path, the simulator records which tickers were held at the prior close. A candidate formed at that close is not eligible to buy at the next open if the ticker was held when the signal formed, even if an older pending exit is successfully sold first at that same open.

A genuinely new signal formed at the close after the sale remains eligible for the following session open, subject to the existing canonical policy and execution constraints.

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

State-level tests remain synthetic software acceptance only. The dependent integration tests additionally exercise real ResearchConfigEngine preparation, exact ExitCompiler compilation, CanonicalStrategySimulator event ordering, RAW ExecutionMarketData, CanonicalExecutionService fills, fee/slippage models, portfolio accounting, settlement state, CA lifecycle and terminal precedence. They are still not PIT validation, strategy-effect evidence, or a baseline backtest.
