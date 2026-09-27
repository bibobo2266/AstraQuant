# Source Canonical Breakout Signal Audit

Status: **PASS**

Purpose: validate canonical simple-breakout candidate generation on frozen source data without evaluating returns.

## Configuration

- adjusted research input: 2024–2026
- audited signal period: 2025-01-01 through 2026-09-24
- breakout lookback: 250 sessions
- daily universe: top 25% by turnover among numeric four-digit, valid adjusted, observed/valid tradability stock-days
- signal availability: after signal-session close
- intended fill coordinate: next-session RAW open

## Candidate counts

- canonical signal candidates: 6,085
- candidates with known next source session: 6,072
- final-session candidates awaiting a future session: 13
- next-session RAW/tradability executable candidates: 6,000
- next-session candidates blocked/unavailable: 72

### By year

| Year | Signal candidates |
|---:|---:|
| 2025 | 2,359 |
| 2026 | 3,726 |

### Recent monthly counts

| Month | Signal candidates |
|---|---:|
| 2025-10 | 293 |
| 2025-11 | 236 |
| 2025-12 | 324 |
| 2026-01 | 493 |
| 2026-02 | 230 |
| 2026-03 | 418 |
| 2026-04 | 628 |
| 2026-05 | 713 |
| 2026-06 | 539 |
| 2026-07 | 280 |
| 2026-08 | 226 |
| 2026-09 | 199 |

## Gates

| Gate | Result |
|---|---|
| signals_nonempty | PASS |
| signal_available_same_close_date | PASS |
| signal_day_tradability_valid | PASS |
| price_semantics_declared | PASS |
| ca_window_requirement_declared | PASS |
| execution_mapping_uses_next_session | PASS |
| raw_execution_coordinate_checked | PASS |
| no_adjusted_execution_price_emitted | PASS |

## Interpretation

Signal generation remains an adjusted-research operation. The audit maps candidates to the following source session only to classify whether a RAW/tradability execution price exists; adjusted close is never reused as an execution price.

No CAGR, return, drawdown, hit-rate, ranking-quality, or strategy comparison is computed here.

## Next gate

Convert canonical signal candidates into a deterministic portfolio-intent policy (board-lot sizing, capacity, re-entry, stop/expiry rules) that feeds CanonicalExecutionService. Performance remains locked while that migration is incomplete.
