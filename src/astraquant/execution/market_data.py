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

    def __init__(
        self,
        source: SourceDataAdapter,
        *,
        ticker_scope: set[str] | None = None,
    ) -> None:
        self.source = source
        self.ticker_scope = None if ticker_scope is None else {str(x) for x in ticker_scope}
        if self.ticker_scope is not None and not self.ticker_scope:
            raise ValueError("ticker_scope must not be empty")
        self._raw_cache: dict[int, pd.DataFrame] = {}
        self._tradability_cache: pd.DataFrame | None = None
        self._available_raw_years: tuple[int, ...] | None = None

    def _ticker_filters(self) -> list[tuple[str, str, object]] | None:
        if self.ticker_scope is None:
            return None
        if len(self.ticker_scope) == 1:
            return [("stock_id", "==", next(iter(self.ticker_scope)))]
        return [("stock_id", "in", sorted(self.ticker_scope))]

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

    def _raw_years(self) -> tuple[int, ...]:
        if self._available_raw_years is None:
            years: list[int] = []
            for rel in self.source.list_files("raw", suffixes=[".parquet"]):
                stem = rel.rsplit("/", 1)[-1].rsplit(".", 1)[0]
                token = stem.rsplit("_", 1)[-1]
                if token.isdigit() and len(token) == 4:
                    years.append(int(token))
            self._available_raw_years = tuple(sorted(set(years)))
        return self._available_raw_years

    def _load_raw_year(self, year: int) -> pd.DataFrame | None:
        rel = f"raw/prices_raw_{year}.parquet"
        if not self.source.exists(rel):
            return None
        if year not in self._raw_cache:
            self._raw_cache[year] = self._index_market_frame(
                self.source.read_parquet(
                    rel,
                    columns=["date", "stock_id", "open", "max", "min", "close"],
                    filters=self._ticker_filters(),
                )
            )
        return self._raw_cache[year]

    def _latest_valid_raw_before(
        self,
        *,
        ticker: str,
        day: pd.Timestamp,
    ) -> tuple[pd.Timestamp, pd.Series] | None:
        years = [y for y in self._raw_years() if y <= day.year]
        for year in sorted(years, reverse=True):
            df = self._load_raw_year(year)
            if df is None or df.empty:
                continue
            try:
                stock = df.xs(str(ticker), level="_stock_key", drop_level=False)
            except KeyError:
                continue
            date_index = stock.index.get_level_values("_date_key")
            candidates = stock[date_index < day].sort_index(
                level="_date_key",
                ascending=False,
            )
            for idx, row in candidates.iterrows():
                source_day = pd.Timestamp(idx[0]).normalize()
                if self._bar_from_row(str(ticker), source_day, row) is not None:
                    return source_day, row
        return None

    def _raw_row(self, ticker: str, session_date: date | datetime | pd.Timestamp) -> pd.Series | None:
        day = self._normalize_day(session_date)
        df = self._load_raw_year(day.year)
        if df is None:
            return None
        return self._unique_indexed_row(
            df,
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
                    filters=self._ticker_filters(),
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


    def resolve_mark(
        self,
        *,
        ticker: str,
        session_date: date | datetime | pd.Timestamp,
        field: str = "close",
        not_before: date | datetime | pd.Timestamp | None = None,
    ) -> ExecutionPriceDecision:
        """Resolve a RAW mark with explicit stale carry for suspension gaps.

        Same-session observed RAW is preferred. If the current tradability row
        explicitly says NO_TRADE_ROW_WITHIN_ACTIVE_SPAN, valuation may carry the
        latest prior valid RAW close. This is valuation-only: fills, stops, and
        sizing never use stale prices.

        not_before is an economic-coordinate barrier. A stale observation older
        than that date is rejected so a pre-CA mark is not carried across an
        explicitly modeled corporate action.
        """

        if field not in {"open", "close"}:
            raise ValueError("MARK supports open or close requests")

        same_day = self.resolve(
            ticker=ticker,
            session_date=session_date,
            side="sell",
            use=PriceUse.MARK,
            field=field,
        )
        if same_day.availability is ExecutionAvailability.EXECUTABLE:
            return same_day

        day = self._normalize_day(session_date)
        trad_row = self._tradability_row(ticker, day)
        if trad_row is None:
            return same_day
        trad = self._tradability_from_row(str(ticker), day, trad_row)
        if trad.observed_trade or trad.reason != "NO_TRADE_ROW_WITHIN_ACTIVE_SPAN":
            return same_day

        stale = self._latest_valid_raw_before(ticker=str(ticker), day=day)
        if stale is None:
            return ExecutionPriceDecision(
                availability=ExecutionAvailability.NOT_EXECUTABLE,
                use=PriceUse.MARK,
                side="sell",
                field="stale_close",
                price=None,
                reason="STALE_RAW_MARK_UNAVAILABLE",
                bar=None,
                tradability=trad,
            )

        source_day, row = stale
        if not_before is not None:
            barrier = self._normalize_day(not_before)
            if source_day < barrier:
                return ExecutionPriceDecision(
                    availability=ExecutionAvailability.NOT_EXECUTABLE,
                    use=PriceUse.MARK,
                    side="sell",
                    field="stale_close",
                    price=None,
                    reason="STALE_RAW_MARK_BLOCKED_BY_CA",
                    bar=None,
                    tradability=trad,
                )

        bar = self._bar_from_row(str(ticker), source_day, row)
        assert bar is not None
        return ExecutionPriceDecision(
            availability=ExecutionAvailability.EXECUTABLE,
            use=PriceUse.MARK,
            side="sell",
            field="stale_close",
            price=float(bar.close),
            reason="STALE_RAW_MARK",
            bar=bar,
            tradability=trad,
        )


    def resolve_stop_fill(
        self,
        *,
        ticker: str,
        session_date: date | datetime | pd.Timestamp,
        stop_price: float,
        side: str = "sell",
    ) -> ExecutionPriceDecision:
        """Resolve a long-position stop fill from RAW OHLC.

        For a sell stop:
        - RAW low must touch/breach the stop;
        - if RAW open gaps below/equal to the stop, fill reference is RAW open;
        - otherwise fill reference is the stop level inside the observed RAW bar;
        - sell-side tradability must permit execution.

        No adjusted price participates in trigger observation or fill pricing.
        """

        if stop_price <= 0:
            raise ValueError("stop_price must be positive")
        if side.lower() != "sell":
            raise ValueError("only sell stops for long positions are currently supported")

        observation = self.resolve(
            ticker=ticker,
            session_date=session_date,
            side="sell",
            use=PriceUse.STOP_OBSERVATION,
            field="low",
        )
        if observation.availability is not ExecutionAvailability.EXECUTABLE:
            return ExecutionPriceDecision(
                availability=ExecutionAvailability.NOT_EXECUTABLE,
                use=PriceUse.STOP_FILL,
                side="sell",
                field="stop",
                price=None,
                reason=observation.reason,
                bar=observation.bar,
                tradability=observation.tradability,
            )

        assert observation.bar is not None
        if observation.bar.low > stop_price:
            return ExecutionPriceDecision(
                availability=ExecutionAvailability.NOT_EXECUTABLE,
                use=PriceUse.STOP_FILL,
                side="sell",
                field="stop",
                price=None,
                reason="STOP_NOT_TRIGGERED",
                bar=observation.bar,
                tradability=observation.tradability,
            )

        executable_open = self.resolve(
            ticker=ticker,
            session_date=session_date,
            side="sell",
            use=PriceUse.STOP_FILL,
            field="open",
        )
        if executable_open.availability is not ExecutionAvailability.EXECUTABLE:
            return ExecutionPriceDecision(
                availability=ExecutionAvailability.NOT_EXECUTABLE,
                use=PriceUse.STOP_FILL,
                side="sell",
                field="stop",
                price=None,
                reason=executable_open.reason,
                bar=executable_open.bar,
                tradability=executable_open.tradability,
            )

        assert executable_open.bar is not None
        fill_price = (
            executable_open.bar.open
            if executable_open.bar.open <= stop_price
            else stop_price
        )
        return ExecutionPriceDecision(
            availability=ExecutionAvailability.EXECUTABLE,
            use=PriceUse.STOP_FILL,
            side="sell",
            field="stop",
            price=float(fill_price),
            reason="OK",
            bar=executable_open.bar,
            tradability=executable_open.tradability,
        )
