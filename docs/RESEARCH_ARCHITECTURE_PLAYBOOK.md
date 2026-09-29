# AstraQuant Research Architecture Playbook

Status: **ARCHITECTURE GUIDE**

This document explains how AstraQuant should organize research ideas so that new strategies become configuration, not new strategy-specific scripts.

The design goal is simple:

> **Idea = Universe × Signal × Exit × Parameters**

Execution, settlement, RAW valuation, corporate actions, FIFO reconstruction, and PIT accounting are shared infrastructure and must not be rewritten for each idea.

---

## 1. The three-layer model

### Layer 1 — Universe

Universe answers:

> **Which stocks are allowed to count today?**

Examples:

- ALL liquid ordinary shares
- STABLE stocks
- a user-authored theme such as 軍工航太
- an official industry group
- an automatic correlation cluster
- stocks passing a fundamental floor
- stocks with an earnings streak

Universe logic produces a **mask**, not a shortened dataset.

The full historical series stays intact so 20/50/200/250-session rolling calculations still mean real trading sessions. A universe condition only decides whether a signal counts on that day.

Example:

```text
full price history
       ↓
compute D50 / D200 / RSI / earnings features
       ↓
universe mask says counts=True/False
       ↓
signal decides whether the stock becomes a candidate
```

Never delete historical rows before rolling calculations.

---

## 2. Universe pools are independently swappable

The candidate base remains:

- listed/OTC four-digit ordinary shares
- close >= NT$10
- observed trade
- valid OHLC
- frozen P2-060 PIT exclusions

Additional pools are composable.

Example:

```text
BASE
  AND top-25%-turnover
  AND Theme = 軍工航太
  AND Fundamental Floor
```

or:

```text
BASE
  AND STABLE
```

or:

```text
BASE
  AND (Theme = AI伺服器 OR Theme = CoWoS)
```

A stock may belong to several themes at once.

---

## 3. Theme research is first-class

Themes are not hard-coded into Python.

Each theme lives as a plain YAML file:

```yaml
schema_version: "1"
theme: 軍工航太
members:
  - ticker: "2634"
    from: 2022-02-24
    to: null
    source: "<evidence>"
  - ticker: "8033"
    from: 2023-06-01
    to: 2025-03-31
    source: "<evidence>"
notes: "free text"
```

Important rule:

> **Theme membership must be dated.**

An undated theme would silently project today's narrative backward into 2016 and create leakage.

The engine should report theme member count through time so a thin or collapsing theme is visible.

---

## 4. Signal is split into Trigger A and Filter B

Signal is not one monolithic rule.

### Trigger A — which day?

Examples:

- N-session high
- gap-up
- volume spike
- moving-average golden cross
- MACD zero cross
- KD low-zone golden cross
- RSI cross
- Bollinger upper-band break
- pullback and reclaim
- consecutive up days

### Filter B — which stock?

Examples:

- long-term trend structure
- relative strength
- volatility
- turnover
- volume behavior
- institutional flows
- valuation
- ROE
- margins
- leverage
- monthly revenue
- earnings streak
- dividend streak
- group breadth
- market-cap percentile

The trigger and filter are independent.

For example:

```text
Trigger:
    250-session breakout

Filters:
    O'Neil long-term trend structure
    RSI > 50
    monthly revenue YoY > 0

Ranking:
    relative strength
    ROE
```

The same O'Neil filter can later be reused with a volume-spike trigger, MACD trigger, or theme-specific trigger without new strategy code.

---

## 5. Research ideas become reusable components

Do not create a separate engine for:

- O'Neil
- Minervini
- Weinstein
- CANSLIM
- momentum
- quality
- institutional-flow strategies

Instead, decompose each method into reusable components.

Example:

```text
O'Neil concept
    ↓
LONG_TERM_TREND_STRUCTURE
EPS_YOY_GROWTH
REVENUE_ACCELERATION
RELATIVE_STRENGTH
NEW_HIGH
VOLUME_EXPANSION
GROUP_STRENGTH
MARKET_REGIME
```

A later strategy can reuse any subset.

A component should be implemented once, registered once, and then referenced by config forever.

---

## 6. O'Neil example: long-term trend structure

Owner-provided concept:

- W10
- W40 ≈ D200
- close > W10 > W40
- both averages rising
- healthy spread between the two averages

AstraQuant represents this as a reusable Filter B:

