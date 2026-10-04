# PIT Feature Layer 1 causal RAW v2 — real-data gate closure

Status date: 2026-10-04  
Status: **EVIDENCE CLOSED TO ACTIONABLE GAPS / DATA GATE BLOCKED / ASTRA REVIEW PENDING**  
Source revision: `fb8b042b46dc38838d103544ca17da10286c7bfe`  
Scope: 2015 warmup + E1 (2016-01-04 through 2021-12-31)

This report closes the evidence inventory for owner queue item 5. It does not approve
item 5, does not build a formal E1 feature artifact, does not query E2/E3 effects,
and does not authorize a strategy backtest.

The evidence-only audit calculation completed successfully in workflow
`37165519596`. The workflow later failed only in the git writeback step after a
local evidence commit because `git pull --rebase` found runner-side unstaged
changes. The successful calculation was **not recomputed**. Aggregate evidence
below was recovered from the job log. The detailed ticker/event CSVs were not
published, which also preserves the rule that private source rows must not be
committed to the public repository.

## Decision cutoff in force

The approved machine gate remains:

`source_available_at < CanonicalStrategySimulator._session_start(T+1)`

The current simulator represents that next-session start as the date-level
`T+1 00:00` cutoff. Evidence is evaluated against that existing contract. A
source need not retain per-record receiver seconds if a credible historical
publication rule proves that the data was public before the cutoff. Conversely,
an event date, a retrieval timestamp, and evidence that today's historical value
is the same version that existed then are separate claims.

## Dependency evidence table

