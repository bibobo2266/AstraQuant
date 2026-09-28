# Three-Layer Config-Driven Research Engine Contract

Status: **INTERFACE CONTRACT ONLY — evaluators not yet implemented**

Goal: a new research idea is expressed by configuration, not a new strategy script. The three research layers are independently swappable and compile into stable interfaces above the existing execution/accounting stack.

Execution, corporate actions, FIFO reconstruction, settlement, RAW marking, and PIT governance are outside this contract and remain unchanged.

## 1. File layout

```
configs/
  universes/
    <name>.yaml
  signals/
    <name>.yaml
  exits/
    <name>.yaml
  runs/
    <name>.yaml
themes/
  <theme>.yaml
```

Every stored file carries `schema_version: "1"`. Theme files are plain YAML and are intended to be editable without code changes.

## 2. Universe config

Example:

```yaml
schema_version: "1"
name: stable_defense_aero
base:
  ticker_pattern: "^[1-9]\\d{3}$"
  min_close_twd: 10
  require_observed_trade: true
  require_valid_ohlc: true
  p2_060_exclusion_sha256: "379d58f6a8aa06b1e020d56911930f4bc01861d3eeca109613d9e5b1e490d134"

combine: AND
pools:
  - type: ALL
    turnover_top_fraction: 0.25

  - type: STABLE
    index_down_threshold: -0.01
    downside_rs_multiplier: 0.70
    downside_rs_lookback: 250
    rv60_bottom_fraction: 0.40
    max_drawdown_multiplier: 1.20
    max_drawdown_lookback: 250
    large_holder_min_fraction: 0.60
    large_holder_max_change_pp: 5.0
    holder_lookback: 250
    consecutive_dividend_years: 5
    turnover_ratio_bottom_fraction: 0.50

  - type: INDUSTRY_THEME
    combine: AND
    groups:
      - mode: THEME
        themes: [軍工航太]
        combine: OR
        dated_membership_required: true
      - mode: OFFICIAL
        groups: [工業運輸營建, 電子上游]
        leakage_note_required: true
```

The base filter is always applied and cannot be disabled by a pool. Candidate membership remains four-digit ordinary shares; widening the valuation universe for passively received successor securities does not widen this candidate universe.

### Universe interface

```text
UniverseCompiler.compile(config, panel, context) -> UniverseMask
```

`UniverseMask` is a full-keyed `(date, ticker)` table containing at minimum:

- `counts: bool`
- per-pool booleans
- rejection reasons
- config hash / provenance
- leakage warnings when applicable

**Invariant:** the compiler must never delete observations from the research panel. Rolling features are computed on the intact trading-day series first. The mask only determines whether a signal counts on a day.

### Grouping-mode provenance

- **OFFICIAL:** present-value vendor classification backfilled through history; not PIT. Every report using it must say so.
- **THEME:** user-authored and dated. Membership is valid only between explicit `from` and `to`. This avoids silent present-day narrative backfill, but evidence quality remains user/source dependent.
- **CORRELATION:** recomputed from trailing returns using only information available at each recompute date; PIT-safe by construction if the implementation obeys the declared window/recompute schedule.

No grouping mode may silently substitute for another.

## 3. Theme file

Stored theme memberships are always explicitly dated:

```yaml
schema_version: "1"
theme: 軍工航太
members:
  - ticker: "2634"
    from: 2022-02-24
    to: null
    source: "owner research note / cited source"
  - ticker: "8033"
    from: 2023-06-01
    to: 2025-03-31
    source: "owner research note / cited source"
notes: "Free text."
```

An authoring UI may default `from` to the date the owner adds a member, but it must materialize that date into the stored file. A stored member without `from` is invalid. `from` must never precede the evidence cited in `source`.

Reports must show member count by date/recompute period so thin or collapsing themes are visible.

## 4. Signal config

Trigger A answers **which day**. Filters/rankings answer **which stock**. They are independent.