```yaml
- type: LONG_TERM_TREND_STRUCTURE
  params:
    fast_sessions: 50
    slow_sessions: 200
    slope_lookback_sessions: 10
    min_fast_slow_spread: 0.00
    max_fast_slow_spread: null
```

Daily equivalents are the default implementation:

- D50 ≈ W10
- D200 ≈ W40

The parameters are not treated as sacred.

They are reference defaults.

---

## 7. Taiwan adaptation: do not blindly copy US parameters

A parameter from a book is a hypothesis, not truth.

Example:

```text
Original:
W10 / W40
```

Possible Taiwan research grid:

```text
fast:
40 / 50 / 60

slow:
160 / 180 / 200 / 220 / 250

slope lookback:
5 / 10 / 20 sessions

minimum fast-slow spread:
0% / 2% / 5% / 8%

maximum fast-slow spread:
10% / 15% / 20% / none
```

AstraQuant should expand this into a parameter surface.

The objective is **not**:

> Find the single best number.

The objective is:

> Find a broad region where nearby parameter choices behave similarly.

A broad plateau is more credible than one isolated peak.

---

## 8. Robust-region research

Suppose a sweep produces:

```text
D40 / D180  good
D50 / D180  good
D50 / D200  good
D60 / D200  good
D60 / D220  good
```

That is potentially useful evidence.

If only:

```text
D47 / D193
```

works and everything around it fails, treat it as likely overfit.

Research should therefore report:

- parameter surface
- neighboring-parameter stability
- yearly stability
- regime stability
- trade count
- expectancy
- payoff
- uncertainty
- pool coverage

Never promote the numerical winner merely because it is highest.

---

## 9. Pool-specific parameters are allowed

A single parameter set does not need to fit every stock.

The same component can be calibrated separately by research pool.

For example:

```text
ALL
  LONG_TERM_TREND_STRUCTURE grid A

Theme = 軍工航太
  LONG_TERM_TREND_STRUCTURE grid B

Theme = AI伺服器
  LONG_TERM_TREND_STRUCTURE grid C

STABLE
  LONG_TERM_TREND_STRUCTURE grid D
```

This is still one evaluator.

Only the config changes.

This allows the engine to test whether a concept is:

- broad-market
- industry-specific
- theme-specific
- regime-specific
- useful only inside a stable/defensive pool

without writing a new strategy.

---

## 10. Scope × parameter grid

The scalable research unit is:

> **scope × trigger × filters × exit × parameter grid**

Example:

```text
Scopes:
    ALL
    軍工航太
    AI伺服器
    重電

Trigger:
    250-session high

O'Neil filter:
    fast = [40, 50, 60]
    slow = [180, 200, 220]
    slope = [5, 10, 20]
    min spread = [0, 0.02, 0.05]

Exit:
    stop = [0.08, 0.10, 0.12]
    time exit = [120, 250]
```

The batch engine expands combinations automatically.

No new script should be required.

---

## 11. The batch funnel

Do not run every combination through full portfolio accounting immediately.

Use a funnel.

### Stage A — cheap composition

Use cached features and masks.

Typical batch:

```text
100–1,000 configs
```

Measure:

- signal count
- trade-level expectancy proxy
- win rate
- payoff
- temporal stability
- parameter-neighbor stability
- theme coverage

### Stage B — canonical simulation

Only survivors enter:

- RAW execution
- settlement
- corporate actions
- capacity
- FIFO
- portfolio path

Typical batch:

```text
6–20 configs
```

### Stage C — frozen validation

Only explicitly frozen candidates continue.

No parameter tuning after locked OOS begins.

---

## 12. Shared feature cache

This architecture only scales if repeated calculations are shared.

Example:

```text
D50
D200
RSI14
ATR20
ROE4Q
revenue YoY
relative strength
```

Each unique feature/parameter combination should be calculated once per source revision.

Cache identity:

```text
source revision
+ feature name
+ feature parameters
+ availability policy
```

If 200 configs use D200, D200 is computed once.

---

## 13. Fundamentals can be both filters and rankings

Example threshold use:

```yaml
- type: ROE
  params:
    min: 0.15
```

Example ranking use:

```yaml
ranking:
  - type: ROE
    params:
      direction: DESC
      weight: 0.5
```

The architecture must support both.

Previous conclusions from older defective accounting runs do not carry forward automatically.

---

