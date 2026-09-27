# Corporate-Action-Aware Stop State

Canonical stop observation and fill always use RAW prices. To keep the stop policy economically continuous across corporate actions, the managed stop level must move when the security's economic coordinate changes.

For an event with:

- pre-event stop level `S`
- pre-event cash entitlement per old share `c`
- post/pre share multiplier `m`

the post-event RAW stop is:

`S' = (S - c) / m`

because economic equivalence requires:

`m × S' + c = S`

Examples:

- pure split: `c=0`, so stop divides by the share multiplier;
- cash dividend: `m=1`, so stop is reduced by cash/share;
- capital reduction with cash refund and share replacement: both terms apply.

The portfolio ledger remains responsible for actual share/cash accounting. The policy adjustment only keeps the RAW stop threshold on a consistent economic basis.

No adjusted execution price is introduced.
