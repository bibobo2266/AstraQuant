# Canonical Strategy-Intent Simulator

AstraQuant now has a causal strategy-intent simulator that connects canonical research candidates to RAW execution/accounting without computing strategy performance.

## Session ordering

For each session:

1. settle due cash movements;
2. apply effective corporate actions to opening holdings;
3. at the open, process candidates generated on the prior signal session;
4. after open-entry decisions, evaluate RAW stops for positions already held before the session;
5. at the close, process max-hold exits;
6. take a RAW close NAV snapshot.

This ordering prevents an intraday stop from freeing capacity or cash retroactively for the same session's opening entries.

## Entry path

signal candidate from T close

→ T+1 RAW sizing/open decision

→ board-lot/capacity/re-entry policy

→ CanonicalExecutionService

→ RAW Fill

→ settlement

→ policy state registered from actual RAW fill price.

## Exit path

Stops:

RAW low observation → gap/intraday RAW stop fill → settlement.

Max hold:

session-count rule → RAW close exit → settlement.

## Corporate actions

Corporate-action economic accounting is applied before same-session trading. Managed policy stop state is transformed onto the new RAW economic coordinate using the explicit cash/share components.

## Performance lock

The simulator records accounting/session audit counts only. It does not compute CAGR, MDD, MAR, Sharpe, hit rate, or strategy rankings.

The next gate is a frozen-source integration smoke using real canonical breakout candidates. Missing/invalid RAW marks or other accounting blockers must fail visibly rather than falling back to adjusted prices.


## Trading Calendar Policy

Corporate actions whose economic effective date is not a trading session are mapped **forward only** to the first configured trading session after the effective date. The original effective date remains unchanged for audit/provenance. No event is mapped backward, and events beyond the configured calendar horizon hard-fail instead of being guessed.

See `docs/TRADING_CALENDAR_POLICY.md` and `docs/SOURCE_CA_CALENDAR_AUDIT.md`.
