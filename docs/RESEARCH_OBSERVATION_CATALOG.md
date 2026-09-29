# Research Observation Catalog

Status: **ACTIVE RESEARCH INPUT CATALOG**

This document records owner-supplied observations before they are promoted into any strategy conclusion. Each observation is separated into: original idea, machine-testable definition, configurable parameters, PIT/data requirements, and current implementation status.

No entry in this catalog is automatically promoted, tuned into locked OOS, or treated as a trading recommendation.

---

## OBS-001 — Taiwan overnight futures and U.S. market context

### Original observation

1. Compare the 05:00 Taiwan index-futures night-session close with the previous Taiwan Weighted Index close:
   - positive basis may favor long context;
   - negative basis may favor short context.
2. U.S. overnight influence on Taiwan equities is hypothesized to be strongest from:
   - TSM ADR;
   - Philadelphia Semiconductor Index (SOX);
   - Nasdaq.

### Machine-testable representation

Component:

`OVERNIGHT_MARKET_CONTEXT`

Required research columns:

- `taifex_night_close_0500`
- `twse_prev_close`
- `tsm_adr_return`
- `sox_return`
- `nasdaq_return`

Long context example:

```yaml
- type: OVERNIGHT_MARKET_CONTEXT
  params:
    direction: LONG
    min_basis: 0.0
    min_positive_sources: 2
```

Short context is symmetric.

### Hard PIT rules

The context for Taiwan session T is only legal if every input was known before the Taiwan execution point on T.

The eventual source adapter must explicitly handle:

- Taiwan/U.S. daylight-saving changes;
- Taiwan and U.S. holiday mismatches;
- TSM ADR session date mapping;
- SOX/Nasdaq close timestamps;
- TAIFEX night-session contract roll;
- futures-vs-cash scale/contract semantics;
- no use of a U.S. close that occurred after the Taiwan decision timestamp.

### Current status

- Component contract implemented.
- Missing required columns hard-fail.
- Real source-backed historical test: **NOT RUN** because a canonical overseas/night-session source with frozen timestamp semantics has not yet been established.
- No synthetic fallback or present-value substitution is allowed.

---

## OBS-002 — Bollinger compression breakout

### Original observation

- Bollinger channel: MA14, 2 standard deviations.
- Look for compression followed by upward price expansion with volume.
- 60-minute entry version:
  - Bollinger middle line rising;
  - price breaks above upper band;
  - volume expands;
  - RSI13 > RSI26.

### Daily machine-testable representation

Components:

- `BOLLINGER_COMPRESSION` — filter.
- `BOLLINGER_COMPRESSION_BREAKOUT` — trigger.
- `RSI_RELATIVE` — filter, default RSI13 > RSI26.

Compression is defined mechanically using Bollinger bandwidth:

```text
bandwidth = (upper - lower) / middle
```

A bar is compressed when its bandwidth is below a configurable trailing percentile.

Default research form:

```yaml
trigger:
  type: BOLLINGER_COMPRESSION_BREAKOUT
  params:
    window: 14
    stddev: 2.0
    percentile_lookback: 120
    max_bandwidth_percentile: 0.20
    recent_compression_sessions: 5
    volume_lookback: 20
    volume_multiplier: 1.5
    require_mid_slope_up: true
    mid_slope_lookback: 5

filters:
  - type: RSI_RELATIVE
    params:
      fast_lookback: 13
      slow_lookback: 26
```

### Parameter-sweep candidates

- Bollinger window: 10 / 14 / 20
- stddev: 1.5 / 2.0 / 2.5
- compression percentile: 10% / 20% / 30%
- compression lookback: 60 / 120 / 250
- recent compression window: 3 / 5 / 10
- volume multiplier: 1.2 / 1.5 / 2.0 / 3.0
- middle-line slope lookback: 3 / 5 / 10
- RSI fast/slow pairs around 13/26

The objective is a robust parameter region, not a single maximum cell.

### 60-minute version

The same logical components can operate on a 60-minute panel, but a canonical 60-minute source with timestamp/execution semantics must be supplied first.

