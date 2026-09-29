#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from astraquant.data.corporate_actions import build_finmind_normalized_actions
from astraquant.portfolio.corporate_actions import CashEntitlementBasis, CorporateActionType
from astraquant.portfolio.historical_runner import HistoricalCorporateActionInstruction
from astraquant.portfolio.policy import PortfolioPolicyConfig
from astraquant.research.contact_registry import ContactRecord, append_contact_record
from astraquant.research.epoch_governance import (
    EpochGovernanceError,
    purge_path_windows,
    resolve_historical_effect_period,
)
from astraquant.research.parameter_sweep import ResearchParameterSweepRunner
from astraquant.research.path_diagnostics import (
    OrderState,
    PathDirection,
    PathStatus,
    PriceLimitObservation,
    RawBar,
    WINDOW_SESSIONS,
    WindowDiagnostic,
    evaluate_ca_aware_unit_path,
)
from astraquant.research.signal_engine import SignalContext
from astraquant.research.universe_engine import UniverseContext

from source_config_sweep import (
    EXPECTED_ELIGIBLE_TICKERS,
    EXPECTED_EXCLUSIONS_SHA256,
    _load_exclusions,
    _research_panel,
)
from source_eligible_universe_ca_coverage import eligible_turnover_universe
from source_strategy_integration_smoke import build_supported_ca


SWEEP_PATH = Path(
    os.environ.get(
        "SWEEP_PATH",
        "configs/research/observations/bollinger_daily_surface.yaml",
    )
)
REPORT_PATH = Path(
    os.environ.get("REPORT_PATH", "docs/SOURCE_PATH_DIAGNOSTIC.md")
)
CSV_PATH = Path(
    os.environ.get("CSV_PATH", "docs/SOURCE_PATH_DIAGNOSTIC.csv")
)
CONTACT_REGISTRY_PATH = Path(
    os.environ.get("CONTACT_REGISTRY_PATH", "docs/CONTACT_REGISTRY.md")
)
SOURCE_ROOT = Path(
    os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")
).resolve()
SOURCE_REVISION = os.environ.get("SOURCE_REVISION", "source-checkout")
RESEARCH_EPOCH = os.environ.get("RESEARCH_EPOCH", "E1").strip().upper()
OUTCOME_DIRECTION = os.environ.get("OUTCOME_DIRECTION", "LONG").strip().upper()
if OUTCOME_DIRECTION not in {"LONG", "SHORT"}:
    raise SystemExit("OUTCOME_DIRECTION must be LONG or SHORT")
DIRECTION = PathDirection(OUTCOME_DIRECTION)

try:
    EFFECT_PERIOD = resolve_historical_effect_period(RESEARCH_EPOCH)
except EpochGovernanceError as exc:
    raise SystemExit(f"BLOCKED: {exc}") from exc
assert EFFECT_PERIOD.end is not None
PERIOD_START = pd.Timestamp(EFFECT_PERIOD.start)
PERIOD_END = pd.Timestamp(EFFECT_PERIOD.end)


