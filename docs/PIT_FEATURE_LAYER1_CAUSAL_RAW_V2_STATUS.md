# PIT Feature Layer 1 — causal RAW v2 implementation status

Status date: 2026-10-04  
Implementation commit: `129ef0a2b42f96a784ae703a4aba6d26c6db5804`  
Known-at precision fix: `a38abad253d8e319e3d034f6b4985b67399846d5`  
Gate closure: `docs/PIT_FEATURE_LAYER1_CAUSAL_RAW_V2_GATE_CLOSURE.md`  
Review status: **PROGRAM IMPLEMENTED / DATA GATE BLOCKED WITH ACTIONABLE GAPS / ASTRA REVIEW PENDING**

This status record implements the already approved minimal `layer1_60d_ma120_causal_raw_v2` direction. It does not reopen the data plan, does not unlock OOS, does not promote a strategy, and contains no strategy-effect query.

## What is now implemented

- `src/astraquant/research/causal_raw_v2.py`
  - RAW absolute close adapter for the existing universe compiler; no eligibility threshold changes.
  - Frozen `MA120`, `N60`, and prior-20-session amount windows.
  - Common-session semantics: suspension / absent observations remain null rows and are not time-compressed.
  - `N60` keeps the existing strict first-cross rule, but insufficient or non-comparable history is nullable rather than being converted to `False`.
  - Corporate-action state accepts only the already normalized cash-dividend and stock-dividend components. It applies an event only after the event is effective and `known_at < decision_cutoff_at`.
  - Historical observations retained inside a rolling window are transformed into the current causal RAW coordinate with `P_post=(P_pre-cash)/share_multiplier`, without per-event rounding.
  - Future events never rewrite already emitted feature rows. An earlier unresolved effective event blocks later event application instead of allowing an out-of-order coordinate jump.
- `configs/quality/layer1_60d_ma120_causal_raw_v2.yaml`
  - freezes source revision, windows, coordinate semantics, missingness semantics, and the current fail-closed data gate.
  - keeps the v1 artifact preserved and declares no formal v2 E1 artifact while required availability evidence is incomplete.

No execution, accounting, terminal lifecycle, signal thresholds, VCP Round 1 result, or strategy simulator behavior was changed for this implementation.

## Verification evidence

Local synthetic verification after implementation:

- causal RAW v2 core: 14 tests passed;
- core + v2/hydration integration: 18 targeted tests are included in the repository suite;
- Python compile check passed;
- repository `tests` workflow for implementation commit `129ef0a2` completed successfully;\n- repository `tests` workflow `37161408316` for hydration-evidence commit `9eb825e2` completed successfully: **327 passed in 6.51s**.

Covered cases include:

1. adding a future corporate action does not change earlier feature rows;
2. a corporate action effective on a non-market day is applied once at the first later observation;
3. same-date cash/share components use one consistent coordinate without rounding drift;
4. an effective but not-yet-known event blocks MA120/N60 comparability until it is actually available;
5. an event with unknown `known_at` remains fail-closed;
6. a prior unresolved event prevents a later event from being applied out of order;
7. `known_at == decision_cutoff_at` is not treated as available;
8. MA120/N60 comparability flags agree with their explicit feature states;
9. N60 warmup/missing history is null, not a false breakout result;
10. prior-20 amount excludes the current session and preserves missing common-session rows;
11. hydration preserves logical row count and the v2 formula/coordinate fields;
12. hydration rejects source data available at or after the decision cutoff;
13. an E1-only hydration request rejects an E2 key before artifact loading.

The local sandbox does not provide `pyarrow`, so Parquet-backed hydration is intentionally verified in the repository CI environment declared by `pyproject.toml`. The committed v2 integration test writes an actual Parquet fixture and exercises the production `FeaturePanelIntegrator`, including manifest version/source checks, exact-key hydration, cutoff enforcement, warmup missing reasons, and E1-only rejection.