| dependency | frozen data / actual version | historical publication evidence | source acquisition / revision evidence | cutoff conclusion | affected scope | minimum remedy |
| --- | --- | --- | --- | --- | --- | --- |
| RAW OHLC | `data/raw/prices_raw_2015..2021.parquet`; 3,306,022 rows / 2,316 tickers; fixed at source revision `fb8b042b` | TWSE Daily Quotes are produced on each trading day at about 14:00 / 15:30 / 17:30 and include OHLC. TPEx has same-day post-market quote products; its historical daily-close site covers the warmup period. FinMind TaiwanStockPrice documents weekday 17:30 updates. These rules support publication before the existing T+1 00:00 cutoff. | Frozen files were reconstructed/backfilled in Sep 2026, not retained as E1 point-in-time snapshots. Current source mix is 1,775,524 TWSE_MI_INDEX; 1,353,445 TPEx_OTC_QUOTES; 106,721 FinMind:TaiwanStockPrice; 65,205 FinMind:TaiwanStockPrice_GAP_FILL; 5,127 TPEx_OTC_HTML_TARGETED. The source gap-fill ledger reports 171,925 FinMind rows added for 2015-2021 with 0 target rows unrecovered and 0 existing rows overwritten. Historical bit/version identity and any later correction chain are not retained. | **Timing supported; historical version identity unresolved. Overall dependency stays UNKNOWN.** | OHLC-null rows are explicit: 2015 6,895; 2016 8,221; 2017 7,334; 2018 9,304; 2019 9,425; 2020 8,435; 2021 8,180. These rows cause explicit non-comparable rolling windows rather than being dropped. | Obtain source/version evidence for the reconstructed official/FinMind historical rows (for example, immutable as-published archive/version metadata or a documented correction lineage). No owner trading decision is needed. |
| Trading_money | Same frozen RAW files; `Trading_money` has 0 null rows on the 3,306,022 stored RAW keys in 2015-2021. | TWSE Daily Quotes explicitly include Trading Value and share the same same-day production schedule; TPEx daily close exposes成交金額; FinMind TaiwanStockPrice includes Trading_money and documents weekday 17:30 updates. | Same 2026 reconstruction/acquisition history and same mixed-source version risk as RAW OHLC. | **Timing supported; historical version identity unresolved. Overall dependency stays UNKNOWN.** | Stored RAW keys have no Trading_money nulls. Common-session rows absent from RAW remain explicit through tradability; prior20 windows touching such rows remain missing instead of being compressed. | Same source/version-lineage evidence as RAW. No unrelated TRI/chip/fundamental input is required. |
| tradability feature fields | `data/reference/tradability.parquet`; warmup+E1 audit scanned 3,023,736 rows. For causal-v2 feature construction the required fields are `observed_trade` and `valid_ohlc`. | These two fields are deterministic from market-session presence and RAW OHLC validity; they do not require an independent publication clock once their RAW inputs are valid for the cutoff. | Audit found 0 `valid_ohlc` reconstruction mismatches on RAW keys, 0 observed_trade=True rows without a RAW key, and 0 RAW keys marked observed_trade=False. There are 11,287 explicit derived missing rows. `buy_blocked` / `sell_blocked` additionally depend on execution/limit semantics and are not inputs to the minimal MA120/N60/prior20 feature artifact. | **Derivation verified; availability inherits unresolved RAW version identity. Overall feature dependency stays UNKNOWN, but buy/sell execution flags are no longer misclassified as a feature-artifact prerequisite.** | 11,287 explicit missing rows remain visible. They affect only windows that touch them; no session compression, ticker deletion, or year deletion is authorized. | Close RAW version evidence. Execution-layer `buy_blocked`/`sell_blocked` remains a separate later gate and is not weakened. |
| cash / stock dividend effective date + known_at | `data/fundamentals/dividend.parquet`, normalized through `astraquant.data.corporate_actions`. Warmup+E1: 10,097 normalized cash/stock components, 1,581 tickers. Component/economic reconciliation program is frozen at `9914525f`; full closure is in `docs/CA_DIVIDEND_COMPONENT_RECONCILIATION_CLOSURE.md`. | FinMind schema carries separate cash/stock ex-dates plus AnnouncementDate and AnnouncementTime. Current TWSE/TPEx official documentation provides source-specific cash/allotment semantics, but those semantics are not treated as one universal multiplier formula. | Frozen dividend parquet was backfilled/rebuilt in Sep 2026. `known_at` preserves AnnouncementDate+AnnouncementTime when present. Final private reconciliation run `37171913233` classified 11,156 source-all economic event groups: 2,972 consistent, 5 value/unit conflicts, 1,627 outside certified normalizer scope, 142 evidence-backed genuine source-event misses, and 6,410 insufficient-evidence groups. Same-date proven component-missing groups: 0. Historical revision/cancellation lineage remains unknown because frozen source builders retain current state rather than an as-published revision chain. | **Component-level reconciliation is complete, but source economics/completeness are only partially verified. Dependency stays UNKNOWN.** | The prior 2,172 official-only rows are no longer treated as one missing count. Private versioned review candidates contain 142 evidence-backed supplements plus 5 value-conflict reviews. Theoretical window estimates are explicitly not actual builder unblock counts; current fail-closed engine behavior is unchanged. | Astra reviews the CA closure and private 147-row candidate set. Remaining CA evidence gaps include 6,410 insufficient-evidence event groups, TWSE historical economic-detail completeness, source-specific stock-unit/par-value proof, and revision/cancellation lineage. Do not infer cash, multiplier, known_at, or silently change population. |
| non-dividend share changes | `data/reference/corporate_actions_ledger.parquet`; audited event types: capital_reduction, par_value_change_split, capital_reduction_deficit. | TWSE/TPEx official corporate-action products establish that these are exchange-published events, but the current frozen ledger does not retain sufficient historical known-date/economic fields for almost all affected rows. | Warmup+E1: 386 rows / 310 tickers; 385 known_date missing; 209 share_multiplier missing/invalid. Current causal-v2 normalizer intentionally certifies only CASH_DIVIDEND and STOCK_DIVIDEND. | **UNAVAILABLE for affected windows under the current certified v2 input.** | 375 events overlap an E1 MA120 dependency window; 364 overlap an E1 N60 dependency window. Year/type aggregate scope is listed below. Windows outside those dependency spans are unaffected by this blocker, but formal population scope is unchanged. | Join source-specific official event detail that supplies both event timing/known-at evidence and an interpretable share mutation. If either is absent, keep those exact windows blocked; do not drop the ticker/year or infer a multiplier. |

