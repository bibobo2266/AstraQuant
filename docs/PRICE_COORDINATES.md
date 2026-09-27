# Price Coordinate Guard

AstraQuant separates execution/accounting prices from research continuity prices.

## Coordinates

- `RAW_EXECUTION` — true market-price coordinate used for economic execution and accounting.
- `ADJUSTED_RESEARCH` — continuity representation used only for research/signals when feature semantics permit.

## Hard rule

The following uses require `RAW_EXECUTION` and must hard-fail on adjusted input:

- entry
- stop observation
- stop fill
- exit
- position sizing / affordability
- mark-to-market
- cash / realized P&L accounting

There is no adjusted-price execution fallback.

## Signal rule

Every signal price request must declare one of:

- `SCALE_INVARIANT`
- `SCALE_SENSITIVE`
- `RAW_REQUIRED`

Adjusted research prices may be used for the first two subject to the feature's corporate-action lookback requirement. `RAW_REQUIRED` signals must use the RAW coordinate.

This guard is intentionally narrow. Corporate-action event handling, tradability enforcement, and canonical feature masking are separate contracts.
