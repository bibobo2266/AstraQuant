# Successor / Terminal Security Cases

Status: **PASS — source-backed regression cases integrated**

Purpose: document explicit terminal-security and successor-security cases required by the canonical strategy/accounting path. Missing RAW history alone never creates a corporate-action assumption.

## 6251 定穎 → 3715 定穎投控

Source-backed facts:

- 6251 last trading date: 2022-08-12.
- trading suspension begins: 2022-08-15.
- delisting / share-conversion effective date: 2022-08-25.
- successor security: 3715 定穎投控.
- conversion ratio: 1 share of 6251 converts to 1 share of 3715.
- 3715 begins listed trading on 2022-08-25.

AstraQuant treatment:

- valuation-only stale RAW mark for 6251 is permitted during the declared 2022-08-15 through pre-conversion suspension window;
- on 2022-08-25 the position is converted exogenously from 6251 to 3715 at a 1.0 quantity multiplier;
- cost basis is transferred rather than realizing a synthetic trade;
- managed policy state moves from 6251 to 3715;
- subsequent marks/exits use 3715 RAW data.

Source references:

- https://www.moneydj.com/KMDJ/news/newsviewer.aspx?a=3dbfbc6a-01a5-4eda-87f9-d2aa3530a649
- https://www.moneydj.com/kmdj/news/newsviewer.aspx?a=099b1a66-92f7-47a2-b29c-840609170bf1
- TWSE 2022 market statistics / listing-change records.

Regression evidence:

- `tests/test_strategy_simulator.py::test_successor_security_conversion_moves_position_and_policy_state`
- source terminal / RAW mark audits performed against the frozen read-only source checkout.

## 5305 敦南 cash conversion

Source-backed facts:

- last trading date: 2020-11-23.
- trading suspension begins: 2020-11-24.
- share-conversion / delisting effective date: 2020-11-30.
- consideration: TWD 42.5 cash per common share.
- declared expected consideration payment date: 2020-12-04.

AstraQuant treatment:

- valuation-only stale RAW mark during the declared suspension window;
- opening/pre-event shares receive TWD 42.5 per share on the effective date;
- the position is explicitly extinguished as a merger corporate action rather than through a synthetic sell fill;
- cash remains a receivable until the declared payment date.

Source references:

- https://www.moneydj.com/kmdj/news/newsviewer.aspx?a=08e82787-ac21-4b82-a7e5-0457c205ba74
- TWSE delisting records for 2020.

Source audit evidence:

- final frozen-source RAW observation for 5305: 2020-11-23;
- no RAW/tradability observation on 2020-11-24 or after;
- no ordinary nearby corporate-action row in the existing frozen CA ledger explains the terminal lifecycle.

## Canonical invariants

- adjusted prices are never used to fabricate terminal marks or conversion economics;
- no missing-RAW inference is allowed without explicit source-backed lifecycle facts;
- successor conversion preserves economic cost basis and does not create a realized trade;
- cash takeovers use opening/pre-event share entitlement;
- payment timing is declared, not guessed;
- signals/recommendations never mutate holdings.

## Validation status

After adding successor-security conversion support and the two explicit cases above:

- unit CI passes;
- source strategy integration smoke passes;
- full long-horizon canonical accounting probe passes;
- descriptive performance report passes;
- fixed-path execution-cost attribution passes.

The source repository `bibobo2266/minervini_picks` remained read-only and unchanged.