```yaml
schema_version: "1"
name: high250_quality_momentum

trigger:
  type: N_SESSION_HIGH
  params:
    lookback: 250

filter_combine: AND
filters:
  - type: RSI
    params:
      lookback: 14
      min: 50
  - type: MONTHLY_REVENUE_YOY
    params:
      min: 0
  - type: GROUP_BREADTH
    params:
      min_percentile: 0.60

ranking:
  - type: RELATIVE_STRENGTH
    params:
      lookback: 120
      direction: DESC
      weight: 1.0
  - type: ROE
    params:
      trailing_quarters: 4
      direction: DESC
      weight: 0.5
```

### Signal interface

```text
SignalCompiler.compile(config, feature_registry) -> SignalPlan
SignalEvaluator.evaluate(plan, full_panel, universe_mask, context) -> SignalFrame
```

Evaluation order:

1. Compute trigger/filter/ranking features on the full intact panel.
2. Apply PIT availability rules.
3. Compute `triggered`.
4. Compute filter pass/fail and ranking values.
5. Apply `universe_mask.counts` only to decide `counts_as_candidate`.

A `SignalFrame` must preserve at least `signal_date`, `ticker`, `triggered`, `filter_pass`, `counts_as_candidate`, ranking metadata, feature provenance, and `available_date`.

Fundamentals must be registerable both as threshold filters and ranking factors. Prior conclusions about fundamental ranking from the defective earlier engine are withdrawn and must not be used as evidence here.

## 5. Exit config

```yaml
schema_version: "1"
name: stop12_target30_time250
first_trigger_wins: true
rules:
  - type: FIXED_STOP_TARGET
    params:
      stop_pct: 0.12
      target_pct: 0.30
  - type: TIME_EXIT
    params:
      sessions: 250
```

### Exit interface

```text
ExitCompiler.compile(config, feature_registry) -> ExitPlan
ExitEvaluator.evaluate(plan, held_position_state, session_features, context) -> ExitIntent | None
```

The exit layer may request an exit, but it never chooses an execution price and never creates a fill. `ExitIntent` flows into the unchanged canonical RAW execution service. Corporate-action state mutations remain owned by the existing accounting layer.

## 6. Run config

```yaml
schema_version: "1"
run_name: stable_aero_high250_stop12
universe: configs/universes/stable_defense_aero.yaml
signal: configs/signals/high250_quality_momentum.yaml
exit: configs/exits/stop12_target30_time250.yaml
execution_assumptions_id: taiwan-zero-cost-signal-isolation-v1
report_trade_stats_first: true
```

Engine contract:

```text
ResearchEngine.run(run_config)
  -> load/validate 3 configs
  -> build/cache full PIT-safe feature panel
  -> UniverseCompiler -> UniverseMask
  -> SignalCompiler/Evaluator -> SignalFrame
  -> ExitCompiler -> ExitPlan
  -> unchanged canonical simulator/execution/accounting
  -> CA-aware FIFO reconstruction
  -> report
```

Changing one config must not require changing the other two or touching execution/accounting code.

## 7. PIT availability contract

These rules are engine-level invariants, not per-strategy options:

- financial statement features use `available_date`, never period end;
- standard availability deadlines: Q1 05-15, Q2 08-14, Q3 11-14, Q4 following 03-31; financial holdings may be later, so actual later `available_date` wins;
- monthly revenue is available on the 10th of the following month;
- institutional flow and margin data published after close are usable from T+1 only;
- no feature may silently fall back to an earlier coordinate with different semantics.

## 8. Current capability matrix

