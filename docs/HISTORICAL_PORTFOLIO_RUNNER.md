# Historical Portfolio Runner

AstraQuant now has a chronological historical replay runner built on the canonical execution and accounting path.

## Session ordering

For each configured historical session the runner performs, in order:

1. settle trade settlements that are due by session start;
2. apply corporate actions effective that session to opening holdings;
3. execute externally supplied trade instructions through CanonicalExecutionService;
4. take an end-of-session RAW NAV snapshot.

## Inputs

The runner consumes explicit instructions:

- historical session calendar;
- declared-signal trade instructions;
- explicit corporate-action instructions.

It does not generate signals, optimize parameters, rank strategies, or compute performance metrics.

## Corporate actions

Cash dividends use opening holdings on the effective session.

Share-multiplier events mutate holdings before same-session trades.

Non-dividend cash components require both:

- a declared economic component name; and
- an explicit entitlement-share basis.

No entitlement basis is inferred from adjusted prices.

## Guardrails

- trade instructions outside the supplied calendar hard-fail;
- corporate actions outside the supplied calendar hard-fail;
- corporate actions must be applied on their effective date;
- fills still require RAW/tradability through the canonical execution service;
- all NAV snapshots use RAW marks.

## Current status

Unit/integration tests cover chronological settlement, share mutation, dividend entitlement, trading, and RAW NAV snapshots. CI passes.

The next gate is a frozen-source full-history probe spanning the 2015–2026 RAW history. That probe remains accounting/integration evidence only; strategy performance stays locked.


## Trading Calendar Policy

Corporate actions whose economic effective date is not a trading session are mapped **forward only** to the first configured trading session after the effective date. The original effective date remains unchanged for audit/provenance. No event is mapped backward, and events beyond the configured calendar horizon hard-fail instead of being guessed.

See `docs/TRADING_CALENDAR_POLICY.md` and `docs/SOURCE_CA_CALENDAR_AUDIT.md`.
