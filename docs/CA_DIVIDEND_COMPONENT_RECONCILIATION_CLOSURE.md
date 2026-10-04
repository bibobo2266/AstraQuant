# CA dividend component / economic reconciliation closure

Status date: 2026-10-04  
Status: **RECONCILIATION COMPLETE / ITEM 5 STILL BLOCKED / ASTRA REVIEW REQUIRED**  
Frozen source revision: `fb8b042b46dc38838d103544ca17da10286c7bfe`  
Frozen reconciliation program revision: `9914525fe7db92a69fc08360823fb679518ee0b8`  
Scope: 2015 warmup + full E1 through 2021-12-31

This is a CA-only reconciliation closure. It does not investigate RAW historical-version
identity, does not complete the 386 non-dividend share events, does not change the
canonical CA/accounting/execution engine, does not build the formal E1 feature artifact,
and does not run Round 2, baseline, E2/E3, or any strategy-effect query.

The fixed private run completed in workflow `37171913233`. Row-level source and
reconciliation tables are persisted in the authorized private repository under:

`private/astraquant/ca_dividend_component_reconciliation/v1-9914525f/`

The public repository contains only code, aggregate counts, and evidence conclusions.

## 1. Frozen inputs and counting units

| item | frozen value |
| --- | --- |
| source revision | `fb8b042b46dc38838d103544ca17da10286c7bfe` |
| reconciliation program | `9914525fe7db92a69fc08360823fb679518ee0b8` |
| source acquisition time for final run | 2026-10-04T02:45:06Z |
| dividend input SHA-256 | `f0fa98a466923b25f15135aa7f67edf0633ff00720c034f79e1bfe3851f1a415` |
| official input SHA-256 | `78d481ef10a3e3e6691d803ecf2805a8096b1c4bec4f63ac4faf717c8785300c` |
| normalized counting unit | one CASH_DIVIDEND or STOCK_DIVIDEND component |
| official counting unit | one raw official source row |
| conserved classification unit | one unique stock_id + economic effective/event date group |

The prior counts 10,652 official rows, 2,172 official-only candidates, and 10,097
normalized components use different units. They are not subtracted from each other.

## 2. Source field and unit contract

### FinMind TaiwanStockDividend

Fields retained from the frozen source include:

- `stock_id`;
- `date` (rights-distribution record/base date in the provider schema);
- `CashExDividendTradingDate` and `StockExDividendTradingDate`;
- `CashEarningsDistribution` and `CashStatutorySurplus`;
- `StockEarningsDistribution` and `StockStatutorySurplus`;
- `AnnouncementDate` and `AnnouncementTime`.

FinMind documents the cash/stock fields and separate ex-dates, and exposes
AnnouncementDate plus AnnouncementTime. The frozen 2015+E1 normalized component set
contains 10,097 components, and all 10,097 carry an exact parsed announcement timestamp.

That timestamp precision is **not** proof that the frozen 2026 copy is the exact historical
version originally published in E1. The source builder de-duplicates current rows with
keep-last semantics and does not preserve revision/cancellation history.

Cash fields are retained as source-specific per-share cash economics. For stock
distribution fields, the current normalizer's divide-by-10 transform is **not certified by
this audit as a universal or event-safe conversion**. Event par value/unit evidence is
required before the resulting share multiplier can be promoted from a candidate transform
to verified economics.

Provider schema reference:
https://finmind.github.io/tutor/TaiwanMarket/Fundamental/

### TWSE TWT49U — calculation result table

The frozen official ingest contains 5,828 warmup+E1 TWT49U rows. In that frozen shape,
TWT49U supplies event/date presence and calculation-result evidence, not the cash and
free-allotment component fields needed to certify full economic equivalence.

TWSE publishes the calculation formula using cash value, free-allotment ratio, cash
capital-increase ratio, and subscription price. Therefore a same-stock/same-date TWT49U
match is useful event evidence but is **not sufficient by itself** to certify that all
FinMind cash/stock components and values are complete.

Reference:
https://www.twse.com.tw/zh/announcement/ex-right/twt49u.html

### TWSE TWT48U — preannouncement/detail economics

The current TWSE TWT48U public schema explicitly exposes:

