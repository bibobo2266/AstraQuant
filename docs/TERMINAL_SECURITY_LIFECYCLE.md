# Terminal Security Lifecycle

Status: **PASS — canonical terminal-merger path validated**

Purpose: define how AstraQuant handles a held security whose RAW market history ends because trading is suspended and the security is later extinguished for cash through a merger/delisting.

## Accounting rule

A terminal security is not treated as an ordinary missing-price gap.

The canonical lifecycle is:

1. last valid RAW trading session;
2. explicit terminal suspension window begins;
3. valuation may carry the last valid RAW close only while that declared terminal window is active;
4. entries, exits, sizing, and stops remain non-executable without same-session RAW/tradability;
5. at the merger/delisting economic effective date, opening/pre-event shares determine the cash entitlement;
6. the position is extinguished through an explicit exogenous corporate-action mutation, never through a synthetic trade fill;
7. the cash entitlement remains a receivable until the declared payment date;
8. on payment date, receivable moves to settled cash.

Adjusted prices are never used as a fallback.

## 4141 source-backed regression case

The long-horizon strategy probe exposed ticker 4141 after its final RAW session on 2022-04-26.

Public merger/delisting disclosures establish:

- final trading date: 2022-04-26;
- trading suspension starts: 2022-04-27;
- delisting / merger effective date used by the replay: 2022-05-03;
- cash consideration: TWD 26.23 per outstanding pre-event share;
- expected payment date: 2022-05-10;
- the outstanding common shares are cancelled in exchange for the cash right.

AstraQuant models this as a `MERGER` corporate action with:

- `CashEntitlementBasis.OPENING_POSITION`;
- `terminal_stale_from = 2022-04-27`;
- `extinguish_position = True`;
- explicit `payment_at = 2022-05-10`.

The terminal stale mark is valuation-only and is permitted only before the effective extinguishment date.

## Implementation

Core paths:

- `src/astraquant/execution/market_data.py`
  - explicit `allow_terminal_stale_without_tradability` for MARK only;
  - no change to execution eligibility.

- `src/astraquant/portfolio/models.py`
  - `PositionExtinguishment` records the exogenous terminal mutation.

- `src/astraquant/portfolio/ledger.py`
  - explicit position-extinguishment path sets quantity to zero without fabricating a sell fill.

- `src/astraquant/portfolio/corporate_actions.py`
  - merger extinguishment is recorded as corporate-action accounting.

- `src/astraquant/portfolio/historical_runner.py`
  - terminal instructions can declare suspension start and extinguishment.

- `src/astraquant/portfolio/strategy_simulator.py`
  - carries RAW valuation only inside a declared terminal window;
  - accrues merger cash on opening shares;
  - extinguishes the position on the effective date;
  - settles the receivable on the declared payment date.

## Regression evidence

Unit test:

- `tests/test_strategy_simulator.py::test_terminal_merger_carries_last_raw_then_extinguishes_and_pays`

The test verifies:

- 1,000 shares remain valued from last RAW close during the suspension window;
- merger cash entitlement is 1,000 × 26.23 = 26,230;
- shares are extinguished on the merger effective date;
- pending receivable is paid on 2022-05-10;
- final settled cash is 26,230;
- no synthetic trade is required.

Source evidence:

- `docs/SOURCE_TERMINAL_SECURITY_AUDIT.md`
- `docs/SOURCE_MARK_GAP_AUDIT.md`

Full integration evidence:

- `docs/SOURCE_STRATEGY_LONG_HORIZON_PROBE.md`

The long-horizon probe now passes from 2016-01-04 through the 2026-07-07 drain horizon with 2,559 RAW NAV snapshots and no adjusted execution fallback.

## Scope limitation

The framework is generic, but the current curated terminal-event feed contains the specifically verified 4141 merger/delisting case required by the long-horizon regression.

Additional terminal securities must be added only from explicit source-backed suspension/effective/cashout/payment facts. AstraQuant must not infer terminal economics merely because RAW history stops.

## Repository boundary

The source repository `bibobo2266/minervini_picks` remains read-only. All terminal-event handling and regression logic are implemented in AstraQuant.
