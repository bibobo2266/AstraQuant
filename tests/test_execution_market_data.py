from datetime import date

import pandas as pd

from astraquant.data.market_coordinates import PriceUse
from astraquant.data.source_adapter import SourceDataAdapter
from astraquant.execution.market_data import (
    ExecutionAvailability,
    ExecutionMarketData,
)


def _write_source(tmp_path, *, raw_rows, trad_rows):
    root = tmp_path / "source"
    (root / "raw").mkdir(parents=True)
    (root / "reference").mkdir(parents=True)
    pd.DataFrame(raw_rows).to_parquet(root / "raw" / "prices_raw_2026.parquet", index=False)
    pd.DataFrame(trad_rows).to_parquet(root / "reference" / "tradability.parquet", index=False)
    return SourceDataAdapter(root)


def test_resolve_raw_open_when_tradable(tmp_path):
    source = _write_source(
        tmp_path,
        raw_rows=[{
            "date": "2026-09-24",
            "stock_id": "2330",
            "open": 100.0,
            "max": 110.0,
            "min": 99.0,
            "close": 108.0,
        }],
        trad_rows=[{
            "date": "2026-09-24",
            "stock_id": "2330",
            "observed_trade": True,
            "valid_ohlc": True,
            "buy_blocked": False,
            "sell_blocked": False,
            "reason": "OBSERVED",
        }],
    )
    market = ExecutionMarketData(source)

    decision = market.resolve(
        ticker="2330",
        session_date=date(2026, 9, 24),
        side="buy",
        use=PriceUse.ENTRY,
        field="open",
    )

    assert decision.availability is ExecutionAvailability.EXECUTABLE
    assert decision.price == 100.0
    assert decision.reason == "OK"


def test_missing_raw_is_not_executable_and_has_no_fallback(tmp_path):
    source = _write_source(
        tmp_path,
        raw_rows=[{
            "date": "2026-09-24",
            "stock_id": "2317",
            "open": 50.0,
            "max": 52.0,
            "min": 49.0,
            "close": 51.0,
        }],
        trad_rows=[{
            "date": "2026-09-24",
            "stock_id": "2330",
            "observed_trade": True,
            "valid_ohlc": True,
            "buy_blocked": False,
            "sell_blocked": False,
            "reason": "OBSERVED",
        }],
    )
    market = ExecutionMarketData(source)

    decision = market.resolve(
        ticker="2330",
        session_date=date(2026, 9, 24),
        side="buy",
        use=PriceUse.ENTRY,
        field="open",
    )

    assert decision.availability is ExecutionAvailability.NOT_EXECUTABLE
    assert decision.price is None
    assert decision.reason == "RAW_MISSING_OR_NONUNIQUE"


def test_blocked_buy_is_not_executable(tmp_path):
    source = _write_source(
        tmp_path,
        raw_rows=[{
            "date": "2026-09-24",
            "stock_id": "2330",
            "open": 100.0,
            "max": 110.0,
            "min": 100.0,
            "close": 110.0,
        }],
        trad_rows=[{
            "date": "2026-09-24",
            "stock_id": "2330",
            "observed_trade": True,
            "valid_ohlc": True,
            "buy_blocked": True,
            "sell_blocked": False,
            "reason": "LOCKED_LIMIT_UP",
        }],
    )
    market = ExecutionMarketData(source)

    decision = market.resolve(
        ticker="2330",
        session_date=date(2026, 9, 24),
        side="buy",
        use=PriceUse.ENTRY,
        field="open",
    )

    assert decision.availability is ExecutionAvailability.NOT_EXECUTABLE
    assert decision.price is None
    assert decision.reason == "LOCKED_LIMIT_UP"