## RAW / Trading_money coverage recovered from the successful audit

| year | rows | tickers | OHLC-null rows | Trading_money-null rows |
| ---: | ---: | ---: | ---: | ---: |
| 2015 | 413,367 | 1,787 | 6,895 | 0 |
| 2016 | 436,698 | 1,851 | 8,221 | 0 |
| 2017 | 457,479 | 1,923 | 7,334 | 0 |
| 2018 | 477,096 | 1,998 | 9,304 | 0 |
| 2019 | 490,775 | 2,100 | 9,425 | 0 |
| 2020 | 511,972 | 2,143 | 8,435 | 0 |
| 2021 | 518,635 | 2,178 | 8,180 | 0 |

Across warmup+E1 there are 3,306,022 RAW rows, 2,316 distinct tickers,
57,794 rows with at least one null OHLC field, 0 duplicate logical keys, and
1,712 market-session dates in the recovered audit.

## Cash / stock normalized timing scope

| year | component | rows | tickers | known_at missing | known after effective date | not known before first affected observation cutoff |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 2015 | CASH_DIVIDEND | 1,163 | 1,163 | 0 | 4 | 2 |
| 2015 | STOCK_DIVIDEND | 254 | 254 | 0 | 1 | 1 |
| 2016 | CASH_DIVIDEND | 1,177 | 1,177 | 0 | 1 | 1 |
| 2016 | STOCK_DIVIDEND | 210 | 210 | 0 | 0 | 0 |
| 2017 | CASH_DIVIDEND | 1,207 | 1,207 | 0 | 1 | 1 |
| 2017 | STOCK_DIVIDEND | 189 | 189 | 0 | 0 | 0 |
| 2018 | CASH_DIVIDEND | 1,250 | 1,250 | 0 | 1 | 0 |
| 2018 | STOCK_DIVIDEND | 185 | 185 | 0 | 1 | 0 |
| 2019 | CASH_DIVIDEND | 1,308 | 1,294 | 0 | 4 | 1 |
| 2019 | STOCK_DIVIDEND | 166 | 166 | 0 | 0 | 0 |
| 2020 | CASH_DIVIDEND | 1,299 | 1,275 | 0 | 0 | 0 |
| 2020 | STOCK_DIVIDEND | 144 | 143 | 0 | 0 | 0 |
| 2021 | CASH_DIVIDEND | 1,390 | 1,342 | 0 | 0 | 0 |
| 2021 | STOCK_DIVIDEND | 155 | 154 | 0 | 0 | 0 |

The 6 late-for-first-observation components are not converted to early-known
events. Existing causal-v2 logic blocks coordinate comparability until their
`known_at < decision_cutoff_at` condition is actually true.

## How missing dividend events are detected

Completeness is not inferred from the rows already present in FinMind. The audit
starts from the independent official `corporate_actions_official.csv`
ex-right/dividend population, then left-matches normalized cash/stock components
by stock and economic ex-date.

