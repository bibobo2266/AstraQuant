# 60 日突破基線 — 探索實測 runner 準備

Status: **SYNTHETIC E2E RUNNABLE / REAL E1 NOT RUN / FORMAL_RESEARCH BLOCKED**

Task: `AQ-EXP-RUNNER-001` revision 2

This is execution preparation for the single frozen translated
`baseline_60d_breakout_v1` method. It is not a parameter sweep, not an ML
pipeline, and not evidence that the strategy is effective.

## Fixed method

The executable method files are:

- `configs/research/baseline_60d_breakout_v1/signal.yaml`
- `configs/research/baseline_60d_breakout_v1/exit.yaml`
- `configs/research/baseline_60d_breakout_v1/run.yaml`
- `configs/research/baseline_60d_breakout_v1/exploration.yaml`

`exploration.yaml` is validated against one exact contract in
`baseline_60d_exploration.py`; drift fails closed.

Frozen items:

- E1 method period: 2016-01-04 through 2021-12-31.
- universe: existing `all_liquid` plus frozen P2-060 exclusion digest.
- entry trigger: existing first-cross `N_SESSION_HIGH lookback=60`.
- MA120 filter: `close_to_ma120 >= 0.0`.
- liquidity filter: `prior20_amount_twd >= 20,000,000`, with the already
  frozen prior-only/common-session semantics supplied by the hydrated feature.
- entry: next canonical RAW open; no adjusted-price execution fallback.
- exits: ATR14 SMA from entry anchor, multiplier 3.0, close-confirmed
  `<= threshold`; and prior-20 valid-close low, current excluded, strict
  `close < reference`; sticky pending to next legal canonical RAW open.
- costs: buy fee 14.25 bps; sell fee+tax 44.25 bps; adverse slippage 10 bps
  each side; canonical cost model applies these once.
- settlement lag: 2 sessions.
- no forced period-end liquidation.
- MFE/MAE: diagnostic only.
- positive-return-rate share removal counts: 1 / 3 / 5.

The following real-E1 allocation settings are intentionally **UNFROZEN** and
are not invented by this task:

- candidate-cohort opening cash / position fraction;
- capital-constrained opening cash / position fraction;
- capital-constrained max positions / selection rule.

The deterministic synthetic fixture supplies fixture-only values for those
mechanics. They are not promoted to real-E1 method settings.

## Row-level qualification table

The adapter follows Sol 4 mapping comment `5985511174` in issue #6.
Only synthetic fixtures were executed; this is not real parquet integration acceptance.

Base CSV / Parquet columns (or the lossless Sol 4 mapping below):

| column | meaning |
| --- | --- |
| `date` | logical research row date |
| `stock_id` | ticker |
| `eligibility_status` | `ELIGIBLE`, `ELIGIBLE_WITH_PIT_EVIDENCE_INCOMPLETE`, `EXCLUDED`, `BLOCKED`, `UNKNOWN`, or `UNAVAILABLE` |
| `reason_code` | explicit reason for every row |
| `reason_detail` | non-authoritative human-readable detail |

Required sidecar manifest fields:

- `schema_version`
- `scope` (`SYNTHETIC_FIXTURE` or `SOURCE_EVIDENCE`)
- `source_revision`
- `epoch`
- `period_start` / `period_end`
- `row_count`
- `table_sha256`

Validation rules:

- checksum and declared row count must match;
- logical keys must be unique and valid;
- every row must retain an explicit status and reason;
- table rows outside the declared period are rejected;
- the full input table is retained in the report as the population
  denominator;
- only `ELIGIBLE` or explicitly PIT-incomplete candidates enter the synthetic simulation;
- the PIT-incomplete label requires A=true, B=C=false and INDETERMINATE;
- plain ELIGIBLE cannot erase an A/B/C flag;
- a signal candidate with no qualification row is retained in the candidate
  funnel as `UNKNOWN / MISSING_ELIGIBILITY_ROW`, not converted to zero and
  not silently deleted.

Therefore a known-unresolved economic-content row remains visible and blocked.

## Source integrity input

Synthetic execution also requires a source manifest with:

- `scope=SYNTHETIC_FIXTURE`;
- source revision;
- period;
- the RAW/tradability files actually used and their SHA256 values.

The source revision must agree with both:

1. the FeaturePanelIntegrator hydration evidence; and
2. the eligibility-table manifest.

Feature formulas, artifact identity/version, cutoff checks, hydrated panel
fingerprints and execution-session binding remain governed by the accepted
PreparedResearchRun evidence chain from PR #5.