def test_missing_tradability_is_not_executable(tmp_path):
    source = _write_source(
        tmp_path,
        raw_rows=[{
            "date": "2026-09-24",
            "stock_id": "2330",
            "open": 100.0,
            "max": 110.0,
            "min": 99.0,
            "close": 108.0,
        }],
        trad_rows=[{
            "date": "2026-09-24",
            "stock_id": "2317",
            "observed_trade": True,
            "valid_ohlc": True,
            "buy_blocked": False,
            "sell_blocked": False,
            "reason": "OBSERVED",
        }],
    )
    market = ExecutionMarketData(source)

    decision = market.resolve(
        ticker="2330",
        session_date=date(2026, 9, 24),
        side="sell",
        use=PriceUse.EXIT,
        field="close",
    )

    assert decision.availability is ExecutionAvailability.NOT_EXECUTABLE
    assert decision.reason == "TRADABILITY_MISSING_OR_NONUNIQUE"


def test_invalid_raw_ohlc_is_not_executable(tmp_path):
    source = _write_source(
        tmp_path,
        raw_rows=[{
            "date": "2026-09-24",
            "stock_id": "2330",
            "open": 100.0,
            "max": 95.0,
            "min": 90.0,
            "close": 94.0,
        }],
        trad_rows=[{
            "date": "2026-09-24",
            "stock_id": "2330",
            "observed_trade": True,
            "valid_ohlc": False,
            "buy_blocked": True,
            "sell_blocked": True,
            "reason": "INVALID_OHLC",
        }],
    )
    market = ExecutionMarketData(source)

    decision = market.resolve(
        ticker="2330",
        session_date=date(2026, 9, 24),
        side="sell",
        use=PriceUse.STOP_FILL,
        field="open",
    )

    assert decision.availability is ExecutionAvailability.NOT_EXECUTABLE
    assert decision.reason == "RAW_INVALID_OHLC"


def test_mark_can_observe_raw_close_on_side_blocked_day(tmp_path):
    source = _write_source(
        tmp_path,
        raw_rows=[{
            "date": "2026-09-24",
            "stock_id": "2330",
            "open": 100.0,
            "max": 110.0,
            "min": 100.0,
            "close": 110.0,
        }],
        trad_rows=[{
            "date": "2026-09-24",
            "stock_id": "2330",
            "observed_trade": True,
            "valid_ohlc": True,
            "buy_blocked": True,
            "sell_blocked": False,
            "reason": "LOCKED_LIMIT_UP",
        }],
    )
    market = ExecutionMarketData(source)

    decision = market.resolve(
        ticker="2330",
        session_date=date(2026, 9, 24),
        side="buy",
        use=PriceUse.MARK,
        field="close",
    )

    assert decision.availability is ExecutionAvailability.EXECUTABLE
    assert decision.price == 110.0


def test_ticker_scope_preserves_execution_behavior(tmp_path):
    source = _write_source(
        tmp_path,
        raw_rows=[
            {
                "date": "2026-09-24",
                "stock_id": "2330",
                "open": 100.0,
                "max": 110.0,
                "min": 99.0,
                "close": 108.0,
            },
            {
                "date": "2026-09-24",
                "stock_id": "2317",
                "open": 50.0,
                "max": 52.0,
                "min": 49.0,
                "close": 51.0,
            },
        ],
        trad_rows=[
            {
                "date": "2026-09-24",
                "stock_id": "2330",
                "observed_trade": True,
                "valid_ohlc": True,
                "buy_blocked": False,
                "sell_blocked": False,
                "reason": "OBSERVED",
            },
            {
                "date": "2026-09-24",
                "stock_id": "2317",
                "observed_trade": True,
                "valid_ohlc": True,
                "buy_blocked": False,
                "sell_blocked": False,
                "reason": "OBSERVED",
            },
        ],
    )
    market = ExecutionMarketData(source, ticker_scope={"2330"})

    decision = market.resolve(
        ticker="2330",
        session_date=date(2026, 9, 24),
        side="buy",
        use=PriceUse.ENTRY,
        field="open",
    )
    outside = market.resolve(
        ticker="2317",
        session_date=date(2026, 9, 24),
        side="buy",
        use=PriceUse.ENTRY,
        field="open",
    )

    assert decision.availability is ExecutionAvailability.EXECUTABLE
    assert outside.availability is ExecutionAvailability.NOT_EXECUTABLE


