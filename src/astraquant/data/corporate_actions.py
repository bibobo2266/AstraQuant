from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

import pandas as pd


class NormalizedCorporateActionError(RuntimeError):
    pass


class NormalizedCorporateActionKind(str, Enum):
    CASH_DIVIDEND = "CASH_DIVIDEND"
    STOCK_DIVIDEND = "STOCK_DIVIDEND"


@dataclass(frozen=True)
class NormalizedCorporateAction:
    ticker: str
    effective_date: date
    kind: NormalizedCorporateActionKind
    known_at: datetime | None
    payment_at: datetime | None
    cash_per_share: float | None
    share_multiplier: float | None
    source_name: str
    source_row: int
    unit_semantics: str


def _timestamp(value: object) -> pd.Timestamp | None:
    out = pd.to_datetime(value, errors="coerce")
    if pd.isna(out):
        return None
    return pd.Timestamp(out)


def _number(value: object) -> float | None:
    out = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(out) else float(out)


def _component_sum(row: pd.Series, primary: str, statutory: str, fallback: str) -> float | None:
    primary_v = _number(row.get(primary))
    statutory_v = _number(row.get(statutory))
    if primary_v is not None or statutory_v is not None:
        return (primary_v or 0.0) + (statutory_v or 0.0)
    return _number(row.get(fallback))


def _known_at(row: pd.Series) -> datetime | None:
    for col in ("available_date", "AnnouncementDate"):
        ts = _timestamp(row.get(col))
        if ts is not None:
            return ts.to_pydatetime()
    return None


def build_finmind_normalized_actions(dividend: pd.DataFrame) -> list[NormalizedCorporateAction]:
    """Normalize FinMind dividend rows without using the legacy ledger date/unit assumptions.

    Cash and stock components are emitted independently because their ex-dates are
    distinct source fields. Cash entitlement is per pre-event share. FinMind stock
    distribution fields are monetary units per share, so NT$10 of stock dividend
    corresponds to one additional share per pre-event share.
    """

    required = {
        "stock_id",
        "CashExDividendTradingDate",
        "StockExDividendTradingDate",
    }
    missing = sorted(required - set(dividend.columns))
    if missing:
        raise NormalizedCorporateActionError(f"missing required dividend columns: {missing}")

    out: list[NormalizedCorporateAction] = []
    for source_row, row in dividend.reset_index(drop=True).iterrows():
        ticker = str(row["stock_id"]).strip()
        if not ticker:
            continue

        known_at = _known_at(row)
        payment_ts = _timestamp(row.get("CashDividendPaymentDate"))
        payment_at = None if payment_ts is None else payment_ts.to_pydatetime()

        cash_per_share = _component_sum(
            row,
            "CashEarningsDistribution",
            "CashStatutorySurplus",
            "CashDividend",
        )
        cash_ex = _timestamp(row.get("CashExDividendTradingDate"))
        if cash_ex is not None and cash_per_share is not None and cash_per_share > 0:
            out.append(
                NormalizedCorporateAction(
                    ticker=ticker,
                    effective_date=cash_ex.date(),
                    kind=NormalizedCorporateActionKind.CASH_DIVIDEND,
                    known_at=known_at,
                    payment_at=payment_at,
                    cash_per_share=cash_per_share,
                    share_multiplier=None,
                    source_name="FinMind TaiwanStockDividend",
                    source_row=int(source_row),
                    unit_semantics="cash_per_pre_event_share",
                )
            )

        stock_units_per_share = _component_sum(
            row,
            "StockEarningsDistribution",
            "StockStatutorySurplus",
            "StockDividend",
        )
        stock_ex = _timestamp(row.get("StockExDividendTradingDate"))
        if stock_ex is not None and stock_units_per_share is not None and stock_units_per_share > 0:
            multiplier = 1.0 + stock_units_per_share / 10.0
            out.append(
                NormalizedCorporateAction(
                    ticker=ticker,
                    effective_date=stock_ex.date(),
                    kind=NormalizedCorporateActionKind.STOCK_DIVIDEND,
                    known_at=known_at,
                    payment_at=None,
                    cash_per_share=None,
                    share_multiplier=multiplier,
                    source_name="FinMind TaiwanStockDividend",
                    source_row=int(source_row),
                    unit_semantics="stock_dividend_currency_per_share_divided_by_10",
                )
            )

    return out


def normalized_actions_frame(actions: list[NormalizedCorporateAction]) -> pd.DataFrame:
    rows = [
        {
            "stock_id": a.ticker,
            "effective_date": pd.Timestamp(a.effective_date),
            "event_kind": a.kind.value,
            "known_at": pd.Timestamp(a.known_at) if a.known_at is not None else pd.NaT,
            "payment_at": pd.Timestamp(a.payment_at) if a.payment_at is not None else pd.NaT,
            "cash_per_share": a.cash_per_share,
            "share_multiplier": a.share_multiplier,
            "source_name": a.source_name,
            "source_row": a.source_row,
            "unit_semantics": a.unit_semantics,
        }
        for a in actions
    ]
    if not rows:
        return pd.DataFrame(
            columns=[
                "stock_id", "effective_date", "event_kind", "known_at", "payment_at",
                "cash_per_share", "share_multiplier", "source_name", "source_row",
                "unit_semantics",
            ]
        )
    return pd.DataFrame(rows).sort_values(
        ["effective_date", "stock_id", "event_kind", "source_row"]
    ).reset_index(drop=True)
