# Trading Calendar Policy

AstraQuant uses an explicit trading-session calendar for causal simulation and accounting.

## Session-based rules

- T+1 entry means the next configured trading session, not the next calendar day.
- Settlement lags are expressed in trading sessions inside the configured simulation calendar.
- Weekend and exchange-holiday dates are never treated as executable sessions.

## Corporate-action effective dates

Corporate-action `effective_at` remains the economic source date.

If `effective_at` is itself a trading session, the event is applied before that session's trading.

If `effective_at` is not a trading session, the event is applied before the first configured trading session after the effective date.

A corporate action is never mapped backward to an earlier session.

If there is no later session inside the configured calendar, the runner hard-fails or the caller must extend the calendar. AstraQuant does not guess.

## Distinct dates remain distinct

The following are not interchangeable:

- known/announcement date
- economic effective/ex date
- record date
- payment date
- first tradable session after a non-session effective date

The calendar mapping changes only when the simulator can apply an already-effective economic event to a trading-session state. It does not rewrite the source event date.

## Frozen-source audit

The source calendar audit found 40,020 corporate-action rows inside the RAW 2015-01-05 through 2026-09-24 horizon.

- 34,422 event dates were trading sessions.
- 5,598 event dates were non-session dates.
- all 5,598 mapped deterministically to a later trading session;
- mapping failures: 0;
- backward mappings: 0.

Rows outside the RAW history horizon are reported separately and are not pulled into the observed period.

Evidence: `docs/SOURCE_CA_CALENDAR_AUDIT.md`.
