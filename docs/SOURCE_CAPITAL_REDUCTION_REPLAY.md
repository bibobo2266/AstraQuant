# Source-Backed Capital-Reduction Replay

Status: **PASS**

Purpose: test a real capital-reduction event carrying both a share multiplier and a cash refund component.
This validates component arithmetic and ledger behavior; it does not claim that the source event_date is a legally complete entitlement/payment timeline.

## Source event

- ticker: 3152
- event date: 2026-06-30
- known date: NaT
- share multiplier: 0.56531945
- cash per share: 4.34680553
- source: TPEx revivt

## Replay

- pre-event RAW entry session: 2026-06-22
- entry RAW open: 202.0
- pre-event shares: 100.0
- post-event shares: 56.53194499999999
- post-event average cost: 357.3200957440966
- post-event total cost basis: 20200.0
- cash refund receivable: 434.68055300000003
- post-event RAW mark session: 2026-06-30
- post-event RAW market value: 18344.6161525
- RAW exit close: 324.5
- final pending receivable: 434.6805529999983

## Gates

| Gate | Result |
|---|---|
| source_event_supported | PASS |
| explicit_share_multiplier | PASS |
| explicit_cash_component | PASS |
| raw_entry | PASS |
| refund_uses_pre_mutation_share_basis | PASS |
| refund_reconciles | PASS |
| share_quantity_reconciles | PASS |
| cost_basis_preserved | PASS |
| cash_unchanged_at_event | PASS |
| receivable_retained | PASS |
| unknown_payment_not_guessed | PASS |
| raw_exit | PASS |
| position_flat_after_exit | PASS |
| final_market_value_zero | PASS |
| no_adjusted_price_used | PASS |

## Source limitation

The canonical ledger has no payment-date field. The capital-reduction refund therefore remains a receivable and cannot be converted to settled cash by guessing a date.

The source event_date for capital reduction is treated as the available economic mutation coordinate for this accounting replay; legal entitlement/record/payment dates remain incomplete and must not be inferred.