| year | official source | official rows | tickers | normalized same-stock/date matches | unmatched candidates |
| ---: | --- | ---: | ---: | ---: | ---: |
| 2015 | TPEx exDailyQ | 510 | 488 | 444 | 66 |
| 2015 | TWSE TWT49U | 747 | 715 | 652 | 95 |
| 2016 | TPEx exDailyQ | 510 | 491 | 454 | 56 |
| 2016 | TWSE TWT49U | 734 | 711 | 657 | 77 |
| 2017 | TPEx exDailyQ | 534 | 507 | 467 | 67 |
| 2017 | TWSE TWT49U | 781 | 746 | 682 | 99 |
| 2018 | TPEx exDailyQ | 587 | 537 | 498 | 89 |
| 2018 | TWSE TWT49U | 825 | 772 | 710 | 115 |
| 2019 | TPEx exDailyQ | 777 | 625 | 535 | 242 |
| 2019 | TWSE TWT49U | 880 | 817 | 742 | 138 |
| 2020 | TPEx exDailyQ | 940 | 637 | 536 | 404 |
| 2020 | TWSE TWT49U | 888 | 804 | 735 | 153 |
| 2021 | TPEx exDailyQ | 966 | 659 | 565 | 401 |
| 2021 | TWSE TWT49U | 973 | 866 | 803 | 170 |

An unmatched row is only a **candidate gap**. It is not permission to manufacture
a cash amount, share multiplier, event kind, or known_at.

The subsequent component-level reconciliation is now complete. Using one conserved
economic-event unit across both directions, the 2,172 official-only candidates resolve to
a mixture of explicit classes rather than one missing-event bucket. Source-all warmup+E1
contains 11,156 event groups: 2,972 component/value-consistent, 5 value/unit conflicts,
1,627 outside the certified normalizer scope, 142 evidence-backed genuine source-event
misses, and 6,410 insufficient-evidence groups; the remaining primary classes are zero.
There are 504 normalized-only groups and 8,480 exact-date groups present on both sides.
The private versioned candidate table contains 142 supplementation candidates plus 5
economic-value reviews. See `docs/CA_DIVIDEND_COMPONENT_RECONCILIATION_CLOSURE.md`
and `out/ca_dividend_component_reconciliation_v1.json`.

## Non-dividend share-event affected scope

| year | event type | rows | tickers | known_date missing | multiplier missing/invalid | events with E1 MA120 impact | events with E1 N60 impact |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2015 | capital_reduction | 43 | 43 | 43 | 24 | 32 | 21 |
| 2015 | capital_reduction_deficit | 1 | 1 | 0 | 0 | 1 | 1 |
| 2016 | capital_reduction | 59 | 58 | 59 | 32 | 59 | 59 |
| 2017 | capital_reduction | 62 | 61 | 62 | 37 | 62 | 62 |
| 2018 | capital_reduction | 63 | 63 | 63 | 34 | 63 | 63 |
| 2019 | capital_reduction | 53 | 52 | 53 | 27 | 53 | 53 |
| 2019 | par_value_change_split | 1 | 1 | 1 | 0 | 1 | 1 |
| 2020 | capital_reduction | 54 | 54 | 54 | 28 | 54 | 54 |
| 2020 | par_value_change_split | 1 | 1 | 1 | 0 | 1 | 1 |
| 2021 | capital_reduction | 48 | 47 | 48 | 27 | 48 | 48 |
| 2021 | par_value_change_split | 1 | 1 | 1 | 0 | 1 | 1 |

The detailed stock/event/window table was calculated transiently by workflow
`37165519596` but its git writeback failed and it was not uploaded as an
artifact. Per owner instruction, the successful data calculation was not rerun.
The public repository therefore retains only aggregate scope. Future workflow
runs keep detailed source-derived scope in runner temporary storage rather than
publishing private source rows.

## Frozen source acquisition / reconstruction timestamps

These are **repository acquisition/reconstruction timestamps**, not historical
publication timestamps:

| frozen input | repository evidence |
| --- | --- |
| fixed source revision | `fb8b042b46dc38838d103544ca17da10286c7bfe`, committed 2026-09-30T01:07:26Z |
| RAW/tradability base batch | `c190277d5e43`, 2026-09-26T15:33:24Z |
| 2016 targeted RAW repair | `9a3a46895a3c`, 2026-09-27T01:22:59Z |
| historical RAW FinMind gap fill | `034a5775e117`, 2026-09-27T08:59:16Z |
| later tradability update visible in frozen history | `2185d4e6b77a`, 2026-09-29T05:51:21Z |
| dividend parquet backfill/rebuild | `83e2212a1f8b`, 2026-09-26T03:59:24Z |
| official CA / ledger remediation | `4cafa8d33478`, 2026-09-26T13:27:03Z |