def test_stop_fill_uses_raw_open_on_gap_down(tmp_path):
    source = _write_source(
        tmp_path,
        raw_rows=[{
            "date": "2026-09-24",
            "stock_id": "2330",
            "open": 90.0,
            "max": 95.0,
            "min": 88.0,
            "close": 92.0,
        }],
        trad_rows=[{
            "date": "2026-09-24",
            "stock_id": "2330",
            "observed_trade": True,
            "valid_ohlc": True,
            "buy_blocked": False,
            "sell_blocked": False,
            "reason": "OBSERVED",
        }],
    )
    market = ExecutionMarketData(source)

    decision = market.resolve_stop_fill(
        ticker="2330",
        session_date=date(2026, 9, 24),
        stop_price=95.0,
    )

    assert decision.availability is ExecutionAvailability.EXECUTABLE
    assert decision.use is PriceUse.STOP_FILL
    assert decision.price == 90.0


def test_stop_fill_uses_stop_level_when_touched_intraday(tmp_path):
    source = _write_source(
        tmp_path,
        raw_rows=[{
            "date": "2026-09-24",
            "stock_id": "2330",
            "open": 100.0,
            "max": 102.0,
            "min": 94.0,
            "close": 98.0,
        }],
        trad_rows=[{
            "date": "2026-09-24",
            "stock_id": "2330",
            "observed_trade": True,
            "valid_ohlc": True,
            "buy_blocked": False,
            "sell_blocked": False,
            "reason": "OBSERVED",
        }],
    )
    market = ExecutionMarketData(source)

    decision = market.resolve_stop_fill(
        ticker="2330",
        session_date=date(2026, 9, 24),
        stop_price=95.0,
    )

    assert decision.availability is ExecutionAvailability.EXECUTABLE
    assert decision.price == 95.0


def test_stop_fill_not_triggered_returns_not_executable(tmp_path):
    source = _write_source(
        tmp_path,
        raw_rows=[{
            "date": "2026-09-24",
            "stock_id": "2330",
            "open": 100.0,
            "max": 105.0,
            "min": 96.0,
            "close": 102.0,
        }],
        trad_rows=[{
            "date": "2026-09-24",
            "stock_id": "2330",
            "observed_trade": True,
            "valid_ohlc": True,
            "buy_blocked": False,
            "sell_blocked": False,
            "reason": "OBSERVED",
        }],
    )
    market = ExecutionMarketData(source)

    decision = market.resolve_stop_fill(
        ticker="2330",
        session_date=date(2026, 9, 24),
        stop_price=95.0,
    )

    assert decision.availability is ExecutionAvailability.NOT_EXECUTABLE
    assert decision.reason == "STOP_NOT_TRIGGERED"
    assert decision.price is None


def test_stop_fill_respects_sell_block(tmp_path):
    source = _write_source(
        tmp_path,
        raw_rows=[{
            "date": "2026-09-24",
            "stock_id": "2330",
            "open": 90.0,
            "max": 95.0,
            "min": 88.0,
            "close": 92.0,
        }],
        trad_rows=[{
            "date": "2026-09-24",
            "stock_id": "2330",
            "observed_trade": True,
            "valid_ohlc": True,
            "buy_blocked": False,
            "sell_blocked": True,
            "reason": "SELL_BLOCKED",
        }],
    )
    market = ExecutionMarketData(source)

    decision = market.resolve_stop_fill(
        ticker="2330",
        session_date=date(2026, 9, 24),
        stop_price=95.0,
    )

    assert decision.availability is ExecutionAvailability.NOT_EXECUTABLE
    assert decision.reason == "SELL_BLOCKED"
