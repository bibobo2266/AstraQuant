# Sol handoff — 2026-10-04 — tasks A, B, D

## Scope and branch state

- Starting `main`: `e9895b43c438be739df99e1ae8f79a019a5b051c`.
- C was reassigned to the second Sol and was not touched here.
- Data/epoch gates were preserved: no E2/E3 effect query, no OOS unlock, no strategy promotion, no VCP Round 2, and no formal 60-day baseline backtest.
- Final code-bearing commit for this work: `76f267b567a690e9998f57fce2ba458ae4aba84e`.

## What changed and why

### Task A — minimal causal RAW v2

Implementation commit: `129ef0a2b42f96a784ae703a4aba6d26c6db5804`.

Added:

- `src/astraquant/research/causal_raw_v2.py`
- `configs/quality/layer1_60d_ma120_causal_raw_v2.yaml`
- `tests/test_causal_raw_v2.py`

New capability:

- RAW absolute close can be used for the existing universe absolute-price eligibility coordinate without changing thresholds.
- Frozen MA120, strict first-cross N60, and prior-20 common-session amount are computed on a causal in-memory price coordinate.
- Corporate actions are applied only when effective and known before the explicit decision cutoff; future events never rewrite earlier emitted rows.
- Event days without a market row are applied once before the first later observation.
- Missing/suspended common-session rows remain missing; N60 insufficient history is nullable rather than false.
- Only already-normalized cash/stock dividend components are accepted; unsupported/non-dividend transforms remain fail-closed rather than inferred.

No existing v1 artifact, signal threshold, execution/accounting, terminal lifecycle, or VCP Round 1 result was overwritten.

### Workflow safety guard

Commit: `738e6bdab7a2b9afd954018b46dcd57e88adf7dd`.

The A implementation push exposed that several strategy-effect workflows auto-ran on any `src/astraquant/**` change. Ten effect publication/sensitivity workflows now honor a `[no-effects]` commit marker at the job level. Explicit `workflow_dispatch` remains available. This was necessary so software/data maintenance can be integrated without implicitly authorizing effect scans.

The two failures from the unguarded `129ef0a2` push were report-writeback failures (`git pull --rebase` rejected unstaged changes), not failed research calculations; those runs were outside the intended scope and are not used as evidence here.

### Task B — integration/acceptance evidence

Commits: `9eb825e290eea9fb996ec687cadd977ae52d8991`, status update `e5bff96fdcd9d5ab64ff0d4e3af65f02302bee8a`.

Added:

- `tests/test_causal_raw_v2_integration.py`
- `docs/PIT_FEATURE_LAYER1_CAUSAL_RAW_V2_STATUS.md`

Verified with real Parquet fixtures in CI that the existing `FeaturePanelIntegrator` preserves exact keys, reads the requested v2 fields, pins formula/source revision, carries the causal coordinate field, enforces source availability before cutoff, distinguishes warmup nulls, and blocks E2 keys before artifact loading.

No real E1 v2 feature artifact was produced because the required data-availability gate is not cleared.

### Task D — 60-day breakout baseline local preparation

Implementation commit: `76f267b567a690e9998f57fce2ba458ae4aba84e`.

Added:

- `src/astraquant/research/baseline_60d_breakout.py`
- `tests/test_baseline_60d_breakout_prep.py`
- `docs/BASELINE_60D_BREAKOUT_READINESS.md`

Only unambiguous math was implemented:

- ATR14 uses rolling SMA, not Wilder.
- stop level is entry anchor minus 3×current ATR14.
- ATR comparator is close <= threshold.
- prior-low comparator is strict close < reference.
- missing comparator inputs remain unknown.
- MA120 and prior20 amount are confirmed reusable through `COLUMN_THRESHOLD` at 0.0 and TWD 20,000,000 respectively.

Deliberately not done:

- `ATR_FROM_ENTRY_STOP` and `BREAK_N_DAY_LOW` are still unregistered and compile fail-closed.
- no generic close-rule state was wired into `CanonicalStrategySimulator`.
- no baseline run config was promoted.
- no CA technical-state transform, pending-next-open lifecycle, BOTH ordering, successor reset, or 20D valid-observed reference was invented while the spec still marks those choices pending.

## Verification actually run

- A local synthetic core: 14 tests passed; Python compile check passed.
- B CI: GitHub `tests` workflow `37161408316` — **327 passed in 6.51s**.
- D pure-math local smoke: passed.
- D CI: GitHub `tests` workflow `37161695576` — **334 passed in 6.73s**.
- Effect workflows on `[no-effects]` commits: jobs skipped as intended.
- Legacy breakout final-NAV boolean regression for `76f267b5`: `37161695551` — success.

## Artifacts / reports / versions

- v2 formula version: `layer1_60d_ma120_causal_raw_v2`.
- v2 status: `docs/PIT_FEATURE_LAYER1_CAUSAL_RAW_V2_STATUS.md`.
- v2 quality contract: `configs/quality/layer1_60d_ma120_causal_raw_v2.yaml`.
- baseline readiness: `docs/BASELINE_60D_BREAKOUT_READINESS.md`.
- No real-data v2 parquet artifact was produced.
- No baseline strategy result/report was produced.

## Gates

Passed:

- software/unit regression;
- synthetic causal invariance / missingness / event-date behavior;
- Parquet hydration contract and E1 boundary behavior;
- workflow effect-scan opt-out guard for authorized software-only pushes.

Still blocked:

- E1 RAW OHLC historical receipt/publication evidence before order-intent cutoff — UNKNOWN;
- E1 `Trading_money` historical cutoff evidence — UNKNOWN;
- RAW/tradability underlying historical cutoff evidence — UNKNOWN;
- complete historical `known_at` + reconciliation for normalized cash/stock actions — UNKNOWN;
- non-dividend share events in causal RAW v2 — UNAVAILABLE in the current certified normalizer;
- Astra acceptance of item 5;
- baseline CA technical coordinate / valid-observed reference / pending-exit event ordering.

Therefore item 5 is **not** marked accepted, the formal E1 v2 artifact remains blocked, and the 60-day baseline remains **NOT EXECUTABLE / NOT BACKTESTED**.

## Workflow state at handoff

- Strategy-effect workflows for the D commit were skipped by `[no-effects]`.
- `tests` for D completed successfully.
- Legacy regression status: success.
- No authorized data-build or strategy-effect workflow was manually dispatched.

## Next concrete work

1. Astra reviews `129ef0a2` / `9eb825e2` against the item-5 causal RAW v2 contract.
2. Close or explicitly approve fail-closed treatment for the exact item-5 data evidence gaps above; only then may a real E1 v2 feature artifact be produced.
3. Separately, freeze the remaining baseline semantics (CA technical-state handling, 20D observation basis, pending-next-open/event ordering). After that, register/wire the two exit rules through `ExitCompiler` → `ResearchConfigEngine` → canonical simulator and add synthetic end-to-end tests.
4. A formal 60-day baseline E1 backtest remains a later explicit step after both the data gate and baseline semantics are cleared.

## Owner decisions needed

None at this handoff. The unresolved items are review/specification gates already assigned to Astra; no owner risk preference or OOS decision is required for the completed A/B/D scope.