# Legacy Signal Migration Audit

Status: **READY_FOR_CANONICAL_SIGNAL_MIGRATION_WITH_PIT_UNIVERSE CHANGE**

Source inspected read-only: `bibobo2266/minervini_picks/scripts/portfolio_backtest.py`.

This audit separates the legacy research signal from legacy execution/accounting behavior. The source repository remains immutable.

## Legacy signal formation

The default/simple legacy signal is:

1. use adjusted daily close;
2. define the daily universe as the top 25% by `Trading_money`;
3. compute the prior rolling high from the previous `breakout_days` sessions;
4. signal when:
   - today's adjusted close is above the prior rolling high;
   - the previous session was not already above its own prior rolling high;
   - the stock is in the daily turnover universe;
5. default `breakout_days = 250`;
6. execute the signal on the following session open.

The optional `minervini` signal adds the legacy eight-condition trend template. It is not part of the first canonical migration task.

## Feature semantics

Canonical breakout research feature:

- price coordinate: `ADJUSTED_RESEARCH`
- `price_semantics = SCALE_SENSITIVE`
- `ca_window_requirement = CONSISTENT_ADJUSTMENT_WITHIN_LOOKBACK`
- availability: after signal-session close
- intended execution: next-session RAW open

The breakout calculation may never provide an execution price.

## Legacy universe issue

The legacy script calls `minervini_core.load_universe()` and filters by the security's current market type.

The source script itself warns that this market type is a current value and can back-label historical transfer/listing states.

That is not a point-in-time-safe historical universe rule.

### Canonical migration decision

AstraQuant will **not** reproduce that current-snapshot universe filter.

The first canonical signal builder will instead use only stock-days that satisfy all of:

- numeric four-digit stock ID;
- adjusted research row exists;
- adjusted research OHLC is valid;
- matching tradability row exists;
- `observed_trade=True`;
- `valid_ohlc=True`.

The daily top-25%-turnover rule is then computed inside that observable historical stock-day set.

This intentionally changes the historical universe relative to the legacy script in order to remove a known non-PIT dependency.

## Legacy execution/accounting behavior that is not migrated

The following legacy behaviors are rejected as execution/accounting inputs:

- adjusted open for entry;
- adjusted low/open/stop for stop handling;
- adjusted close for exits and marks;
- pseudo-RAW reconstructed from adjusted dividend factors for lot sizing;
- adjusted-price total-return accounting in place of explicit corporate actions;
- performance metrics generated before RAW/cash/CA/NAV reconciliation.

AstraQuant already has canonical replacements for these paths.

## Portfolio-policy logic to migrate separately

These are not part of signal formation and require separate governed migration:

- 1000-share board-lot sizing;
- `REENTRY_GAP = 20`;
- `MAX_HOLD = 250`;
- fixed stop;
- max-position capacity;
- random tie-breaking when signals exceed available slots;
- optional ranking by breakout age or external score;
- optional dead-money, ATR, volatility-sizing, regime, and alternate-exit experiments.

No optional policy is promoted merely because it exists in the legacy script.

## Performance lock

No CAGR, MDD, MAR, Sharpe, annual-return, or strategy comparison may be interpreted from the legacy simulator.

The next task is to implement and source-validate the canonical simple breakout signal builder, then feed resulting signal candidates into the canonical historical runner without evaluating performance.