- ex-right/ex-dividend date;
- security ID/type label;
- free allotment ratio;
- cash capital-increase ratio;
- cash capital-increase subscription price;
- cash dividend;
- detail link.

TWSE defines free allotment ratio as bonus/capital-surplus shares divided by shares
participating in ex-rights. This is the source-specific ratio semantics needed for a
verified share-mutation join.

Reference:
https://www.twse.com.tw/zh/announcement/ex-right/twt48u.html

Two private verification snapshots attempted to acquire 2015-2021 TWT48U by annual
date ranges. The endpoint returned the same 58-row payload and identical SHA-256 for
each requested year. That result is retained as verification evidence but is **not accepted
as historical completeness or as a supplementation source**, and none of those rows is
injected into the formal normalizer.

### TPEx exDailyQ / official ex-right-dividend information

The frozen official ingest contains 4,824 warmup+E1 TPEx exDailyQ rows. TPEx's published
calculation contract states that the cash value is per-share cash dividend and defines
the reference-price formula in terms of free-allotment ratio and cash-capital-increase
ratio. Its published post-market format further documents free-allotment ratio as a
source-specific percentage field and cash dividend in currency units.

References:
https://www.tpex.org.tw/zh-tw/announce/market/ex/cal.html
https://www.tpex.org.tw/zh-tw/announce/market/ex/announce.html

The frozen source parser currently derives a stock multiplier from a positional field by
dividing by 1000. This audit does **not** certify that positional conversion because the
frozen parser's field-to-unit mapping has not been independently proven for the historical
rows. No cross-source blanket multiplier formula is accepted.

Private direct re-fetch attempts for TPEx exDailyQ across 2015-2021 timed out or returned
HTTP 520. Those failures are versioned in the private verification manifests and no
synthetic replacement values were introduced.

## 3. Bidirectional reconciliation and count conservation

The reconciler starts from the union of normalized effective-date event groups and
official event-date groups. It therefore detects both:

- official rows without a normalized component group; and
- normalized component groups without an official row.

Primary classes are mutually exclusive on the economic-event counting unit. Independent
issue flags remain overlapping.

### Source-all, warmup + E1

| primary class | event groups |
| --- | ---: |
| COMPONENT_VALUE_CONSISTENT | 2,972 |
| SAME_DATE_COMPONENT_MISSING | 0 |
| VALUE_OR_UNIT_CONFLICT | 5 |
| DATE_DIFFERENCE_EXPLAINED | 0 |
| DUPLICATE_REVISION_CANCEL | 0 |
| OUTSIDE_NORMALIZER_SCOPE | 1,627 |
| GENUINE_SOURCE_EVENT_MISSING | 142 |
| INSUFFICIENT_EVIDENCE | 6,410 |
| **total** | **11,156** |

The eight classes sum exactly to 11,156 event groups.

Additional source-all counts:

- exact-date groups present on both sides: 8,480;
- normalized-only groups: 504;
- official-only groups: 2,172;
- current duplicate groups: 0;
- groups whose historical revision/cancellation history is unknown: 11,156.

A current duplicate count of zero does not prove that historical revisions or cancellations
never existed. The frozen source retains current-state rows, not an as-published revision
chain.

### Matched groups

- TWSE TWT49U exact-date matched groups: 4,981. Their frozen official shape lacks
  component economics, so date identity does not certify component/value completeness.
- TPEx exDailyQ exact-date matched groups: 3,499.
- same-date component-missing findings with sufficient semantics: **0**.
- value/unit conflict findings: **5**.
- stock-unit-unverified flags across source-all groups: **1,332**.

Therefore the prior 2,172 official-only number is no longer treated as a missing-event
count.

Of those candidates, only **142** currently have sufficient source-specific official cash
evidence to be classified as `GENUINE_SOURCE_EVENT_MISSING`. The rest remain in another
explicit class, primarily insufficient evidence or outside the certified normalizer scope.

## 4. Research population and warmup dependency scopes

The population was not changed to reduce CA gaps.

| scope | event groups | distinct tickers |
| --- | ---: | ---: |
| source-all warmup+E1 | 11,156 | 1,913 |
| four-digit research security base | 9,753 | 1,722 |
| established E1 all_liquid ticker set | 7,894 | 1,329 with CA groups |

