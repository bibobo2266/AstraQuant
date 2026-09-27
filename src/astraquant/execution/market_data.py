from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

import pandas as pd

from astraquant.data.market_coordinates import (
    PriceCoordinate,
    PriceUse,
    require_price_coordinate,
)
from astraquant.data.source_adapter import SourceDataAdapter


class ExecutionAvailability(str, Enum):
    EXECUTABLE = "EXECUTABLE"
    NOT_EXECUTABLE = "NOT_EXECUTABLE"


@dataclass(frozen=True)
class RawExecutionBar:
    ticker: str
    session_date: date
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class TradabilityState:
    ticker: str
    session_date: date
    observed_trade: bool
    valid_ohlc: bool
    buy_blocked: bool
    sell_blocked: bool
    reason: str


@dataclass(frozen=True)
class ExecutionPriceDecision:
    availability: ExecutionAvailability
    use: PriceUse
    side: str
    field: str
    price: float | None
    reason: str
    bar: RawExecutionBar | None
    tradability: TradabilityState | None


class ExecutionMarketData:
    """Read execution prices from RAW only and enforce tradability.

    There is deliberately no adjusted-data fallback. Missing RAW or missing
    tradability at an intended fill returns NOT_EXECUTABLE.
    """

    def __init__(self, source: SourceDataAdapter) -> None:
        self.source = source
        self._raw_cache: dict[int, pd.DataFrame] = {}
        self._tradability_cache: pd.DataFrame | None = None

    @staticmethod
    def _normalize_day(value: date | datetime | pd.Timestamp) -> pd.Timestamp:
        return pd.Timestamp(value).normalize()

    @staticmethod
    def _index_market_frame(df: pd.DataFrame) -> pd.DataFrame:
        indexed = df.copy()
        indexed["_date_key"] = pd.to_datetime(
            indexed["date"], errors="coerce"
        ).dt.normalize()
        indexed["_stock_key"] = indexed["stock_id"].astype(str)
        return indexed.set_index(["_date_key", "_stock_key"], drop=False).sort_index()

    @staticmethod
    def _unique_indexed_row(
        df: pd.DataFrame,
        *,
        day: pd.Timestamp,
        ticker: str,
    ) -> pd.Series | None:
        try:
            hit = df.loc[(day, str(ticker))]
        except KeyError:
            return None
        if isinstance(hit, pd.DataFrame):
            return None
        return hit

    def _raw_row(self, ticker: str, session_date: date | datetime | pd.Timestamp) -> pd.Series | None:
        day = self._normalize_day(session_date)
        rel = f"raw/prices_raw_{day.year}.parquet"
        if not self.source.exists(rel):
            return None
        if day.year not in self._raw_cache:
            self._raw_cache[day.year] = self._index_market_frame(
                self.source.read_parquet(
                    rel,
                    columns=["date", "stock_id", "open", "max", "min", "close"],
                )
            )
        return self._unique_indexed_row(
            self._raw_cache[day.year],
            day=day,
            ticker=str(ticker),
        )

    def _tradability_row(
        self,
        ticker: str,
        session_date: date | datetime | pd.Timestamp,
    ) -> pd.Series | None:
        rel = "reference/tradability.parquet"
        if not self.source.exists(rel):
            return None
        if self._tradability_cache is None:
            self._tradability_cache = self._index_market_frame(
                self.source.read_parquet(
                    rel,
                    columns=[
                        "date",
                        "stock_id",
                        "observed_trade",
                        "valid_ohlc",
                        "buy_blocked",
                        "sell_blocked",
                        "reason",
                    ],
                )
            )
        day = self._normalize_day(session_date)
        return self._unique_indexed_row(
            self._tradability_cache,
            day=day,
            ticker=str(ticker),
        )

    @staticmethod
    def _bar_from_row(ticker: str, session_date: pd.Timestamp, row: pd.Series) -> RawExecutionBar | None:
        values = {
            "open": pd.to_numeric(pd.Series([row["open"]]), errors="coerce").iloc[0],
            "high": pd.to_numeric(pd.Series([row["max"]]), errors="coerce").iloc[0],
            "low": pd.to_numeric(pd.Series([row["min"]]), errors="coerce").iloc[0],
            "close": pd.to_numeric(pd.Series([row["close"]]), errors="coerce").iloc[0],
        }
        if any(pd.isna(v) or float(v) <= 0 for v in values.values()):
            return None
        if values["high"] < max(values["open"], values["close"], values["low"]):
            return None
        if values["low"] > min(values["open"], values["close"], values["high"]):
            return None
        return RawExecutionBar(
            ticker=str(ticker),
            session_date=session_date.date(),
            open=float(values["open"]),
            high=float(values["high"]),
            low=float(values["low"]),
            close=float(values["close"]),
        )

    @staticmethod
    def _tradability_from_row(
        ticker: str,
        session_date: pd.Timestamp,
        row: pd.Series,
    ) -> TradabilityState:
        return TradabilityState(
            ticker=str(ticker),
            session_date=session_date.date(),
            observed_trade=bool(row["observed_trade"]),
            valid_ohlc=bool(row["valid_ohlc"]),
            buy_blocked=bool(row["buy_blocked"]),
            sell_blocked=bool(row["sell_blocked"]),
            reason=str(row["reason"]),
        )

    def resolve(
        self,
        *,
        ticker: str,
        session_date: date | datetime | pd.Timestamp,
        side: str,
        use: PriceUse,
        field: str,
    ) -> ExecutionPriceDecision:
        require_price_coordinate(use=use, coordinate=PriceCoordinate.RAW_EXECUTION)

        side_norm = side.lower()
        if side_norm not in {"buy", "sell"}:
            raise ValueError(f"unsupported side: {side}")
        if field not in {"open", "high", "low", "close"}:
            raise ValueError(f"unsupported RAW price field: {field}")

        day = self._normalize_day(session_date)
        raw_row = self._raw_row(ticker, day)
        if raw_row is None:
            return ExecutionPriceDecision(
                availability=ExecutionAvailability.NOT_EXECUTABLE,
                use=use,
                side=side_norm,
                field=field,
                price=None,
                reason="RAW_MISSING_OR_NONUNIQUE",
                bar=None,
                tradability=None,
            )

        bar = self._bar_from_row(str(ticker), day, raw_row)
        if bar is None:
            return ExecutionPriceDecision(
                availability=ExecutionAvailability.NOT_EXECUTABLE,
                use=use,
                side=side_norm,
                field=field,
                price=None,
                reason="RAW_INVALID_OHLC",
                bar=None,
                tradability=None,
            )

        trad_row = self._tradability_row(ticker, day)
        if trad_row is None:
            return ExecutionPriceDecision(
                availability=ExecutionAvailability.NOT_EXECUTABLE,
                use=use,
                side=side_norm,
                field=field,
                price=None,
                reason="TRADABILITY_MISSING_OR_NONUNIQUE",
                bar=bar,
                tradability=None,
            )

        trad = self._tradability_from_row(str(ticker), day, trad_row)
        if not trad.observed_trade or not trad.valid_ohlc:
            return ExecutionPriceDecision(
                availability=ExecutionAvailability.NOT_EXECUTABLE,
                use=use,
                side=side_norm,
                field=field,
                price=None,
                reason=trad.reason or "NOT_TRADABLE",
                bar=bar,
                tradability=trad,
            )

        block_sensitive_uses = {
            PriceUse.ENTRY,
            PriceUse.STOP_FILL,
            PriceUse.EXIT,
            PriceUse.SIZING,
        }
        if use in block_sensitive_uses:
            blocked = trad.buy_blocked if side_norm == "buy" else trad.sell_blocked
            if blocked:
                return ExecutionPriceDecision(
                    availability=ExecutionAvailability.NOT_EXECUTABLE,
                    use=use,
                    side=side_norm,
                    field=field,
                    price=None,
                    reason=trad.reason or f"{side_norm.upper()}_BLOCKED",
                    bar=bar,
                    tradability=trad,
                )

        return ExecutionPriceDecision(
            availability=ExecutionAvailability.EXECUTABLE,
            use=use,
            side=side_norm,
            field=field,
            price=float(getattr(bar, field)),
            reason="OK",
            bar=bar,
            tradability=trad,
        )
