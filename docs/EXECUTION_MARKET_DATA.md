# Execution Market Data Gateway

AstraQuant now has a RAW-only execution market-data gateway in `src/astraquant/execution/market_data.py`.

## Contract

An intended execution price request must:

1. declare an execution/accounting `PriceUse`;
2. resolve from the yearly RAW price parquet;
3. have exactly one RAW `(date, stock_id)` row;
4. pass RAW OHLC validity;
5. have exactly one matching tradability row;
6. satisfy `observed_trade=True` and `valid_ohlc=True`;
7. not be blocked for the requested side.

If any condition fails, the request returns `NOT_EXECUTABLE` with no price.

There is no adjusted-price fallback.

## Supported RAW fields

- open
- high (source column `max`)
- low (source column `min`)
- close

## Tradability

Buy requests enforce `buy_blocked`; sell requests enforce `sell_blocked`.

Missing tradability is itself non-executable. This prevents a missing eligibility state from silently becoming permission to trade.

## Runtime behavior

Yearly RAW data and the tradability table are cached inside one gateway instance so repeated execution requests do not repeatedly reload the same parquet files.

## Scope

This component establishes the data-access boundary only. It does not yet:

- create fills;
- apply fees/slippage;
- mutate positions;
- process corporate actions;
- reconcile cash/receivables/NAV.

Those remain subsequent Phase-2 tasks.
