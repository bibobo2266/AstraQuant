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


## Source-backed daily screening protocol v1

Before observing results, the first real-source daily screen is frozen as follows:

- universe: ALL top-25%-turnover pool on the frozen P2-060 common-support exclusions;
- signal window: 2016-01-04 through 2026-06-30;
- outcome horizon: 60 source sessions;
- evidence level: candidate-level adjusted research outcome only;
- no RAW execution, stop fill, capacity, CA path, FIFO, or portfolio sequencing;
- no automatic winner selection or OOS promotion.

Declared parameter surfaces:

### Bollinger

```text
window: 10 / 14 / 20
stddev: 1.5 / 2.0 / 2.5
compression bandwidth percentile: 10% / 20% / 30%
volume multiplier: 1.2 / 1.5 / 2.0
RSI-relative filter: RSI13 > RSI26 fixed for this first screen
```

81 combinations.

### VCP

```text
contraction windows: [60, 30, 15] fixed for v1
pivot lookback: 10 / 20 / 40
max dry-up volume ratio: 0.50 / 0.70 / 0.90
max chase: 3% / 5%
```

18 combinations.

### Anchor UP

```text
left confirmation: 3 / 5 / 10
right confirmation: 1 / 2 / 3
required closes above anchor: 1 / 2
max wait: 20 sessions fixed
```

18 combinations, evaluated with long-direction 60-session return.

### Anchor DOWN

Same 18-combination surface, evaluated separately with short-direction 60-session return. Long and short outcomes are never pooled.

These first source-backed surfaces are exploratory falsification/screening evidence only. Parameter neighborhoods may be analyzed after the run, but the maximum cell is not a promotion rule.


---

## OBS-005 — Multi-timeframe RSI filtering and pullback reclaim

### Original observation

The supplied chart notes describe a sequential intraday SOP rather than a single RSI threshold:

1. Before the open, reduce a broad watchlist by removing daily-chart names with RSI below 50.
2. Use the 60-minute chart to reject names whose short/medium-term direction is already weakening.
3. During the first 15 minutes, classify strength with 15-minute RSI plus volume:
   - RSI rapidly above 60 with clear volume expansion = stronger candidate;
   - RSI around 50-60 without notable volume = weaker candidate;
   - RSI unable to hold 50 = reject.
4. Do not chase the first opening impulse.
5. After the first push, judge the pullback:
   - RSI holding around 55-58 indicates strength;
   - a pullback toward 50 that quickly recovers may remain valid;
   - a break materially below 50 invalidates the setup.
6. A later reclaim of RSI 60, preferably with confirming volume, is a cleaner second signal.
7. After entry, RSI below 50 is an exit condition; a later recovery does not automatically justify re-entry.

The core idea is hierarchical filtering:

```text
daily direction
→ 60-minute rhythm
→ 15-minute strength/pullback
→ volume confirmation
→ enter only if all required gates pass
```

### Reusable mechanical component

Component:

`RSI_PULLBACK_RECLAIM`

The evaluator is timeframe-agnostic. It encodes the pullback/reclaim portion:

- RSI remains above a configurable floor;
- RSI visits a configurable pullback zone;
- RSI then crosses above a configurable reclaim level;
- optional current-bar volume expansion confirms the reclaim.

Example:

```yaml
trigger:
  type: RSI_PULLBACK_RECLAIM
  params:
    lookback: 14
    hold_floor: 50
    pullback_ceiling: 58
    reclaim_level: 60
    pullback_window: 6
    volume_lookback: 20
    volume_multiplier: 1.5
```

The daily pre-filter can already be represented using the existing RSI filter:

```yaml
filters:
  - type: RSI
    params:
      lookback: 14
      min: 50
```

### Multi-timeframe orchestration contract

The full SOP requires separate PIT-safe panels:

- daily panel;
- completed 60-minute bars;
- completed 15-minute bars.

A higher-timeframe observation may be consumed only after its bar has completed. A 15-minute decision at 09:15 may use the completed 09:00-09:15 bar, but may not use any later information from that session.

The engine must join timeframe states by an explicit `available_at` timestamp, never by calendar date alone.

### Research ranges

Potential first sweep ranges, to be frozen before a source-backed intraday run:

- daily RSI floor: 45 / 50 / 55;
- pullback floor: 45 / 50 / 52;
- pullback ceiling: 55 / 58 / 60;
- reclaim level: 58 / 60 / 62 / 65;
- pullback window: 3 / 6 / 9 completed bars;
- volume multiplier: 1.0 / 1.2 / 1.5 / 2.0.

These are research ranges, not claimed optimal Taiwan parameters.

### Current status

- `RSI_PULLBACK_RECLAIM` implemented as a reusable component.
- Daily RSI gating is already available.
- Full daily → 60m → 15m source-backed test: **BLOCKED** pending a canonical intraday source and explicit completed-bar timestamps.
- No daily-data approximation will be substituted for the missing intraday layers.

---

## OBS-006 — KD saturation as trend state

### Original observation

The supplied note argues against the common rule "KD above 80 means sell / below 20 means buy."

The behavioral hypothesis is:

- sustained KD above 80 can represent strong bullish momentum;
- sustained KD below 20 can represent persistent bearish momentum;
- the important event is not entering an extreme zone, but whether the saturation persists and when it actually releases;
- price structure and volume should be used with the KD state rather than treating KD as a standalone reversal instruction.

### Machine-testable representation

Components:

- `KD_SATURATION_STATE` — filter/state.
- `KD_SATURATION_RELEASE` — trigger when a sustained state actually exits and, optionally, K/D cross confirms the change.

Example high-saturation state:

```yaml
- type: KD_SATURATION_STATE
  params:
    lookback: 9
    k_smooth: 3
    d_smooth: 3
    zone: HIGH
    high_level: 80
    min_sessions: 3
```

Example release:

```yaml
trigger:
  type: KD_SATURATION_RELEASE
  params:
    lookback: 9
    k_smooth: 3
    d_smooth: 3
    zone: HIGH
    high_level: 80
    min_sessions: 3
    require_kd_cross: true
```

LOW is symmetric around a configurable low threshold.

### Research ranges

- high threshold: 75 / 80 / 85;
- low threshold: 15 / 20 / 25;
- minimum saturation duration: 2 / 3 / 5 / 8 bars;
- KD parameters: (9,3,3) and (14,3,3);
- release confirmation: leave zone only vs leave zone + K/D cross.

The primary question is whether duration of saturation contains information beyond a one-bar KD threshold.

### Current status

- high/low saturation state implemented.
- saturation-release trigger implemented.
- Unit tests treat high saturation as a persistent state, not an automatic sell.
- Source-backed daily sweep has not yet been frozen; it must remain separate from the already-running Bollinger/VCP/Anchor protocol.