These hashes are process-integrity/provenance checks, not a security system
against a malicious actor who can rewrite code and evidence together.

## Candidate cohort versus capital-constrained result

The report deliberately has two result blocks.

### Candidate cohort

Each eligible ticker is simulated independently using the canonical simulator.
All signals for that ticker remain together, so the one-open-trade-per-ticker
and same-ticker lifecycle rules are preserved while cross-stock capital
competition is removed.

The synthetic fixture supplies its own normalized test policy. Real E1 cannot
reuse that policy without separate Astra approval.

### Capital-constrained

The same eligible candidate set is also run once through one canonical
portfolio using a separate fixture-only capacity policy.

Capacity rejections and entry skips belong only to this block. They are never
confused with the candidate qualification denominator.

## Report schema

`report.json` schema version 2 contains:

- identity: report type, strategy version, mode, source revision;
- execution period and frozen cost assumptions;
- `unfrozen_for_real_e1`;
- `population`:
  - original row denominator;
  - unique tickers;
  - status and reason counts;
- `candidate_funnel`:
  - signal-candidate count;
  - eligible candidate count;
  - candidate status/reason counts;
- `candidate_cohort` and `capital_constrained`, each reported separately;
- cost-adjusted closed-trade metrics:
  - `n_closed`
  - `n_open` (normal period-end only)
  - `n_data_censored`, reason counts, entered-trade denominator and censored share
  - `win_rate`
  - `average_win`
  - `average_loss_abs`
  - `payoff_ratio`
  - `average_net_return_per_trade`
  - average holding days / sessions
  - top-1/3/5 positive-return concentration share
  - resolved-closed-trade average after removing top-1/3/5 returns;
- `mfe_mae`: diagnostic-only status/counts;
- explicit notes that this is synthetic and FORMAL_RESEARCH is blocked.

Non-computable numeric summary values are serialized as JSON `null`, never
silently zero-filled.

Companion tables:

- `candidate_trades.csv`
- `capital_constrained_trades.csv`
- `open_positions.csv`
- `data_censored_positions.csv`
- `eligibility_audit.csv`
- `candidate_funnel.csv`
- `mfe_mae_diagnostics.csv`

The committed deterministic example is:

- `out/baseline_60d_exploration_synthetic_report.json`

It is checked against a fresh end-to-end fixture run by the package test.

## Executable synthetic command

From the repository root:

```bash
python scripts/baseline_60d_exploration_runner.py \
  --repo-root . \
  --mode SYNTHETIC_FIXTURE \
  --build-fixture \
  --fixture-root /tmp/astraquant_baseline60_fixture \
  --output-dir /tmp/astraquant_baseline60_output
```

This command creates only deterministic synthetic data under the requested
fixture directory and then executes the full synthetic path.

Passing `--mode FORMAL_RESEARCH` hits the existing unconditional formal gate
before fixture/source reads. There is no fallback from formal mode to
`SYNTHETIC_FIXTURE`.

## Synthetic E2E coverage

The package test uses the actual:

`FeaturePanelIntegrator -> PreparedResearchRun evidence ->
ResearchConfigEngine -> CanonicalStrategySimulator -> RAW execution ->
PortfolioEngine -> FIFO trade report`

It validates:

- three usable synthetic candidates enter the candidate cohort;
- one signal candidate with `ECONOMIC_CONTENT_UNRESOLVED` remains in the
  denominator/funnel and never becomes a fill;
- one candidate is a positive closed trade, one is a negative closed trade,
  and one remains open at period end;
- the capital-constrained run has a separate capacity rejection;
- fee/tax/slippage match one-pass canonical fill economics;
- population status/reason totals reconcile to the original row count;
- source and qualification-table checksum tampering fail closed;
- non-fixture evidence scope cannot be used by the synthetic runner;
- MFE/MAE remain a diagnostic output only.

## Revision 2: lossless eligibility mapping

| Sol 4 source | Runner interpretation |
| --- | --- |
| `limited_exploration_label=ELIGIBLE_WITH_PIT_EVIDENCE_INCOMPLETE` | Preserve exact label as `eligibility_status`; A stays true and evidence stays INDETERMINATE |
| `limited_exploration_label=NOT_ELIGIBLE` | Preserve original label; disposition C → UNAVAILABLE, otherwise B → BLOCKED, otherwise UNKNOWN |
| `baseline_issue_a_any/b_any/c_any` | Independent flags; never infer clean from absence of a known problem |
| `baseline_evidence_state`, `raw_version_evidence_reason` | Retained unchanged |
| Per-feature `ma120/n60/atr14/low20` evidence/reasons/event IDs | Retain every original column; summary reason_code does not replace multi-reason evidence |

