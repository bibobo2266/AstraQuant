# Canonical Portfolio Intent Policy

AstraQuant now has a deterministic, configurable portfolio-intent policy for migrating the legacy finite-capital mechanics without using adjusted prices for execution.

## Configurable policy

- position fraction of current NAV
- maximum concurrent positions
- fixed stop fraction
- re-entry gap in sessions
- maximum holding period in sessions
- board-lot size
- deterministic random seed for capacity tie-breaking

No one parameter combination is promoted as a strategy winner. The policy is infrastructure for controlled replay.

## Entry sizing

Entry candidates must already have an executable RAW `SIZING` decision.

Per-position budget:

`current_NAV × position_fraction`

Board-lot quantity:

`floor(min(position_budget, available_cash) / (RAW sizing price × lot_size)) × lot_size`

Candidates that cannot afford one board lot are skipped.

## Capacity

If eligible candidates exceed open slots, selection uses a seeded RNG. The same seed and same ordered candidate set produce the same selection.

This preserves the legacy idea of random allocation under capacity pressure while making runs reproducible.

## Re-entry

A ticker may re-enter only when:

`current_session_index - last_entry_index > reentry_gap_sessions`

This preserves the legacy strict-greater-than rule.

## Stop state

Stop price is established from the **actual RAW fill price**, not adjusted price:

`stop = fill_price × (1 - stop_fraction)`

## Holding period

A managed position becomes max-hold eligible when:

`current_session_index - entry_session_index >= max_hold_sessions`

Actual exit execution remains a separate RAW execution decision.

## Remaining integration task

The next gate is to connect canonical breakout candidates, this policy, RAW stop/expiry exits, settlements, corporate actions, and RAW NAV snapshots in one historical strategy-intent simulation. Performance metrics remain locked until that integration passes accounting gates.