| Requested capability | Current engine | Work required |
|---|---|---|
| Four-digit ordinary-share candidate base | **YES** | Already hard-gated in breakout builder / eligible-universe audit |
| observed_trade + valid_ohlc | **YES** | Already used |
| close >= NT$10 | **NO** | New universe base-mask rule |
| Frozen P2-060 exclusions | **PARTIAL** | Applied by research scripts; move behind universe compiler |
| ALL / turnover top fraction | **PARTIAL** | Fraction is configurable, but currently entangled with breakout builder |
| STABLE six-factor pool | **NO** | New PIT feature implementations; holder-concentration source availability must be verified |
| OFFICIAL eight groups | **NO canonical interface** | Add group provider; mandatory present-value leakage warning |
| THEME dated files | **NO** | Add theme loader/provider and count-over-time reporting |
| CORRELATION grouping | **NO** | Add rolling PIT cluster provider |
| FUNDAMENTAL_FLOOR | **NO** | Add PIT fundamental features/threshold evaluator |
| EARNINGS_STREAK | **NO** | Add PIT EPS YoY streak feature |
| N-session high | **YES, entangled** | Current breakout lookback is configurable; move behind trigger registry |
| All other requested Trigger A rows | **NO** | Add trigger evaluators behind registry |
| Filter/ranking factor framework | **PARTIAL/non-canonical** | Existing `batch_screen` is not the canonical strategy engine; build reusable feature/filter/rank registry later |
| Fixed stop | **YES** | Current `PortfolioPolicyConfig.stop_fraction` |
| Time exit / max hold | **YES** | Current `max_hold_sessions` |
| Fixed target | **NO** | Add exit rule |
| MA/EMA/Ichimoku/Bollinger/ATR/trailing/Donchian exits | **NO** | Add exit evaluators |
| RAW execution / settlement / CA / FIFO | **YES** | **Do not change** for this architecture task |

The present canonical engine therefore expresses approximately one trigger family plus fixed-stop/time-exit policy. The new schema is intentionally broader than current executable capability; unsupported component types must fail loudly at compile time until a registered evaluator exists.

## 9. Cost model and batch-size implication

The architecture must separate **feature cost** from **combination cost**.

### Shared cost

Data hydration, PIT joins, and rolling feature calculation should be cached by:

```text
(source revision, feature name, feature params, availability policy)
```

If 100 configurations reuse the same RSI14, RV60, ROE4Q and revenue-YoY features, those features should be calculated once, not 100 times.

### Per-combination cost after feature caching

These are engineering estimates, not completed benchmarks:

| Stage | Estimated marginal cost / combination | Batch implication |
|---|---:|---|
| YAML parse + schema validation | <0.1 s | Thousands |
| Boolean universe composition from cached masks | ~0.1–1 s | Hundreds/thousands |
| Trigger/filter/ranking composition from cached feature arrays | ~0.1–2 s | Hundreds |
| New rolling feature not yet cached | ~1–30 s **per unique feature**, not per combo | Precompute once |
| Full portfolio simulation + RAW execution + accounting + FIFO | order of 1–3 min / combo on current CI runner | Tens, not hundreds |

Recent P2-062 source-backed execution spent about 7m40s inside the attribution step before failing during a six-rule run. Because it failed before completing all six, this is only a lower-bound indication; it confirms that blindly sending 100 ideas through the full portfolio/accounting path is the wrong architecture.

Initial operating limits should therefore be:

- **screen/compose:** 100–1,000 configs per batch once feature caching exists;
- **full canonical simulation:** 6–20 configs per batch;
- promote only explicitly selected survivors to expensive CA-aware FIFO/path analysis.

Before these limits become production defaults, benchmark the completed three-layer engine on one frozen 10-year panel and record wall-clock, peak memory, feature-cache hit rate, and simulation cost per combination.

## 10. Report contract

Every completed canonical run reports in this order:

1. trade-level statistics: closed-trade n, win rate, average win, average loss, payoff ratio, expectancy per trade;
2. open/unclosed lots separately;
3. uncertainty / falsification evidence;
4. path metrics (CAGR, max drawdown, Sharpe) secondarily;
5. exact universe/grouping provenance and leakage warnings;
6. config hashes and source revision.

No config can tune or promote itself. Locked OOS remains governed separately.
