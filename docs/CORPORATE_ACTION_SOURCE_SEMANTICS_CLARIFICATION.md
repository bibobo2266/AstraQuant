# Corporate-Action Source Semantics Clarification

Status: **DOCUMENTED — source-code-verified where noted; upstream field-coverage claims still require direct parquet audit**

Purpose: preserve the clarified semantics around `ex_right_dividend`, cash-entitlement basis, share multipliers, known-date handling, and payment-date availability before any further accounting changes.

## Repository/source-of-truth clarification

The frozen read-only source repository `bibobo2266/minervini_picks` **does contain**:

- `data/reference/corporate_actions_ledger.parquet`
- `scripts/build_corporate_actions_ledger.py`
- `scripts/fetch_official_corporate_actions.py`
- `data/fundamentals/dividend.parquet`

The canonical source ledger is therefore built in `minervini_picks`; it is not an AstraQuant-created source artifact.

AstraQuant must continue treating `minervini_picks` as immutable/read-only.

## Source-code-verified field construction

### TPEx official ex-right/ex-dividend path

In `minervini_picks/scripts/fetch_official_corporate_actions.py`, TPEx `exDailyQ` rows are converted as follows:

- official event type: `ex_right_dividend`
- `event_date`: parsed from the official ex-right/ex-dividend result date
- `cash_per_share`: taken from the TPEx cash field
- `rights_ratio`: taken from the TPEx stock-distribution field
- `share_multiplier`: computed as `1 + stock / 1000`

Therefore, for this TPEx source path, the code explicitly interprets the stock field as a **per-1,000 pre-event-share distribution** and converts it into a post/pre share multiplier.

Example:

- opening shares = 1,000
- TPEx stock field = 100 shares per 1,000
- `share_multiplier = 1 + 100/1000 = 1.1`
- post-event shares = 1,100

This is different from a source field expressed as stock-dividend currency units per share; such a field must not automatically reuse the `/1000` conversion.

## Cash-entitlement basis

The accounting interpretation currently used by AstraQuant is:

`cash entitlement = opening/pre-event shares × cash_per_share`

Then, if the same economic event also carries a share mutation:

`post-event shares = opening/pre-event shares × share_multiplier`

This ordering is consistent with the verified TPEx source-builder semantics and avoids using post-mutation shares as the cash-dividend entitlement basis.

AstraQuant therefore models supported combined events as:

1. snapshot opening/pre-event holdings;
2. accrue cash entitlement from those opening holdings;
3. apply the explicit share multiplier;
4. continue RAW-coordinate accounting.

This is implemented via `CashEntitlementBasis.OPENING_POSITION`.

## FinMind dividend-row construction

In `minervini_picks/scripts/build_corporate_actions_ledger.py`, `data/fundamentals/dividend.parquet` rows are mapped into ledger rows with:

- `event_type = dividend`
- `event_date` from the dividend row `date`
- `known_date` from `available_date`, falling back to `AnnouncementDate`
- `cash_per_share` from `CashEarningsDistribution`, falling back to `CashDividend`
- `rights_ratio` from `StockEarningsDistribution`, falling back to `StockDividend`
- `share_multiplier` is not created for this FinMind row by that builder

This explains why the source profile showed all ordinary `dividend` ledger rows with populated `known_date`, while official `ex_right_dividend` rows had `known_date` blank.

## Official ex-right/dividend known-date limitation

The official TWSE/TPEx fetch path currently creates `ex_right_dividend` rows without populating `known_date`.

That does **not** imply that announcement information can never exist upstream. It means the current official-event ingestion path does not preserve it.

Any future enrichment must prove a safe event-level join between announcement information and the official economic event before populating `known_at`. Do not infer or backfill it from adjusted prices.

## Payment-date limitation

The canonical ledger schema currently has no payment-date column.

An external review reported that the upstream dividend dataset may contain `CashDividendPaymentDate` for many rows. This claim is plausible but has **not yet been independently verified by AstraQuant against the frozen parquet in this clarification task**.

Before changing accounting, run a dedicated read-only source audit for:

- `CashDividendPaymentDate` presence and coverage;
- logical-key uniqueness;
- relation to `event_date`;
- relation to `available_date` / `AnnouncementDate`;
- whether payment dates can be joined unambiguously to canonical dividend events.

Until that audit passes, unknown payment dates remain UNKNOWN and receivables must not be settled on guessed dates.

## Event-package interpretation

A combined `ex_right_dividend` row may carry both cash and stock components. For supported rows, AstraQuant treats those components as one economic package on one effective/ex-date, while preserving distinct accounting components:

- cash receivable component;
- share-mutation component.

The consumer must not silently double-count equivalent duplicate source representations.

The existing overlap audit remains authoritative for duplicate-source handling.

## 100x-conversion risk

A permanent guardrail:

- use `/1000` only for fields whose documented source unit is **shares distributed per 1,000 pre-event shares**;
- do not apply `/1000` to stock-dividend values expressed in currency units per share;
- every source field must retain provenance and unit semantics before conversion to `share_multiplier`.

A wrong unit conversion can create a 10x/100x share-count error without necessarily causing a runtime exception.

## Source-code references inspected read-only

From `bibobo2266/minervini_picks`:

- `scripts/build_corporate_actions_ledger.py`
- `scripts/fetch_official_corporate_actions.py`
- `scripts/fix_corporate_actions.py`

No source-repository file was modified.

## Current accounting decision

Keep the following frozen unless a source audit disproves them:

- supported TPEx cash entitlement basis = opening/pre-event holdings;
- TPEx `share_multiplier = 1 + stock_per_1000 / 1000`;
- source `event_date` remains the economic/ex-date coordinate;
- mapped trading session is a separate simulation coordinate;
- unknown announcement/payment dates stay unknown;
- no adjusted-price inference is allowed for entitlement basis, share multiplier, known date, or payment date.

## Next source audit

Audit `data/fundamentals/dividend.parquet` directly for announcement/ex/payment fields and quantify whether canonical events can be safely enriched without changing the frozen source repository.