def _parameter_columns(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    params = frame["parameters"].map(json.loads)
    keys = sorted({k for item in params for k in item})
    out = frame.copy()
    for key in keys:
        out[key] = params.map(lambda d, k=key: d.get(k))
    return out


def _load_raw(period_start: pd.Timestamp, period_end: pd.Timestamp) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for year in range(period_start.year - 1, period_end.year + 1):
        path = SOURCE_ROOT / "raw" / f"prices_raw_{year}.parquet"
        if not path.exists():
            continue
        part = pd.read_parquet(
            path,
            columns=[
                "date",
                "stock_id",
                "open",
                "max",
                "min",
                "close",
                "Trading_Volume",
            ],
        )
        part["date"] = pd.to_datetime(part["date"], errors="coerce").dt.normalize()
        part["stock_id"] = part["stock_id"].astype(str)
        part = part.rename(columns={"max": "high", "min": "low"})
        for col in ["open", "high", "low", "close", "Trading_Volume"]:
            part[col] = pd.to_numeric(part[col], errors="coerce")
        parts.append(part)
    if not parts:
        raise SystemExit("BLOCKED: no RAW source files for path diagnostic")
    raw = pd.concat(parts, ignore_index=True)
    if raw.duplicated(["date", "stock_id"]).any():
        raise SystemExit("BLOCKED: duplicate RAW logical keys in path diagnostic source")
    return raw


def _find_col(
    columns: list[str],
    aliases: tuple[str, ...],
    tokens: tuple[str, ...],
) -> str | None:
    lowered = {str(c).lower(): str(c) for c in columns}
    for alias in aliases:
        if alias.lower() in lowered:
            return lowered[alias.lower()]
    for col in columns:
        lc = str(col).lower()
        if all(token.lower() in lc for token in tokens):
            return str(col)
    return None


def _normalize_price_limit_frame(
    frame: pd.DataFrame,
    source_name: str,
) -> pd.DataFrame:
    cols = [str(c) for c in frame.columns]
    date_col = _find_col(cols, ("date", "trading_date"), ("date",))
    ticker_col = _find_col(
        cols,
        ("stock_id", "ticker", "security_id"),
        ("stock", "id"),
    )
    upper_col = _find_col(
        cols,
        (
            "limit_up",
            "up_limit",
            "upper_limit",
            "limit_up_price",
            "up_limit_price",
            "upper_limit_price",
            "max_price",
            "漲停價",
        ),
        ("up", "limit"),
    )
    lower_col = _find_col(
        cols,
        (
            "limit_down",
            "down_limit",
            "lower_limit",
            "limit_down_price",
            "down_limit_price",
            "lower_limit_price",
            "min_price",
            "跌停價",
        ),
        ("down", "limit"),
    )
    no_limit_col = _find_col(
        cols,
        (
            "no_limit",
            "no_price_limit",
            "unlimited",
            "is_unlimited",
            "is_no_limit",
            "無漲跌幅限制",
        ),
        ("no", "limit"),
    )
    note_col = _find_col(
        cols,
        ("status", "reason", "note", "remark", "limit_type"),
        ("status",),
    )
    print(
        "PRICE_LIMIT_SCHEMA "
        f"source={source_name} columns={cols} "
        f"date={date_col} ticker={ticker_col} upper={upper_col} "
        f"lower={lower_col} no_limit={no_limit_col} note={note_col}"
    )
    if date_col is None or ticker_col is None:
        return pd.DataFrame(
            columns=["date", "stock_id", "upper", "lower", "no_limit", "known"]
        )
    out = pd.DataFrame(
        {
            "date": pd.to_datetime(
                frame[date_col],
                errors="coerce",
            ).dt.normalize(),
            "stock_id": frame[ticker_col].astype(str),
        }
    )
    out["upper"] = (
        pd.to_numeric(frame[upper_col], errors="coerce")
        if upper_col is not None
        else np.nan
    )
    out["lower"] = (
        pd.to_numeric(frame[lower_col], errors="coerce")
        if lower_col is not None
        else np.nan
    )
    if no_limit_col is not None:
        raw_no_limit = frame[no_limit_col]
        if pd.api.types.is_bool_dtype(raw_no_limit):
            out["no_limit"] = raw_no_limit.fillna(False).astype(bool)
        else:
            out["no_limit"] = (
                raw_no_limit.astype(str).str.strip().str.lower().isin(
                    {
                        "1",
                        "true",
                        "yes",
                        "y",
                        "no_limit",
                        "unlimited",
                        "無漲跌幅限制",
                    }
                )
            )
    elif note_col is not None:
        note = frame[note_col].astype(str)
        out["no_limit"] = note.str.contains(
            r"no[_ -]?limit|unlimited|無漲跌幅|無價格限制",
            case=False,
            regex=True,
            na=False,
        )
    else:
        out["no_limit"] = False
    out["known"] = (
        out["no_limit"]
        | (
            out["upper"].notna()
            & out["lower"].notna()
            & out["upper"].gt(0)
            & out["lower"].gt(0)
            & out["upper"].ge(out["lower"])
        )
    )
    out = out.dropna(subset=["date", "stock_id"])
    if out.duplicated(["date", "stock_id"]).any():
        raise SystemExit(
            f"BLOCKED: duplicate price-limit logical keys in {source_name}"
        )
    return out


def _load_price_limits(
    period_start: pd.Timestamp,
    period_end: pd.Timestamp,
) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for path in sorted((SOURCE_ROOT / "reference").glob("price_limit_*.parquet")):
        try:
            year = int(path.stem.rsplit("_", 1)[-1])
        except ValueError:
            continue
        if year < period_start.year or year > period_end.year:
            continue
        frame = pd.read_parquet(path)
        normalized = _normalize_price_limit_frame(frame, path.name)
        if not normalized.empty:
            parts.append(normalized)
    if not parts:
        return pd.DataFrame(
            columns=["date", "stock_id", "upper", "lower", "no_limit", "known"]
        )
    return pd.concat(parts, ignore_index=True)


def _late_normalized_ca_days(
    candidate_tickers: set[str],
    period_start: pd.Timestamp,
    period_end: pd.Timestamp,
) -> dict[str, frozenset[pd.Timestamp]]:
    dividend_path = SOURCE_ROOT / "fundamentals" / "dividend.parquet"
    if not dividend_path.exists():
        return {}
    normalized = build_finmind_normalized_actions(
        pd.read_parquet(dividend_path)
    )
    out: dict[str, set[pd.Timestamp]] = defaultdict(set)
    for action in normalized:
        day = pd.Timestamp(action.effective_date).normalize()
        if (
            action.ticker in candidate_tickers
            and period_start <= day <= period_end
            and action.known_at is not None
            and action.known_at.date() > action.effective_date
        ):
            out[str(action.ticker)].add(day)
    return {
        ticker: frozenset(days)
        for ticker, days in out.items()
    }


def _event_maps(
    instructions: list[HistoricalCorporateActionInstruction],
):
    open_by_day: dict[
        pd.Timestamp,
        list[HistoricalCorporateActionInstruction],
    ] = defaultdict(list)
    close_by_day: dict[
        pd.Timestamp,
        list[HistoricalCorporateActionInstruction],
    ] = defaultdict(list)
    regular_by_ticker: dict[
        str,
        dict[pd.Timestamp, list[HistoricalCorporateActionInstruction]],
    ] = defaultdict(lambda: defaultdict(list))
    special_ranges: dict[
        str,
        list[tuple[pd.Timestamp, pd.Timestamp]],
    ] = defaultdict(list)
    stale_windows: dict[
        str,
        tuple[pd.Timestamp, pd.Timestamp],
    ] = {}

    for item in instructions:
        day = pd.Timestamp(
            item.event.effective_at.date()
        ).normalize()
        target = close_by_day if item.apply_at_close else open_by_day
        target[day].append(item)

        ticker = str(item.event.ticker)
        special = (
            item.apply_at_close
            or item.extinguish_position
            or item.successor_ticker is not None
            or bool(item.successor_legs)
            or item.terminal_stale_from is not None
            or item.event.event_type is CorporateActionType.MERGER
            or item.cash_share_basis_mode is CashEntitlementBasis.EXPLICIT
        )
        if special:
            start = (
                pd.Timestamp(item.terminal_stale_from).normalize()
                if item.terminal_stale_from is not None
                else day
            )
            special_ranges[ticker].append((start, day))
            if item.terminal_stale_from is not None:
                stale_windows[ticker] = (start, day)
        else:
            regular_by_ticker[ticker][day].append(item)

    return (
        {d: tuple(v) for d, v in open_by_day.items()},
        {d: tuple(v) for d, v in close_by_day.items()},
        {
            ticker: {
                d: tuple(v)
                for d, v in by_day.items()
            }
            for ticker, by_day in regular_by_ticker.items()
        },
        {
            ticker: tuple(ranges)
            for ticker, ranges in special_ranges.items()
        },
        stale_windows,
    )


def _intersects_special(
    ranges: tuple[tuple[pd.Timestamp, pd.Timestamp], ...],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> bool:
    return any(
        not (end < left or start > right)
        for left, right in ranges
    )


class _SourceLookup:
    def __init__(
        self,
        *,
        raw: pd.DataFrame,
        tradability: pd.DataFrame,
        price_limits: pd.DataFrame,
        sessions: pd.DatetimeIndex,
    ) -> None:
        self.sessions = sessions
        self._raw = raw
        self._trad = tradability
        self._limits = price_limits
        self._bar_cache: dict[
            tuple[str, pd.Timestamp],
            RawBar | None,
        ] = {}
        self._limit_cache: dict[
            tuple[str, pd.Timestamp],
            PriceLimitObservation,
        ] = {}
        self._prior_cache: dict[
            tuple[str, pd.Timestamp],
            float | None,
        ] = {}
        self._ticker_raw_cache: dict[str, pd.DataFrame] = {}
        self._ticker_trad_cache: dict[str, pd.DataFrame] = {}
        self._ticker_limit_cache: dict[str, pd.DataFrame] = {}
        self._prior_series_cache: dict[str, pd.Series] = {}

    def _ticker_raw(self, ticker: str) -> pd.DataFrame:
        if ticker not in self._ticker_raw_cache:
            g = self._raw[
                self._raw["stock_id"].eq(ticker)
            ].copy()
            self._ticker_raw_cache[ticker] = (
                g.set_index("date").sort_index()
            )
        return self._ticker_raw_cache[ticker]

    def _ticker_trad(self, ticker: str) -> pd.DataFrame:
        if ticker not in self._ticker_trad_cache:
            g = self._trad[
                self._trad["stock_id"].eq(ticker)
            ].copy()
            self._ticker_trad_cache[ticker] = (
                g.set_index("date").sort_index()
            )
        return self._ticker_trad_cache[ticker]

    def _ticker_limits(self, ticker: str) -> pd.DataFrame:
        if ticker not in self._ticker_limit_cache:
            g = self._limits[
                self._limits["stock_id"].eq(ticker)
            ].copy()
            self._ticker_limit_cache[ticker] = (
                g.set_index("date").sort_index()
            )
        return self._ticker_limit_cache[ticker]

    def bar(
        self,
        ticker: str,
        day: pd.Timestamp,
    ) -> RawBar | None:
        key = (ticker, day)
        if key in self._bar_cache:
            return self._bar_cache[key]
        raw = self._ticker_raw(ticker)
        trad = self._ticker_trad(ticker)
        if day not in raw.index or day not in trad.index:
            self._bar_cache[key] = None
            return None
        rr = raw.loc[day]
        tr = trad.loc[day]
        if isinstance(rr, pd.DataFrame) or isinstance(tr, pd.DataFrame):
            raise SystemExit(
                f"BLOCKED: nonunique RAW/tradability row "
                f"{ticker} {day.date()}"
            )
        bar = RawBar(
            ticker=ticker,
            session=day,
            open=float(rr["open"]),
            high=float(rr["high"]),
            low=float(rr["low"]),
            close=float(rr["close"]),
            observed_trade=bool(tr["observed_trade"]),
            valid_ohlc=bool(tr["valid_ohlc"]),
        )
        self._bar_cache[key] = bar
        return bar

    def limit(
        self,
        ticker: str,
        day: pd.Timestamp,
    ) -> PriceLimitObservation:
        key = (ticker, day)
        if key in self._limit_cache:
            return self._limit_cache[key]
        limits = self._ticker_limits(ticker)
        if day not in limits.index:
            result = PriceLimitObservation(known=False)
        else:
            row = limits.loc[day]
            if isinstance(row, pd.DataFrame):
                raise SystemExit(
                    f"BLOCKED: nonunique limit row "
                    f"{ticker} {day.date()}"
                )
            result = PriceLimitObservation(
                upper=(
                    None
                    if pd.isna(row["upper"])
                    else float(row["upper"])
                ),
                lower=(
                    None
                    if pd.isna(row["lower"])
                    else float(row["lower"])
                ),
                no_limit=bool(row["no_limit"]),
                known=bool(row["known"]),
            )
        self._limit_cache[key] = result
        return result

    def prior_valid_close(
        self,
        ticker: str,
        day: pd.Timestamp,
    ) -> float | None:
        key = (ticker, day)
        if key in self._prior_cache:
            return self._prior_cache[key]
        if ticker not in self._prior_series_cache:
            raw = self._ticker_raw(ticker).reindex(self.sessions)
            trad = self._ticker_trad(ticker).reindex(self.sessions)
            close = pd.to_numeric(
                raw["close"],
                errors="coerce",
            )
            valid = (
                trad["observed_trade"]
                .fillna(False)
                .astype(bool)
                & trad["valid_ohlc"]
                .fillna(False)
                .astype(bool)
                & close.gt(0)
            )
            self._prior_series_cache[ticker] = (
                close.where(valid).ffill().shift(1)
            )
        series = self._prior_series_cache[ticker]
        value = series.get(day, np.nan)
        result = None if pd.isna(value) else float(value)
        self._prior_cache[key] = result
        return result

    def bars_mapping(self):
        lookup = self

        class _Bars:
            def get(self, key, default=None):
                value = lookup.bar(
                    str(key[0]),
                    pd.Timestamp(key[1]).normalize(),
                )
                return default if value is None else value

        return _Bars()

    def limits_mapping(self):
        lookup = self

        class _Limits:
            def get(self, key, default=None):
                return lookup.limit(
                    str(key[0]),
                    pd.Timestamp(key[1]).normalize(),
                )

        return _Limits()

    def prior_mapping(self):
        lookup = self

        class _Prior:
            def get(self, key, default=None):
                value = lookup.prior_valid_close(
                    str(key[0]),
                    pd.Timestamp(key[1]).normalize(),
                )
                return default if value is None else value

        return _Prior()


def _ticker_arrays(
    *,
    ticker: str,
    sessions: pd.DatetimeIndex,
    raw_index: pd.DataFrame,
    trad_index: pd.DataFrame,
    limit_index: pd.DataFrame,
    regular_events: dict[
        pd.Timestamp,
        tuple[HistoricalCorporateActionInstruction, ...],
    ],
) -> dict[str, np.ndarray]:
    try:
        raw = raw_index.xs(
            ticker,
            level="stock_id",
        ).reindex(sessions)
    except KeyError:
        raw = pd.DataFrame(
            index=sessions,
            columns=["open", "high", "low", "close"],
        )
    try:
        trad = trad_index.xs(
            ticker,
            level="stock_id",
        ).reindex(sessions)
    except KeyError:
        trad = pd.DataFrame(
            index=sessions,
            columns=["observed_trade", "valid_ohlc"],
        )
    try:
        limits = limit_index.xs(
            ticker,
            level="stock_id",
        ).reindex(sessions)
    except KeyError:
        limits = pd.DataFrame(
            index=sessions,
            columns=["upper", "lower", "no_limit", "known"],
        )

    open_px = pd.to_numeric(
        raw["open"],
        errors="coerce",
    ).to_numpy(dtype=float)
    high = pd.to_numeric(
        raw["high"],
        errors="coerce",
    ).to_numpy(dtype=float)
    low = pd.to_numeric(
        raw["low"],
        errors="coerce",
    ).to_numpy(dtype=float)
    close = pd.to_numeric(
        raw["close"],
        errors="coerce",
    ).to_numpy(dtype=float)
    observed = (
        trad["observed_trade"]
        .fillna(False)
        .astype(bool)
        .to_numpy()
    )
    valid_ohlc = (
        trad["valid_ohlc"]
        .fillna(False)
        .astype(bool)
        .to_numpy()
    )
    valid = (
        observed
        & valid_ohlc
        & np.isfinite(open_px)
        & np.isfinite(high)
        & np.isfinite(low)
        & np.isfinite(close)
        & (open_px > 0)
        & (high > 0)
        & (low > 0)
        & (close > 0)
        & (high >= np.maximum.reduce([open_px, close, low]))
        & (low <= np.minimum.reduce([open_px, close, high]))
    )

    q = 1.0
    cash = 0.0
    q_series = np.ones(len(sessions), dtype=float)
    c_series = np.zeros(len(sessions), dtype=float)
    for i, day in enumerate(sessions):
        for item in regular_events.get(day, ()):
            event = item.event
            if event.cash_per_share is not None:
                cash += q * float(event.cash_per_share)
            if event.share_multiplier is not None:
                q *= float(event.share_multiplier)
        q_series[i] = q
        c_series[i] = cash

    upper = pd.to_numeric(
        limits["upper"],
        errors="coerce",
    ).to_numpy(dtype=float)
    lower = pd.to_numeric(
        limits["lower"],
        errors="coerce",
    ).to_numpy(dtype=float)
    no_limit = (
        limits["no_limit"]
        .fillna(False)
        .astype(bool)
        .to_numpy()
    )
    limit_known = (
        limits["known"]
        .fillna(False)
        .astype(bool)
        .to_numpy()
    )

    return {
        "open": open_px,
        "high": high,
        "low": low,
        "close": close,
        "valid": valid,
        "q": q_series,
        "cash": c_series,
        "upper": upper,
        "lower": lower,
        "no_limit": no_limit,
        "limit_known": limit_known,
    }


def _vector_window_metrics(
    arrays: dict[str, np.ndarray],
    window: int,
    direction: PathDirection,
) -> dict[str, np.ndarray]:
    n = len(arrays["open"])
    count = max(0, n - window)
    if count == 0:
        return {
            "raw_mfe": np.array([], dtype=float),
            "raw_mae": np.array([], dtype=float),
            "days_to_mfe": np.array([], dtype=int),
            "days_to_mae": np.array([], dtype=int),
            "valid": np.array([], dtype=bool),
        }

    entry = np.arange(1, n - window + 1)
    h_value = (
        arrays["q"] * arrays["high"]
        + arrays["cash"]
    )
    l_value = (
        arrays["q"] * arrays["low"]
        + arrays["cash"]
    )
    h_windows = np.lib.stride_tricks.sliding_window_view(
        h_value,
        window,
    )[1:]
    l_windows = np.lib.stride_tricks.sliding_window_view(
        l_value,
        window,
    )[1:]
    valid_windows = np.lib.stride_tricks.sliding_window_view(
        arrays["valid"],
        window,
    )[1:]
    valid = (
        arrays["valid"][entry]
        & valid_windows.all(axis=1)
        & np.isfinite(arrays["q"][entry])
        & (arrays["q"][entry] > 0)
    )
    denom = arrays["q"][entry] * arrays["open"][entry]
    c_entry = arrays["cash"][entry]
    max_idx = np.argmax(h_windows, axis=1)
    min_idx = np.argmin(l_windows, axis=1)
    max_value = (
        np.max(h_windows, axis=1) - c_entry
    ) / denom
    min_value = (
        np.min(l_windows, axis=1) - c_entry
    ) / denom
    if direction is PathDirection.LONG:
        raw_mfe = max_value - 1.0
        raw_mae = min_value - 1.0
        days_to_mfe = max_idx + 1
        days_to_mae = min_idx + 1
    else:
        raw_mfe = 1.0 - min_value
        raw_mae = 1.0 - max_value
        days_to_mfe = min_idx + 1
        days_to_mae = max_idx + 1
    raw_mfe = np.where(valid, raw_mfe, np.nan)
    raw_mae = np.where(valid, raw_mae, np.nan)
    return {
        "raw_mfe": raw_mfe,
        "raw_mae": raw_mae,
        "days_to_mfe": days_to_mfe.astype(int),
        "days_to_mae": days_to_mae.astype(int),
        "valid": valid,
    }


def _limit_counts_from_arrays(
    arrays: dict[str, np.ndarray],
    *,
    entry_index: int,
    window: int,
) -> dict[str, int]:
    sl = slice(entry_index, entry_index + window)
    known = arrays["limit_known"][sl]
    no_limit = arrays["no_limit"][sl]
    valid = arrays["valid"][sl]
    upper = arrays["upper"][sl]
    lower = arrays["lower"][sl]
    high = arrays["high"][sl]
    low = arrays["low"][sl]
    close = arrays["close"][sl]
    open_px = arrays["open"][sl]

    def eq(left, right):
        return np.isclose(
            left,
            right,
            rtol=0.0,
            atol=1e-9,
        )

    active_known = known & ~no_limit
    all_one = (
        valid
        & eq(open_px, high)
        & eq(open_px, low)
        & eq(open_px, close)
    )
    at_either = (
        eq(open_px, upper)
        | eq(open_px, lower)
    )
    return {
        "limit_touch_up_days": int(
            (valid & active_known & eq(high, upper)).sum()
        ),
        "limit_touch_down_days": int(
            (valid & active_known & eq(low, lower)).sum()
        ),
        "limit_close_up_days": int(
            (valid & active_known & eq(close, upper)).sum()
        ),
        "limit_close_down_days": int(
            (valid & active_known & eq(close, lower)).sum()
        ),
        "all_trade_at_limit_days": int(
            (active_known & all_one & at_either).sum()
        ),
        "no_price_limit_days": int(no_limit.sum()),
        "limit_price_unknown_days": int(
            (~known & ~no_limit).sum()
        ),
    }


def _diagnostic_from_vector(
    metrics: dict[str, np.ndarray],
    arrays: dict[str, np.ndarray],
    *,
    signal_index: int,
    window: int,
) -> WindowDiagnostic:
    if signal_index >= len(metrics["raw_mfe"]):
        return WindowDiagnostic(
            window,
            PathStatus.TRUNCATED_SOURCE_CALENDAR,
        )
    entry = signal_index + 1
    if not arrays["valid"][entry]:
        return WindowDiagnostic(
            window,
            PathStatus.NO_VALID_ENTRY_REF,
        )
    if not metrics["valid"][signal_index]:
        return WindowDiagnostic(
            window,
            PathStatus.MISSING_PATH_PRICE,
            unresolved_reason="MISSING_OR_INVALID_RAW_PATH_PRICE",
        )
    d_mfe = int(metrics["days_to_mfe"][signal_index])
    d_mae = int(metrics["days_to_mae"][signal_index])
    if d_mfe < d_mae:
        state = OrderState.MFE_FIRST
    elif d_mae < d_mfe:
        state = OrderState.MAE_FIRST
    else:
        state = OrderState.SAME_DAY_UNKNOWN
    return WindowDiagnostic(
        window_sessions=window,
        status=PathStatus.OK,
        raw_mfe=float(metrics["raw_mfe"][signal_index]),
        raw_mae=float(metrics["raw_mae"][signal_index]),
        days_to_mfe=d_mfe,
        days_to_mae=d_mae,
        order_state=state,
        **_limit_counts_from_arrays(
            arrays,
            entry_index=entry,
            window=window,
        ),
    )


def _special_diagnostic(
    *,
    ticker: str,
    signal_index: int,
    window: int,
    sessions: pd.DatetimeIndex,
    arrays: dict[str, np.ndarray],
    lookup: _SourceLookup,
    open_events_by_day,
    close_events_by_day,
    stale_windows,
    unsupported_event_days,
) -> WindowDiagnostic:
    entry = signal_index + 1
    if entry >= len(sessions):
        return WindowDiagnostic(
            window,
            PathStatus.TRUNCATED_SOURCE_CALENDAR,
        )
    if not arrays["valid"][entry]:
        return WindowDiagnostic(
            window,
            PathStatus.NO_VALID_ENTRY_REF,
        )
    window_days = sessions[
        entry : entry + window
    ]
    if len(window_days) != window:
        return WindowDiagnostic(
            window,
            PathStatus.TRUNCATED_SOURCE_CALENDAR,
        )
    return evaluate_ca_aware_unit_path(
        sessions=window_days,
        entry_ticker=ticker,
        entry_ref=float(arrays["open"][entry]),
        direction=DIRECTION,
        bars=lookup.bars_mapping(),
        price_limits=lookup.limits_mapping(),
        open_events_by_day=open_events_by_day,
        close_events_by_day=close_events_by_day,
        terminal_stale_windows=stale_windows,
        prior_valid_close=lookup.prior_mapping(),
        unsupported_event_days=unsupported_event_days,
    )


def _aggregate_row(
    *,
    run_name: str,
    universe: str,
    parameters: dict[str, object],
    signals: pd.DataFrame,
    window: int,
    candidate_metrics: dict[
        tuple[str, pd.Timestamp, int],
        dict[str, object],
    ],
    sessions: pd.DatetimeIndex,
) -> dict[str, object]:
    purge = purge_path_windows(
        signals.rename(
            columns={"signal_date": "date"}
        ),
        trading_sessions=sessions,
        period_start=EFFECT_PERIOD.start,
        period_end=EFFECT_PERIOD.end,
        window_sessions=window,
        signal_date_col="date",
    )
    rows: list[dict[str, object]] = []
    for row in signals.itertuples(index=False):
        key = (
            str(row.stock_id),
            pd.Timestamp(row.signal_date).normalize(),
            window,
        )
        metric = candidate_metrics.get(key)
        if metric is None:
            metric = {
                "status": PathStatus.TRUNCATED_SOURCE_CALENDAR.value,
                "terminal_event": False,
            }
        rows.append(metric)
    frame = pd.DataFrame(rows)
    candidate_count = len(signals)

    def count_status(status: PathStatus) -> int:
        if frame.empty or "status" not in frame:
            return 0
        return int(
            frame["status"].eq(status.value).sum()
        )

    if frame.empty:
        ok = pd.DataFrame()
    else:
        ok = frame[
            frame["status"].eq(PathStatus.OK.value)
        ].copy()
    if ok.empty:
        calculable = pd.DataFrame()
    else:
        calculable = ok[
            pd.to_numeric(
                ok["demeaned_mfe"],
                errors="coerce",
            ).notna()
            & pd.to_numeric(
                ok["demeaned_mae"],
                errors="coerce",
            ).notna()
        ].copy()

    def median(col: str) -> float:
        if calculable.empty or col not in calculable:
            return float("nan")
        values = pd.to_numeric(
            calculable[col],
            errors="coerce",
        ).dropna()
        return (
            float(values.median())
            if len(values)
            else float("nan")
        )

    order = (
        calculable["order_state"]
        if not calculable.empty
        else pd.Series(dtype=str)
    )
    ratios = (
        pd.to_numeric(
            calculable["mfe_to_abs_mae"],
            errors="coerce",
        )
        if not calculable.empty
        else pd.Series(dtype=float)
    )
    unresolved = Counter(
        str(x)
        for x in (
            frame["unresolved_reason"].dropna()
            if not frame.empty
            and "unresolved_reason" in frame
            else []
        )
        if str(x).strip()
    )
    unresolved_text = ";".join(
        (
            f"{reason}={count} "
            f"({count / candidate_count:.6f})"
        )
        for reason, count in sorted(unresolved.items())
    ) if candidate_count else ""

    def total(col: str) -> int:
        if calculable.empty or col not in calculable:
            return 0
        return int(
            pd.to_numeric(
                calculable[col],
                errors="coerce",
            ).fillna(0).sum()
        )

    denom = len(calculable)
    terminal_count = (
        int(
            frame["terminal_event"]
            .fillna(False)
            .astype(bool)
            .sum()
        )
        if not frame.empty
        and "terminal_event" in frame
        else 0
    )
    result = {
        "run_name": run_name,
        "universe": universe,
        "parameters": json.dumps(
            parameters,
            ensure_ascii=False,
            sort_keys=True,
        ),
        "window_sessions": window,
        "candidates": candidate_count,
        "calculable": denom,
        "unique_tickers": int(
            signals["stock_id"]
            .astype(str)
            .nunique()
        ),
        "unique_signal_dates": int(
            pd.to_datetime(
                signals["signal_date"]
            ).nunique()
        ),
        "truncated": count_status(
            PathStatus.TRUNCATED_SOURCE_CALENDAR
        ),
        "missing_data": (
            count_status(PathStatus.MISSING_PATH_PRICE)
            + count_status(PathStatus.UNSUPPORTED_CA_EVENT)
            + count_status(
                PathStatus.INSUFFICIENT_DEMEAN_CROSS_SECTION
            )
        ),
        "terminal_event_candidates": terminal_count,
        "no_valid_entry_ref": count_status(
            PathStatus.NO_VALID_ENTRY_REF
        ),
        "multi_leg_intraday_unresolved": count_status(
            PathStatus.MULTI_LEG_INTRADAY_UNRESOLVED
        ),
        "cross_boundary_excluded": int(
            purge.cross_boundary_count
        ),
        "unresolved_reasons": unresolved_text,
        "limit_touch_up_days_total": total(
            "limit_touch_up_days"
        ),
        "limit_touch_down_days_total": total(
            "limit_touch_down_days"
        ),
        "limit_close_up_days_total": total(
            "limit_close_up_days"
        ),
        "limit_close_down_days_total": total(
            "limit_close_down_days"
        ),
        "all_trade_at_limit_days_total": total(
            "all_trade_at_limit_days"
        ),
        "no_price_limit_days_total": total(
            "no_price_limit_days"
        ),
        "limit_price_unknown_days_total": total(
            "limit_price_unknown_days"
        ),
        "demeaned_mfe_median": median(
            "demeaned_mfe"
        ),
        "demeaned_mae_median": median(
            "demeaned_mae"
        ),
        "days_to_mfe_median": median(
            "days_to_mfe"
        ),
        "days_to_mae_median": median(
            "days_to_mae"
        ),
        "order_mfe_first_share": (
            float(
                order.eq(
                    OrderState.MFE_FIRST.value
                ).mean()
            )
            if denom
            else float("nan")
        ),
        "order_mae_first_share": (
            float(
                order.eq(
                    OrderState.MAE_FIRST.value
                ).mean()
            )
            if denom
            else float("nan")
        ),
        "order_same_day_unknown_share": (
            float(
                order.eq(
                    OrderState.SAME_DAY_UNKNOWN.value
                ).mean()
            )
            if denom
            else float("nan")
        ),
        "raw_mfe_gt_5pct_share": (
            float(
                pd.to_numeric(
                    calculable["raw_mfe"],
                    errors="coerce",
                ).gt(0.05).mean()
            )
            if denom
            else float("nan")
        ),
        "raw_mfe_gt_10pct_share": (
            float(
                pd.to_numeric(
                    calculable["raw_mfe"],
                    errors="coerce",
                ).gt(0.10).mean()
            )
            if denom
            else float("nan")
        ),
        "raw_mfe_gt_20pct_share": (
            float(
                pd.to_numeric(
                    calculable["raw_mfe"],
                    errors="coerce",
                ).gt(0.20).mean()
            )
            if denom
            else float("nan")
        ),
        "raw_mfe_to_abs_mae_median": (
            float(ratios.dropna().median())
            if ratios.notna().any()
            else float("nan")
        ),
        "raw_mae_zero_ratio_undefined_share": (
            float(
                pd.to_numeric(
                    calculable["raw_mae"],
                    errors="coerce",
                ).eq(0).mean()
            )
            if denom
            else float("nan")
        ),
    }
    return result


def main() -> None:
    exclusions = _load_exclusions()
    panel, adjusted, tradability = _research_panel()

    eligible = eligible_turnover_universe(
        adjusted,
        tradability,
    )
    eligible_count = int(
        eligible["stock_id"]
        .astype(str)
        .nunique()
    )
    if eligible_count != EXPECTED_ELIGIBLE_TICKERS:
        raise SystemExit(
            "BLOCKED: frozen eligible-universe ticker count changed "
            f"(expected {EXPECTED_ELIGIBLE_TICKERS}, got {eligible_count})"
        )

    exclusions_path = Path(
        os.environ.get(
            "EXCLUSIONS_PATH",
            "docs/SOURCE_CA_PIT_EXCLUSIONS.csv",
        )
    )
    source_hash = hashlib.sha256(
        exclusions_path.read_bytes()
    ).hexdigest()
    if source_hash != EXPECTED_EXCLUSIONS_SHA256:
        raise SystemExit(
            "BLOCKED: frozen P2-060 exclusion ledger hash changed"
        )

    theme_root = Path(
        os.environ.get("THEME_ROOT", "themes")
    ).resolve()
    runner = ResearchParameterSweepRunner()
    stream = runner.stream_sweep(
        sweep_config_path=SWEEP_PATH,
        root=Path("."),
        panel=panel,
        universe_context=UniverseContext(
            p2_060_excluded_tickers=frozenset(exclusions),
            p2_060_exclusion_sha256=EXPECTED_EXCLUSIONS_SHA256,
            theme_root=(
                theme_root
                if theme_root.exists()
                else None
            ),
        ),
        signal_context=SignalContext(
            source_revision=SOURCE_REVISION
        ),
        base_policy=PortfolioPolicyConfig(
            position_fraction=0.10,
            max_positions=10,
            stop_fraction=0.12,
            max_hold_sessions=250,
        ),
    )

    run_candidates: list[
        tuple[
            str,
            str,
            dict[str, object],
            pd.DataFrame,
        ]
    ] = []
    candidate_parts: list[pd.DataFrame] = []
    for item in stream.runs:
        run = item.prepared
        signals = run.signal_frame[
            run.signal_frame["counts_as_candidate"]
            & run.signal_frame["signal_date"].between(
                PERIOD_START,
                PERIOD_END,
                inclusive="both",
            )
        ][["signal_date", "stock_id"]].copy()
        signals["signal_date"] = pd.to_datetime(
            signals["signal_date"]
        ).dt.normalize()
        signals["stock_id"] = (
            signals["stock_id"].astype(str)
        )
        if signals.duplicated(
            ["signal_date", "stock_id"]
        ).any():
            raise SystemExit(
                "BLOCKED: duplicate candidate key in run "
                f"{run.run_config.run_name}"
            )
        compact = signals.reset_index(drop=True)
        run_candidates.append(
            (
                run.run_config.run_name,
                item.universe,
                dict(item.parameters),
                compact,
            )
        )
        candidate_parts.append(compact)

    if not run_candidates:
        raise SystemExit(
            "FAIL: sweep produced no configurations"
        )

    candidate_union = (
        pd.concat(
            candidate_parts,
            ignore_index=True,
        )
        .drop_duplicates(
            ["signal_date", "stock_id"]
        )
        .reset_index(drop=True)
    )
    candidate_dates_by_ticker: dict[
        str,
        set[pd.Timestamp],
    ] = defaultdict(set)
    for row in candidate_union.itertuples(
        index=False
    ):
        candidate_dates_by_ticker[
            str(row.stock_id)
        ].add(
            pd.Timestamp(
                row.signal_date
            ).normalize()
        )

    sessions = pd.DatetimeIndex(
        sorted(
            pd.to_datetime(
                adjusted["date"],
                errors="coerce",
            )
            .dropna()
            .dt.normalize()
            .unique()
        )
    )
    session_pos = {
        pd.Timestamp(day): i
        for i, day in enumerate(sessions)
    }

    raw = _load_raw(
        PERIOD_START,
        PERIOD_END,
    )
    trad = tradability[
        [
            "date",
            "stock_id",
            "observed_trade",
            "valid_ohlc",
        ]
    ].copy()
    trad["date"] = pd.to_datetime(
        trad["date"],
        errors="coerce",
    ).dt.normalize()
    trad["stock_id"] = trad["stock_id"].astype(str)

    raw_index = (
        raw.set_index(
            ["stock_id", "date"]
        ).sort_index()
    )
    trad_index = (
        trad.set_index(
            ["stock_id", "date"]
        ).sort_index()
    )
    price_limits = _load_price_limits(
        PERIOD_START,
        PERIOD_END,
    )
    if price_limits.empty:
        limit_index = pd.DataFrame(
            columns=[
                "upper",
                "lower",
                "no_limit",
                "known",
            ],
            index=pd.MultiIndex.from_arrays(
                [[], []],
                names=["stock_id", "date"],
            ),
        )
    else:
        limit_index = (
            price_limits.set_index(
                ["stock_id", "date"]
            ).sort_index()
        )

    mother = panel[
        panel["date"].between(
            PERIOD_START,
            PERIOD_END,
            inclusive="both",
        )
        & panel["stock_id"]
        .astype(str)
        .str.fullmatch(
            r"[1-9]\d{3}",
            na=False,
        )
        & ~panel["stock_id"]
        .astype(str)
        .isin(exclusions)
        & panel["observed_trade"]
        .fillna(False)
        .astype(bool)
        & panel["valid_ohlc"]
        .fillna(False)
        .astype(bool)
    ][["date", "stock_id"]].copy()
    mother["date"] = pd.to_datetime(
        mother["date"]
    ).dt.normalize()
    mother["stock_id"] = mother[
        "stock_id"
    ].astype(str)
    mother_dates_by_ticker: dict[
        str,
        set[pd.Timestamp],
    ] = defaultdict(set)
    for row in mother.itertuples(index=False):
        mother_dates_by_ticker[
            str(row.stock_id)
        ].add(
            pd.Timestamp(row.date).normalize()
        )

    event_scope = (
        set(mother_dates_by_ticker)
        | set(candidate_dates_by_ticker)
    )
    ca_scope = set(event_scope)
    (
        ca_instructions,
        unsupported_ca_source_rows,
        unsupported_ca_summary,
    ) = build_supported_ca(
        candidate_tickers=ca_scope,
        sessions=set(
            sessions[
                (sessions >= PERIOD_START)
                & (sessions <= PERIOD_END)
            ]
        ),
    )
    (
        open_events_by_day,
        close_events_by_day,
        regular_by_ticker,
        special_ranges,
        stale_windows,
    ) = _event_maps(ca_instructions)

    unsupported_event_days = (
        _late_normalized_ca_days(
            event_scope,
            PERIOD_START,
            PERIOD_END,
        )
    )
    for ticker, days in (
        unsupported_event_days.items()
    ):
        ranges = list(
            special_ranges.get(ticker, ())
        )
        ranges.extend(
            (day, day)
            for day in days
        )
        special_ranges[ticker] = tuple(ranges)

    lookup = _SourceLookup(
        raw=raw,
        tradability=trad,
        price_limits=price_limits,
        sessions=sessions,
    )

    sums_mfe = {
        w: np.zeros(
            len(sessions),
            dtype=float,
        )
        for w in WINDOW_SESSIONS
    }
    sums_mae = {
        w: np.zeros(
            len(sessions),
            dtype=float,
        )
        for w in WINDOW_SESSIONS
    }
    counts = {
        w: np.zeros(
            len(sessions),
            dtype=int,
        )
        for w in WINDOW_SESSIONS
    }
    candidate_metrics: dict[
        tuple[str, pd.Timestamp, int],
        dict[str, object],
    ] = {}

    all_tickers = sorted(
        set(mother_dates_by_ticker)
        | set(candidate_dates_by_ticker)
    )
    for ticker in all_tickers:
        arrays = _ticker_arrays(
            ticker=ticker,
            sessions=sessions,
            raw_index=raw_index,
            trad_index=trad_index,
            limit_index=limit_index,
            regular_events=regular_by_ticker.get(
                ticker,
                {},
            ),
        )
        vector = {
            w: _vector_window_metrics(
                arrays,
                w,
                DIRECTION,
            )
            for w in WINDOW_SESSIONS
        }
        special_for_ticker = (
            special_ranges.get(
                ticker,
                (),
            )
        )
        support_dates = mother_dates_by_ticker.get(
            ticker,
            set(),
        )
        candidate_dates = (
            candidate_dates_by_ticker.get(
                ticker,
                set(),
            )
        )

        for window in WINDOW_SESSIONS:
            metrics = vector[window]

            for signal_day in support_dates:
                signal_idx = session_pos.get(
                    signal_day
                )
                if signal_idx is None:
                    continue
                if signal_idx + window >= len(sessions):
                    continue
                endpoint = sessions[
                    signal_idx + window
                ]
                if endpoint > PERIOD_END:
                    continue
                entry_day = sessions[
                    signal_idx + 1
                ]
                use_special = _intersects_special(
                    special_for_ticker,
                    entry_day,
                    endpoint,
                )
                if use_special:
                    diag = _special_diagnostic(
                        ticker=ticker,
                        signal_index=signal_idx,
                        window=window,
                        sessions=sessions,
                        arrays=arrays,
                        lookup=lookup,
                        open_events_by_day=open_events_by_day,
                        close_events_by_day=close_events_by_day,
                        stale_windows=stale_windows,
                        unsupported_event_days=unsupported_event_days,
                    )
                    if diag.status is PathStatus.OK:
                        sums_mfe[window][
                            signal_idx
                        ] += float(diag.raw_mfe)
                        sums_mae[window][
                            signal_idx
                        ] += float(diag.raw_mae)
                        counts[window][
                            signal_idx
                        ] += 1
                elif (
                    signal_idx
                    < len(metrics["valid"])
                    and bool(
                        metrics["valid"][
                            signal_idx
                        ]
                    )
                ):
                    sums_mfe[window][
                        signal_idx
                    ] += float(
                        metrics["raw_mfe"][
                            signal_idx
                        ]
                    )
                    sums_mae[window][
                        signal_idx
                    ] += float(
                        metrics["raw_mae"][
                            signal_idx
                        ]
                    )
                    counts[window][
                        signal_idx
                    ] += 1

            for signal_day in candidate_dates:
                signal_idx = session_pos.get(
                    signal_day
                )
                key = (
                    ticker,
                    signal_day,
                    window,
                )
                if (
                    signal_idx is None
                    or signal_idx + window
                    >= len(sessions)
                ):
                    diag = WindowDiagnostic(
                        window,
                        PathStatus.TRUNCATED_SOURCE_CALENDAR,
                    )
                else:
                    endpoint = sessions[
                        signal_idx + window
                    ]
                    if endpoint > PERIOD_END:
                        diag = WindowDiagnostic(
                            window,
                            PathStatus.CROSS_EPOCH,
                        )
                    else:
                        entry_day = sessions[
                            signal_idx + 1
                        ]
                        if _intersects_special(
                            special_for_ticker,
                            entry_day,
                            endpoint,
                        ):
                            diag = _special_diagnostic(
                                ticker=ticker,
                                signal_index=signal_idx,
                                window=window,
                                sessions=sessions,
                                arrays=arrays,
                                lookup=lookup,
                                open_events_by_day=open_events_by_day,
                                close_events_by_day=close_events_by_day,
                                stale_windows=stale_windows,
                                unsupported_event_days=unsupported_event_days,
                            )
                        else:
                            diag = (
                                _diagnostic_from_vector(
                                    metrics,
                                    arrays,
                                    signal_index=signal_idx,
                                    window=window,
                                )
                            )
                candidate_metrics[key] = {
                    **asdict(diag),
                    "status": diag.status.value,
                    "order_state": (
                        None
                        if diag.order_state is None
                        else diag.order_state.value
                    ),
                }

    daily_means: dict[
        int,
        tuple[
            np.ndarray,
            np.ndarray,
            np.ndarray,
        ],
    ] = {}
    for window in WINDOW_SESSIONS:
        valid_cross = (
            counts[window] >= 200
        )
        mean_mfe = np.full(
            len(sessions),
            np.nan,
            dtype=float,
        )
        mean_mae = np.full(
            len(sessions),
            np.nan,
            dtype=float,
        )
        mean_mfe[valid_cross] = (
            sums_mfe[window][valid_cross]
            / counts[window][valid_cross]
        )
        mean_mae[valid_cross] = (
            sums_mae[window][valid_cross]
            / counts[window][valid_cross]
        )
        daily_means[window] = (
            mean_mfe,
            mean_mae,
            counts[window],
        )

    for (
        ticker,
        signal_day,
        window,
    ), metric in candidate_metrics.items():
        if (
            metric["status"]
            != PathStatus.OK.value
        ):
            continue
        signal_idx = session_pos[signal_day]
        (
            mean_mfe,
            mean_mae,
            cross_count,
        ) = daily_means[window]
        if cross_count[signal_idx] < 200:
            metric["status"] = (
                PathStatus
                .INSUFFICIENT_DEMEAN_CROSS_SECTION
                .value
            )
            metric["unresolved_reason"] = (
                "DEMEAN_CROSS_SECTION_LT_200"
            )
            continue
        metric["demeaned_mfe"] = (
            float(metric["raw_mfe"])
            - float(mean_mfe[signal_idx])
        )
        metric["demeaned_mae"] = (
            float(metric["raw_mae"])
            - float(mean_mae[signal_idx])
        )
        raw_mae = float(metric["raw_mae"])
        metric["mfe_to_abs_mae"] = (
            float(metric["raw_mfe"])
            / abs(raw_mae)
            if raw_mae != 0
            else float("nan")
        )
        metric[
            "demean_cross_section_count"
        ] = int(cross_count[signal_idx])

    result_rows: list[
        dict[str, object]
    ] = []
    for (
        run_name,
        universe,
        parameters,
        signals,
    ) in run_candidates:
        for window in WINDOW_SESSIONS:
            result_rows.append(
                _aggregate_row(
                    run_name=run_name,
                    universe=universe,
                    parameters=parameters,
                    signals=signals,
                    window=window,
                    candidate_metrics=candidate_metrics,
                    sessions=sessions,
                )
            )

    results = _parameter_columns(
        pd.DataFrame(result_rows)
    )
    CSV_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    results.to_csv(
        CSV_PATH,
        index=False,
    )

    limit_years = sorted(
        {
            int(
                path.stem.rsplit(
                    "_",
                    1,
                )[-1]
            )
            for path in (
                SOURCE_ROOT / "reference"
            ).glob(
                "price_limit_*.parquet"
            )
            if path.stem.rsplit(
                "_",
                1,
            )[-1].isdigit()
        }
    )
    lines = [
        "# Candidate Path Diagnostics",
        "",
        "Status: **PASS**",
        "",
        "## 定位與時期",
        "",
        f"- epoch: {EFFECT_PERIOD.label}",
        "- 本報告只做路徑診斷；MFE / MAE / order_state / days_to_MFE / days_to_MAE 不取代完整交易績效，也不得單獨判定訊號有效或無效。",
        "- E1 為預設；E2 僅能以 RESEARCH_EPOCH=E2 顯式啟用；E3 由治理層阻擋。",
        "- 本報告是候選層，不套用部位上限與資金限制；候選數不等於可執行交易數，資金受限結果另行報告。",
        f"- direction: {DIRECTION.value}",
        "- windows: 5 / 10 / 20 common trading sessions; entry day is day 1.",
        "- entry_ref: signal date next common trading session RAW open; no valid open => NO_VALID_ENTRY_REF; no delay and no skip-forward.",
        "- path value V_t uses one initial unit with canonical cash/share/successor/terminal corporate-action semantics.",
        "- multi-successor intraday extrema are not summed; they are MULTI_LEG_INTRADAY_UNRESOLVED.",
        "",
        "## 方向定義",
        "",
        "- LONG: favorable = V_t^high - 1; adverse = V_t^low - 1.",
        "- SHORT (Anchor-DOWN): favorable = 1 - V_t^low; adverse = 1 - V_t^high.",
        "- MFE is maximum favorable deviation; MAE is minimum adverse deviation.",
        "- repeated cross-day extrema use the first day; same-day MFE/MAE is SAME_DAY_UNKNOWN because daily OHLC cannot establish intraday order.",
        "",
        "## 去均值",
        "",
        "- Demean mother is all same-day four-digit P2-060 common-support names with observed_trade and valid_ohlc, not the triggered signal set.",
        "- MFE and MAE are demeaned separately; a date requires at least 200 calculable mother names for that window.",
        "- SHORT uses the same short-direction transformation for the mother before demeaning.",
        "",
        "## 漲跌停口徑",
        "",
        "- Uses source price-limit records when an explicit daily upper/lower limit or explicit no-limit state is available.",
        "- No previous-close fixed-multiplier fallback is used. Missing source limit information is counted as limit-price-unknown.",
        (
            "- source price-limit file years present: "
            + (
                ",".join(
                    map(str, limit_years)
                )
                if limit_years
                else "none"
            )
        ),
        "- Touch flags are market-constraint diagnostics only; touch does not mean locked and daily OHLC cannot establish fillability at the extreme.",
        "",
        "## 不可計算與跨界",
        "",
        "- Each 5/10/20 window is purged independently. A window crossing the epoch boundary is counted and excluded; it is never shortened.",
        "- Suspended/no-price sessions remain calendar days. Existing terminal stale-mark semantics are used only inside an explicitly modeled terminal stale window; otherwise missing RAW path value is reported, not filled.",
        (
            "- build_supported_ca unsupported source rows observed: "
            f"{unsupported_ca_source_rows}; "
            f"event summary: {unsupported_ca_summary}"
        ),
        "",
        "## 參數組合 × 窗口輸出",
        "",
        f"- machine-readable table: {CSV_PATH.as_posix()}",
        f"- rows: {len(results):,}",
        "- columns include candidate/calculable/unique counts, truncation/missing/terminal/NO_VALID_ENTRY_REF/multi-leg/cross-boundary counts, all requested price-limit strata, demeaned MFE/MAE medians, days-to-extrema medians, three order_state shares, raw MFE threshold shares, and the auxiliary raw MFE / |raw MAE| median plus undefined share.",
        "",
        "## 比值限制",
        "",
        "每筆原始 MFE / |原始 MAE| 僅為輔助描述；原始 MAE = 0 時保持未定義，不代入任意小數。此比值不是交易賠率，也不能推出每筆期望值，因為最大有利與最大不利偏離不是可同時實現的一筆交易結果。",
        "",
        "## 待驗證解釋清單",
        "",
        "- 若後續對齊完整交易後觀察到 MFE 明顯高於實際獲利，待驗證：出場過早、出場過晚後回吐、執行價與極值價差異、極值當下不可成交（鎖停或無量）。",
        "- 若後續對齊完整交易後觀察到 MAE 淺但遭停損掃出，待驗證：停損過緊、停損採用的價格基準與診斷不同、盤中觸價與收盤價差異。",
        "- 若極值集中於窗口末端，只標示邊界效應提示；不自動主張延長窗口，也不據此選擇最佳窗口。",
        "- 上述均為待驗證解釋，不是成因判定。",
    ]
    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    REPORT_PATH.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    append_contact_record(
        CONTACT_REGISTRY_PATH,
        ContactRecord(
            result_id=REPORT_PATH.stem,
            covered_period=(
                f"{PERIOD_START.date()} "
                f"~ {PERIOD_END.date()}"
            ),
            contact_date=datetime.now(
                ZoneInfo("Asia/Taipei")
            ).date(),
            context=(
                "candidate path diagnostics; "
                f"epoch={EFFECT_PERIOD.epoch.value}; "
                f"direction={DIRECTION.value}; "
                "windows=5/10/20; "
                f"source_revision={SOURCE_REVISION}"
            ),
        ),
    )


if __name__ == "__main__":
    main()