The established E1 all_liquid ticker set contains 1,394 distinct tickers in total. Among
event groups on those tickers:

- 2,379 are component/value consistent;
- 3 are value/unit conflicts;
- 115 are evidence-backed genuine source-event misses;
- 5,230 remain insufficient evidence;
- 167 are outside the certified normalizer's handled event/component scope.

Warmup-only events with a theoretical E1 dependency overlap:

- MA120: 922 event groups;
- N60: 60 event groups.

These are **calendar/dependency estimates only**. They are not counts of dates on which the
actual feature builder unblocks.

Observed valid-active-span coverage is also kept separate:

- 9,742 event groups fall inside an observed-valid active span;
- 1,414 are outside or lack such an active span.

## 5. Actual builder blocking / recovery contract

No engine recovery rule was changed.

The current causal-v2 rule remains:

1. an effective event that is unavailable at the decision cutoff blocks the current causal
   coordinate;
2. availability requires `known_at < decision_cutoff_at`;
3. an earlier unresolved event blocks application of later events so the coordinate cannot
   jump out of order;
4. an unknown known_at remains fail-closed.

The existing minimal regression case remains:

`tests/test_causal_raw_v2.py::test_earlier_unresolved_event_prevents_later_event_from_applying_out_of_order`

The reconciliation's theoretical MA120/N60 window estimates are not substituted for this
actual program behavior.

## 6. Private delivery and versioned supplementation candidates

The final private delivery contains:

- `finmind_source_rows.csv`;
- `normalized_components.csv`;
- `official_source_rows.csv`;
- `source_event_component_mapping.csv`;
- `event_reconciliation.csv`;
- `aggregate_reconciliation.csv`;
- `public_safe_summary.json`;
- `scope_aggregate.json`;
- `manifest.json`.

A follow-up private-only derivation, without re-running source reconciliation, adds:

- `supplement_candidates.csv`;
- `supplement_candidates_manifest.json`.

Candidate version: `ca_dividend_component_reconciliation_candidates_v1`.

| private review candidate | rows |
| --- | ---: |
| evidence-backed supplement (`GENUINE_SOURCE_EVENT_MISSING`) | 142 |
| economic-value review (`VALUE_OR_UNIT_CONFLICT`) | 5 |
| **total** | **147** |

`INSUFFICIENT_EVIDENCE`, out-of-scope events, and mere same-date matches are explicitly
not promoted into this supplementation file.

## 7. Evidence obtained vs remaining evidence gap

Evidence obtained this round:

- event/component mapping is stable and bidirectional;
- primary classifications conserve one common event counting unit;
- no matched group has a proven same-date component omission under currently verified
  source semantics;
- five value conflicts are isolated for review;
- 142 evidence-backed missing-source events are isolated for supplementation review;
- exact FinMind announcement timestamps are retained for all 10,097 normalized components;
- private row-level evidence is persistently versioned outside the public repository.

Still unresolved:

- 6,410 event groups lack enough evidence to certify economics/completeness;
- TWT49U date matches need a verified historical economic-detail join before they can
  certify cash/share completeness;
- TPEx stock-distribution positional unit conversion remains unverified;
- FinMind stock-distribution-to-share-multiplier conversion lacks event-par-value proof;
- historical revision/cancellation lineage is not retained in the frozen current-state
  sources;
- the previously documented six normalized components that were not known before the first
  affected observation cutoff remain fail-closed; this reconciliation does not move their
  known_at earlier.

No price-gap inference, guessed multiplier, guessed known_at, ticker deletion, year deletion,
or population change was used.

## 8. Gate decision

This CA reconciliation task is complete as an evidence deliverable.

It does **not** make the normalized cash/stock CA dependency fully VERIFIED and does not
unlock queue item 5. The other item-5 blockers remain unchanged, including RAW /
Trading_money historical-version identity and the separately deferred non-dividend
share-event evidence gaps.

No formal E1 causal RAW v2 artifact was built. No strategy effect was queried.

Next action: Astra reviews this CA reconciliation closure and the versioned private
candidate tables. Do not start another blocker or item 6 from this closure alone.