## 14. PIT rules are engine rules, not strategy options

Strategies may not override information availability.

Required rules include:

- financial statements use available_date
- Q1 standard deadline: 5/15
- Q2: 8/14
- Q3: 11/14
- Q4: following 3/31
- actual later availability wins
- monthly revenue: usable from the 10th of the following month
- institutional flows: T+1
- margin data: T+1

A component that cannot establish legal availability must fail rather than guess.

---

## 15. Execution/accounting remains separate

Research configuration must never decide:

- RAW execution price
- fill creation
- settlement
- corporate-action conversion
- NAV valuation
- FIFO accounting

Research produces:

```text
candidate
or
exit intent
```

The existing canonical execution/accounting layer handles everything after that.

This separation prevents every strategy from re-implementing accounting differently.

---

## 16. Reporting order

Every canonical strategy run reports trade-level statistics first:

```text
trades
win rate
average win
average loss
payoff
expectancy per trade
```

Then:

- open lots separately
- uncertainty / robustness
- parameter-surface stability
- pool/theme provenance
- path metrics such as CAGR, drawdown, Sharpe

Path performance is secondary to trade-level evidence.

---

## 17. What "flexible" should mean

The architecture is successful when the owner can say:

> Test O'Neil long-term trend structure inside 軍工航太, AI伺服器 and ALL.

Then change:

> Use volume spike instead of breakout.

Then:

> Compare 40/180, 50/200 and 60/220.

Then:

> Use ATR trailing instead of fixed stop.

And all of that requires changing config files only.

No new strategy script.

---

## 18. Research governance

Parameter scanning is allowed for research, but it does not authorize promotion.

Rules:

1. Define the search space before looking at results.
2. Keep all adverse results.
3. Prefer stable regions over best points.
4. Compare across years/regimes.
5. Record the number of combinations tested.
6. Correct interpretation for multiple testing.
7. Freeze the selected region/config before validation.
8. Never retune from locked OOS.
9. Theme-specific evidence stays theme-specific unless separately shown to generalize.
10. A result from one pool must never be silently generalized to another.

---

## 19. Target end state

The final workflow should look like:

```text
Owner collects research idea
        ↓
decompose idea into reusable components
        ↓
add component once if it does not exist
        ↓
write/edit YAML configs
        ↓
choose pool/theme
        ↓
declare parameter grid
        ↓
batch screen
        ↓
inspect robust regions
        ↓
canonical full simulation for survivors
        ↓
freeze
        ↓
validation / OOS governance
```

The engine should become a **research factory**, not a collection of backtest scripts.


## 20. Implemented parameter-sweep syntax

AstraQuant parameter sweeps use component paths rather than strategy-specific code.

Example:

```yaml
schema_version: "1"
name: oneil_taiwan_surface

universes:
  - configs/examples/universes/all_liquid.yaml
  - configs/examples/universes/defense_aero_theme.yaml

signal: configs/examples/signals/high250_oneil_structure.yaml
exit: configs/examples/exits/stop12_time250_executable.yaml

axes:
  - target: filter:LONG_TERM_TREND_STRUCTURE.fast_sessions
    values: [40, 50, 60]
  - target: filter:LONG_TERM_TREND_STRUCTURE.slow_sessions
    values: [180, 200, 220]
  - target: filter:LONG_TERM_TREND_STRUCTURE.slope_lookback_sessions
    values: [5, 10, 20]
  - target: filter:LONG_TERM_TREND_STRUCTURE.min_fast_slow_spread
    values: [0.0, 0.02, 0.05]

execution_assumptions_id: taiwan-zero-cost-signal-isolation-v1
max_combinations: 1000
report_trade_stats_first: true
```

Supported sweep target forms are:

```text
trigger.<param>
filter:<TYPE>.<param>
ranking:<TYPE>.<param>
exit:<TYPE>.<param>
universe:<TYPE>.<param>
```

The same runner can therefore scan an O'Neil trend filter today and later scan RSI thresholds, volume-spike thresholds, universe liquidity cutoffs, or exit parameters without a new sweep script.

Multiple universe files create the scope dimension. This is how the same parameter surface can be evaluated independently in ALL, STABLE, 軍工航太, AI伺服器, or any other dated theme.

The sweep runner expands configurations and prepares research candidates. It does **not** select the winning parameter set. Robust-region analysis and frozen validation remain separate governance steps.