## Workflow execution guard

Commit `738e6bdab7a2b9afd954018b46dcd57e88adf7dd` adds a `[no-effects]` push guard to the strategy-effect publication/sensitivity workflows. This keeps explicit `workflow_dispatch` available, while software/data-only maintenance commits carrying the marker skip those effect jobs. The guard was added after commit `129ef0a2` unintentionally triggered the existing broad `src/astraquant/**` push paths. It does not loosen epoch or data gates.

## Data gate — still blocked, now narrowed to specific evidence gaps

The evidence-only audit in workflow `37165519596` completed its calculation
successfully against fixed source revision
`fb8b042b46dc38838d103544ca17da10286c7bfe`. Its final git writeback failed
after calculation; per owner instruction the successful calculation was not
rerun. Aggregate evidence was recovered from the job log and recorded in
`docs/PIT_FEATURE_LAYER1_CAUSAL_RAW_V2_GATE_CLOSURE.md`.

The gate is no longer summarized as a generic lack of receipt timestamps:

| dependency | evidence now established | remaining blocker |
| --- | --- | --- |
| RAW OHLC | 3,306,022 warmup+E1 rows; source mix and null scope measured; TWSE/TPEx/FinMind publication rules support publication before the existing T+1 00:00 cutoff | frozen values are Sep-2026 reconstructions; historical as-published version/correction lineage is not retained |
| Trading_money | 0 nulls on stored RAW keys; official/provider publication rules support the same cutoff | same historical-version identity gap as RAW |
| observed_trade / valid_ohlc | 0 reconstruction mismatches, 0 observed-without-RAW, 0 RAW-marked-unobserved; 11,287 explicit missing rows | availability inherits the unresolved RAW historical-version evidence |
| buy_blocked / sell_blocked | retained as execution fields | not a prerequisite for the minimal MA120/N60/prior20 feature artifact; no execution gate is relaxed |
| cash/stock actions | 10,097 normalized components; exact AnnouncementDate+AnnouncementTime is retained for all 10,097 frozen components; component-level bidirectional reconciliation is complete at program `9914525f`; private run `37171913233` conserves 11,156 economic event groups | dependency remains UNKNOWN: 142 evidence-backed missing-source events, 5 value/unit conflicts, 6,410 insufficient-evidence groups, source-specific stock-unit/par-value proof and historical revision lineage remain unresolved; the previously identified 6 late-for-first-cutoff components remain fail-closed |
| non-dividend share events | exact aggregate scope measured: 386 rows / 310 tickers | 385 known_date missing, 209 multiplier missing/invalid; 375 MA120-impact and 364 N60-impact event windows remain unavailable to the certified v2 normalizer |

The independent official reconciliation starts from the union of official
event groups and normalized effective-date groups rather than from FinMind rows
alone. The completed component-level closure is
`docs/CA_DIVIDEND_COMPONENT_RECONCILIATION_CLOSURE.md`. The earlier 2,172
official-only candidates are no longer treated as one missing count: only 142
currently meet the evidence-backed missing-source class, 5 event groups are
value/unit conflicts, and 6,410 event groups remain insufficient evidence.
A private 147-row versioned review candidate file contains the 142 supplement
candidates plus the 5 conflicts.

The minimal feature route remains independent of TRI, industry, chip, and
fundamental datasets. No stock/year is silently removed, no multiplier or
known_at is guessed, and no population scope is changed.

## Artifact decision

No formal E1 causal RAW v2 feature artifact is produced from real source data in this state. The evidence-only audit is a data-quality/availability audit, not the formal feature artifact and not a strategy backtest.

The requested CA component/economic reconciliation is complete and now waits for Astra review. RAW/Trading_money historical-version evidence and the 386 non-dividend share-event rows remain separate item-5 blockers and were not expanded in this round.

Astra still must validate the CA closure and private candidate set. Until then, item 5 remains IN_PROGRESS and dependent strategy work remains blocked.