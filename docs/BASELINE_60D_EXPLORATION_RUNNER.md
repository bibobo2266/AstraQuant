# 60 日突破基線 — 探索實測 runner 準備

Status: **SYNTHETIC E2E RUNNABLE / REAL E1 NOT RUN / FORMAL_RESEARCH BLOCKED**

Task: `AQ-EXP-RUNNER-001`

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
- profit-concentration removal counts: 1 / 3 / 5.

The following real-E1 allocation settings are intentionally **UNFROZEN** and
are not invented by this task:

- candidate-cohort opening cash / position fraction;
- capital-constrained opening cash / position fraction;
- capital-constrained max positions / selection rule.

The deterministic synthetic fixture supplies fixture-only values for those
mechanics. They are not promoted to real-E1 method settings.

## Row-level qualification table

The runner accepts the same row-level shape intended for Sol 4 eligibility /
reason evidence.

Required CSV columns:

| column | meaning |
| --- | --- |
| `date` | logical research row date |
| `stock_id` | ticker |
| `eligibility_status` | `ELIGIBLE`, `EXCLUDED`, `BLOCKED`, `UNKNOWN`, or `UNAVAILABLE` |
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
- only candidate rows marked `ELIGIBLE` may enter simulation;
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

`report.json` schema version 1 contains:

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
  - `n_open`
  - `win_rate`
  - `average_win`
  - `average_loss_abs`
  - `payoff_ratio`
  - `average_net_return_per_trade`
  - average holding days / sessions
  - top-1/3/5 positive-return concentration share
  - expectancy after removing top-1/3/5 returns;
- `mfe_mae`: diagnostic-only status/counts;
- explicit notes that this is synthetic and FORMAL_RESEARCH is blocked.

Non-computable numeric summary values are serialized as JSON `null`, never
silently zero-filled.

Companion tables:

- `candidate_trades.csv`
- `capital_constrained_trades.csv`
- `open_positions.csv`
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

## Stop point

This task completes **synthetic execution preparation**, not real exploration.

The only remaining run authorization blocker is the separate real-E1 step:
after Sol 4 publishes the actual row-level coverage, Astra must explicitly
accept the data limitations, freeze the real execution/capital settings and
range, and authorize the formal exploration entry. Until that happens,
`FORMAL_RESEARCH` remains blocked and E2/E3 are untouched.
