# PIT Feature Layer 1 — causal RAW v2 implementation status

Status date: 2026-10-04  
Implementation commit: `129ef0a2b42f96a784ae703a4aba6d26c6db5804`  
Review status: **PROGRAM IMPLEMENTED / DATA GATE BLOCKED / ASTRA REVIEW PENDING**

This status record implements the already approved minimal `layer1_60d_ma120_causal_raw_v2` direction. It does not reopen the data plan, does not unlock OOS, does not promote a strategy, and contains no strategy-effect query.

## What is now implemented

- `src/astraquant/research/causal_raw_v2.py`
  - RAW absolute close adapter for the existing universe compiler; no eligibility threshold changes.
  - Frozen `MA120`, `N60`, and prior-20-session amount windows.
  - Common-session semantics: suspension / absent observations remain null rows and are not time-compressed.
  - `N60` keeps the existing strict first-cross rule, but insufficient or non-comparable history is nullable rather than being converted to `False`.
  - Corporate-action state accepts only the already normalized cash-dividend and stock-dividend components. It applies an event only after the event is effective and `known_at < decision_cutoff_at`.
  - Historical observations retained inside a rolling window are transformed into the current causal RAW coordinate with `P_post=(P_pre-cash)/share_multiplier`, without per-event rounding.
  - Future events never rewrite already emitted feature rows. An earlier unresolved effective event blocks later event application instead of allowing an out-of-order coordinate jump.
- `configs/quality/layer1_60d_ma120_causal_raw_v2.yaml`
  - freezes source revision, windows, coordinate semantics, missingness semantics, and the current fail-closed data gate.
  - keeps the v1 artifact preserved and declares no formal v2 E1 artifact while required availability evidence is incomplete.

No execution, accounting, terminal lifecycle, signal thresholds, VCP Round 1 result, or strategy simulator behavior was changed for this implementation.

## Verification evidence

Local synthetic verification after implementation:

- causal RAW v2 core: 14 tests passed;
- core + v2/hydration integration: 17 tests passed locally;
- `tests/test_causal_raw_v2_integration.py` adds a real-Parquet CI regression for the generic hydration path;
- Python compile check passed;
- repository `tests` workflow for commit `129ef0a2` completed successfully.

Covered cases include:

1. adding a future corporate action does not change earlier feature rows;
2. a corporate action effective on a non-market day is applied once at the first later observation;
3. same-date cash/share components use one consistent coordinate without rounding drift;
4. an effective but not-yet-known event blocks MA120/N60 comparability until it is actually available;
5. an event with unknown `known_at` remains fail-closed;
6. a prior unresolved event prevents a later event from being applied out of order;
7. `known_at == decision_cutoff_at` is not treated as available;
8. MA120/N60 comparability flags agree with their explicit feature states;
9. N60 warmup/missing history is null, not a false breakout result;
10. prior-20 amount excludes the current session and preserves missing common-session rows;
11. hydration preserves logical row count and the v2 formula/coordinate fields;
12. hydration rejects source data available at or after the decision cutoff;
13. an E1-only hydration request rejects an E2 key before artifact loading.

The local sandbox did not have `pyarrow`, so the new v2-specific local hydration test substitutes only the physical parquet reader. The production join/gate class itself is exercised; the repository's existing integration tests continue to cover real parquet schema/checksum loading in the CI dependency environment.

## Workflow guardrail added during B

The ordinary `push` trigger was removed from the ten workflows that publish or recompute strategy-effect, falsification, sensitivity, replication, or performance results. They remain available through explicit `workflow_dispatch`. Ordinary source commits therefore no longer fan out into effect queries merely because `src/astraquant/**` changed. The normal unit-test workflow remains unchanged.

This is a workflow-governance correction, not research evidence. The accidental runs from commit `129ef0a2` are not used to clear any data or research gate.

## Data gate — still blocked

Program correctness is not equivalent to real historical availability. The formal E1 feature artifact remains blocked by the following evidence gaps:

| dependency | source table / fields | required period | current status | evidence gap | affected capability |
| --- | --- | --- | --- | --- | --- |
| RAW OHLC | `data/raw/prices_raw_YYYY.parquet`: date, stock_id, open, max, min, close | 2015 warmup + E1 | UNKNOWN | historical receipt/publication evidence before the order-intent cutoff is not retained | RAW eligibility, MA120, N60 |
| Trading_money | `data/raw/prices_raw_YYYY.parquet`: date, stock_id, Trading_money | 2015 warmup + E1 | UNKNOWN | historical receipt/publication evidence before the order-intent cutoff is not retained | turnover cross-section, prior20 amount |
| RAW tradability | `data/reference/tradability.parquet`: observed_trade, valid_ohlc, buy_blocked, sell_blocked | 2015 warmup + E1 | UNKNOWN | flags are reproducible, but cutoff availability of their underlying historical inputs is not proven | missing-session semantics, universe eligibility, execution gate |
| normalized cash/stock actions | `data/fundamentals/dividend.parquet`: available/announcement/ex-date and cash/share component fields | 2015 warmup + E1 | UNKNOWN | complete `known_at` coverage and reconciliation are not proven for every required event | causal price coordinate, MA120, N60 |
| non-dividend share events | `data/reference/corporate_actions_ledger.parquet`: event_date, known_date, event_type, cash_per_share, share_multiplier | 2015 warmup + E1 | UNAVAILABLE in current v2 normalizer | current certified normalizer covers only cash/stock dividend components; no multiplier/timing is guessed for other events | affected ticker rolling windows |

`raw_history_coverage_by_year.csv` showing row coverage is useful completeness evidence, but it is not historical publication-time evidence and therefore does not clear the availability gate.

## Artifact decision

No formal E1 causal RAW v2 feature artifact or quality report is produced from real source data in this state. Doing so would require silently turning UNKNOWN/UNAVAILABLE dependencies into verified inputs. Synthetic fixtures are test evidence only and are not represented as real-data availability.

The next reviewable step for item 5 is therefore Astra validation of the implementation plus source-backed closure (or an explicit approved fail-closed treatment) of the data dependencies above. Until then, item 5 remains in progress and dependent strategy work remains blocked.