These timestamps prove when the frozen research source was assembled. They do
**not** prove when an E1 market datum was originally public and do not prove that
a 2026 historical value is identical to its original E1 version.

## Source timing evidence and revision distinction

Public source rules support the existing T+1 cutoff:

- TWSE **Daily Quotes / 每日收盤行情**: each trading day around 14:00, 15:30,
  and 17:30; includes OHLC and Trading Value; history begins 2003-12-01.
- TPEx post-market product catalogue: individual daily quote products are
  produced during the same trading day; its historical quote site provides
  older daily-close records. The current product-labelled individual daily file
  begins 2015-11-16, so that product label alone does not certify the earlier
  2015 warmup subset.
- FinMind **TaiwanStockPrice**: historical range begins 1994-10-01 and the
  documented weekday update time is 17:30; fields include OHLC and
  Trading_money.
- TWSE **除權除息資訊**: produced each trading day at 08:10; history begins
  2005-02-04 and includes ex-date, cash dividend, stock dividend and related
  fields.
- TPEx post-market **T48** ex-right/listing information: produced 21:20; history
  begins 2011-11-30.
- FinMind dividend schema separately exposes AnnouncementDate,
  AnnouncementTime, cash/stock ex-dates and cash/stock distribution fields.

These publication rules establish **when a class of data is normally public**.
They do not establish that the Sep-2026 reconstructed value is byte-for-byte
the same version that existed during E1. That unresolved version/revision
question is why RAW and Trading_money remain blocked despite publication-time
evidence.

## Minimal corrections completed

1. `a38abad253d8e319e3d034f6b4985b67399846d5` — dividend `known_at`
   now preserves source AnnouncementDate + AnnouncementTime when available,
   rather than silently preferring the source-added date-only
   `available_date`.
2. `b972b169970175b5a57d0d91df1d8603316b1635` — regression test locks the
   timestamp behavior.
3. Repository tests workflow `37165519584`: **335 passed in 5.84s**.
4. Evidence workflow `37165519596`: evidence calculation and summary publish
   steps succeeded; only git writeback failed. No calculation rerun was used to
   hide that failure.
5. `2af31b869e323cce07774e7c22635da512ba9d07` changes future evidence
   workflow persistence so private row-level scope stays transient and
   runner-side changes cannot block public aggregate writeback.

Legacy breakout regression remained a software regression only and completed
successfully. No strategy/sensitivity/Round2/E2/E3 effect report was run by
these item-5 evidence commits.

## Artifact decision

**Do not build the formal E1 causal RAW v2 feature artifact yet.**

The minimal feature path does **not** require unrelated TRI, industry, chip or
fundamental datasets, and it does **not** require execution-only
`buy_blocked`/`sell_blocked` to construct MA120/N60/prior20. However, the
full E1 artifact contract still requires source/version evidence for RAW /
Trading_money and complete, source-backed handling of the corporate actions that
can change the rolling price coordinate.

Gate conclusion: **BLOCKED**, for specific source/version and CA gaps above.
This is an evidence conclusion only. Astra still must review the implementation
and this closure; item 5 is not self-approved.

## Next executable action

The CA component/economic reconciliation requested after Astra's prior review is
complete. The immediate next action is **Astra review of the CA closure and the
versioned private 147-row candidate table**.

Other item-5 blockers remain recorded but are not started by this closure:
RAW / Trading_money historical-version identity and the 386 non-dividend
share-event evidence gaps. No owner trading-preference decision is required for
the present CA evidence classification. An owner decision would be needed only
if a source is proven intrinsically unavailable and a change to formal research
scope/semantics is proposed.