The mapping requires manifest v2: the existing fields plus
`original_row_denominator`, `contract_revision`, `evidence_revision`, and
`private_delivery_revision`. `source_revision` remains mandatory.
`row_count` checks the provided table; `original_row_denominator` is separately
reported and never replaced with the usable subset size. Status/reason counts
refer to provided rows (`provided_row_count`), not an assertion of complete
original-population or holding-path coverage. Synthetic revisions are visibly
synthetic. SOURCE_EVIDENCE is still rejected by the execution runner.

## Revision 2: daily censoring and portfolio stop

The checksum-bound synthetic eligibility table additionally supplies
`ca_path_status=NO_CA` for each reliable session. Missing/unknown CA evidence,
cash/split events or unresolved multiple successor legs stop the path; no CA
accounting engine or normalizer is rewritten. NO_CA is fixture evidence, not
proof about real market history. A real CA bridge is not integrated here.

The simulator's optional baseline-only data guard runs before each session's
settlements/CA/exits/sizing/NAV, and again after new entry fills but before close
processing and valuation. It examines only current holdings and the current
session, never future rows to remove past entries. At the first missing daily
row, B/C, non-observed/invalid RAW session, or unsupported CA path it permanently
stops that simulation. Daily evidence is conservatively session-granular;
there is no claim of intraday known-at resolution.

All entry fills remain in the canonical ledger. There is no synthetic exit,
forced liquidation, zero return, retrospective deletion, or restart on a later
recovery. Open lots at the stop move to `data_censored_positions.csv`, retaining
entry identity/cost/quantity, `DATA_CENSORED`, `UNRESOLVED`, first `censored_at`,
reason, phase, and `last_reliable_date` / boundary. They are excluded from the
normal period-end open-position table. Closed trades before the stop remain.

One unreliable holding stops the entire capital portfolio before subsequent
cash/NAV-dependent execution. Other live lots become PORTFOLIO_STATE_UNRESOLVED.
`performance_status=BLOCKED_DATA_CENSORED`, `blocked_at`, last complete session,
and `full_period_performance_available=false` disclose this; prefix closed-trade
statistics cannot be represented as full-period realizable performance. The
independent ticker cohort stops only the affected ticker's simulation, including
its later entries. Censored counts/shares use closed + normal open + censored
entries as their denominator. No closed-only mean is overall strategy expectancy.

Leaving all_liquid does not remove a holding. An explicit complete daily holding
evidence row can support continuation; a missing row cannot. The original
all_liquid table alone is not complete holding-path coverage.

## Revision 2: holding-path diagnostics and return-rate shares

MFE/MAE are **trade holding-period path diagnostics**, not fixed-window candidate
MFE. For a next-open exit, prior held sessions supply high/low; the exit session
supplies only RAW open. Later exit-day high/low cannot contaminate the diagnostic.
Every expected common session and its explicit NO_CA qualification must exist.
CA/terminal/multi-leg/invalid/missing paths are UNAVAILABLE with a reason and
null MFE/MAE. There is no RAW cross-CA division.

`top{1,3,5}_positive_return_share` is the sum of the largest positive **return
rates** divided by the sum of all positive return rates. It is not monetary
profit concentration, nor a share of total currency profit. The frozen report
setting is now `positive_return_share_remove_top`; return calculations and
strategy parameters are unchanged. `expectancy_ex_topN` is renamed to
`average_net_return_ex_topN`, a resolved-closed-subset descriptive average.

## Verification and remaining limits

Tests cover next-open extreme prices; cash/split/multi-leg diagnostic exclusion;
missing sessions and rows; first post-entry failure; entry-day censor followed
by recovery; retained entry fills; normal open versus censored separation;
capital cash/NAV stop before later exits and entries; lossless PIT-incomplete
mapping; one-pass costs; formal refusal; and the existing legacy package tests.

Real E1/E2/E3 were not run. No actual Sol 4 private parquet was used for an effect
run or claimed integrated. Full daily holding coverage, a reliable CA path bridge,
real execution/capital settings, and acceptance of known limitations remain for
separate review. FORMAL_RESEARCH remains unconditionally blocked. Only Owner may
authorize changing that gate or starting real effects; this PR does neither.
