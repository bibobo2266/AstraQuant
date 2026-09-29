from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd


REQUIRED_TERMINAL_EVENT_COLUMNS = (
    "ticker",
    "last_trading_date",
    "event_type",
    "suspension_from",
    "effective_date",
    "cash_per_share",
    "payment_date",
    "successor_ticker",
    "share_ratio",
    "confidence",
    "source_url",
    "source_quote",
)
ALLOWED_CONFIDENCE = {"CONFIRMED", "PARTIAL", "NOT_FOUND"}


@dataclass(frozen=True)
class TerminalEventRecord:
    ticker: str
    last_trading_date: date | None
    event_type: str
    suspension_from: date | None
    effective_date: date | None
    cash_per_share: float | None
    payment_date: date | None
    successor_ticker: str | None
    share_ratio: float | None
    confidence: str
    source_url: str
    source_quote: str

    @property
    def can_override_fallback(self) -> bool:
        return self.confidence == "CONFIRMED"


def _optional_date(value) -> date | None:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return None
    return pd.Timestamp(value).date()


def _optional_float(value) -> float | None:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return None
    out = float(value)
    if out <= 0:
        raise ValueError("terminal-event numeric economics must be positive")
    return out


def load_terminal_event_records(path: str | Path) -> tuple[TerminalEventRecord, ...]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    frame = pd.read_csv(p, dtype=str, keep_default_na=False)
    missing = set(REQUIRED_TERMINAL_EVENT_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(
            f"terminal event CSV missing columns: {sorted(missing)}"
        )

    records: list[TerminalEventRecord] = []
    for row in frame.to_dict("records"):
        ticker = str(row["ticker"]).strip()
        confidence = str(row["confidence"]).strip().upper()
        if not ticker:
            raise ValueError("terminal event ticker is required")
        if confidence not in ALLOWED_CONFIDENCE:
            raise ValueError(
                f"invalid terminal-event confidence for {ticker}: {confidence}"
            )
        successor = str(row["successor_ticker"]).strip() or None
        record = TerminalEventRecord(
            ticker=ticker,
            last_trading_date=_optional_date(row["last_trading_date"]),
            event_type=str(row["event_type"]).strip().upper(),
            suspension_from=_optional_date(row["suspension_from"]),
            effective_date=_optional_date(row["effective_date"]),
            cash_per_share=_optional_float(row["cash_per_share"]),
            payment_date=_optional_date(row["payment_date"]),
            successor_ticker=successor,
            share_ratio=_optional_float(row["share_ratio"]),
            confidence=confidence,
            source_url=str(row["source_url"]).strip(),
            source_quote=str(row["source_quote"]).strip(),
        )
        if record.can_override_fallback:
            if record.effective_date is None:
                raise ValueError(
                    f"CONFIRMED terminal event requires effective_date: {ticker}"
                )
            has_cash = record.cash_per_share is not None
            has_successor = record.successor_ticker is not None
            if has_cash == has_successor:
                raise ValueError(
                    "CONFIRMED terminal event must declare exactly one of "
                    f"cash_per_share or successor_ticker: {ticker}"
                )
            if has_successor and record.share_ratio is None:
                raise ValueError(
                    f"CONFIRMED successor event requires share_ratio: {ticker}"
                )
        records.append(record)

    confirmed = [x.ticker for x in records if x.can_override_fallback]
    if len(set(confirmed)) != len(confirmed):
        raise ValueError(
            "terminal event CSV has duplicate CONFIRMED ticker rows; "
            "multi-leg conversions require the dedicated composite model"
        )
    return tuple(records)


def confirmed_terminal_events(
    records: tuple[TerminalEventRecord, ...],
) -> dict[str, TerminalEventRecord]:
    return {
        record.ticker: record
        for record in records
        if record.can_override_fallback
    }