A completed 60-minute bar may only be used after that bar closes. No intrabar execution may use information from the completed bar.

### Current status

- Daily components implemented and unit tested.
- 60-minute source-backed test: **NOT RUN** pending canonical intraday source contract.

---

## OBS-003 — VCP entry

### Original observation

- Buy near a solid base before breakout.
- Use volume contraction to identify tightening.
- Add after breakout.
- Do not chase above pivot × 1.05.

### Machine-testable representation

Component:

`VCP_BREAKOUT`

The first mechanical version intentionally uses observable quantities:

1. rolling price-range contractions over several descending windows;
2. prior-volume dry-up;
3. pivot defined from a prior-only rolling high;
4. breakout above pivot;
5. close no higher than `pivot × (1 + max_chase_pct)`.

Example:

```yaml
trigger:
  type: VCP_BREAKOUT
  params:
    contraction_windows: [60, 30, 15]
    pivot_lookback: 20
    volume_base_lookback: 60
    volume_dryup_lookback: 10
    max_dryup_volume_ratio: 0.70
    max_chase_pct: 0.05
```

### Important limitation

This is a machine-testable approximation of the visual VCP concept, not a claim that all discretionary VCP chart-reading has been captured.

Later refinements may add:

- number of contractions;
- contraction depth ratios;
- volatility/ATR contraction;
- base duration;
- prior advance requirement;
- distance from 52-week high;
- breakout-day volume confirmation.

Each refinement must remain parameterized and PIT-safe.

### Current status

- First mechanical trigger implemented.
- Regression test verifies contraction + dry-up + pivot breakout and the 5% chase cap.

---

## OBS-004 — Anchor reversal

### Original observation

Anchor-up:

- find the lowest bar;
- anchor-up = high of the bar immediately before that low;
- reversal requires two closes above anchor-up.

Anchor-down:

- find the highest bar;
- anchor-down = low of the bar immediately before that high;
- reversal requires two closes below anchor-down.

### Look-ahead problem

A historical lowest/highest bar cannot be known at the time if it is defined by future data.

Therefore the literal hindsight form is **not legal** for PIT research.

### PIT-safe mechanical representation

Component:

`ANCHOR_REVERSAL`

A local extreme is only recognized after a configurable right-side confirmation window.

Example:

```yaml
trigger:
  type: ANCHOR_REVERSAL
  params:
    direction: UP
    left_confirm_sessions: 5
    right_confirm_sessions: 2
    required_closes: 2
    max_wait_sessions: 20
```

For UP:

1. candidate local low is identified;
2. wait for the declared right-side confirmation bars;
3. anchor = high of bar immediately before the local low;
4. require the declared number of closes above that anchor;
5. signal may occur only on/after confirmation.

DOWN is symmetric.

Signals are never backfilled to the extreme date.

### Parameter-sweep candidates

- left confirmation: 3 / 5 / 10
- right confirmation: 1 / 2 / 3 / 5
- required closes: 1 / 2 / 3
- max wait: 10 / 20 / 40

### Current status

- PIT-safe UP/DOWN component implemented.
- Unit test verifies that the UP signal cannot appear before local-low confirmation and two qualifying closes.

---

## Cross-pool testing

Every implemented observation is intended to remain independent of the universe layer.

The same trigger/filter can be tested under:

- ALL;
- STABLE;
- official groups;
- dated themes such as 軍工航太 / AI伺服器 / 重電;
- future PIT-safe correlation clusters.

Example research matrix:

```text
scope
× trigger
× filter/context
× exit
× parameter range
```

Theme-specific evidence remains theme-specific unless separately shown to generalize.

---

## Governance

For every observation:

1. preserve the owner-supplied original wording;
2. document the mechanical translation separately;
3. declare the parameter range before examining results;
4. never silently replace unavailable data;
5. never use a future-confirmed event before its confirmation timestamp;
6. record adverse and null results;
7. search for robust regions, not a single best cell;
8. do not promote or unlock locked OOS from an exploratory sweep.
