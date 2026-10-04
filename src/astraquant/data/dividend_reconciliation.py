from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from typing import Iterable

import numpy as np
import pandas as pd

from astraquant.data.corporate_actions import (
    build_finmind_normalized_actions,
    normalized_actions_frame,
)


TRANSFORM_VERSION = "ca_dividend_component_reconciliation_v1"
FINMIND_UNIT_SEMANTICS = "NTD_PER_PRE_EVENT_SHARE"
TPEX_STOCK_UNIT_SEMANTICS = "SHARES_PER_1000_PRE_EVENT_SHARES"
CASH_UNIT_SEMANTICS = "NTD_PER_PRE_EVENT_SHARE"


class AnnouncementPrecision(str, Enum):
    EXACT_TIMESTAMP = "EXACT_TIMESTAMP"
    DATE_ONLY = "DATE_ONLY"
    PARSE_FAILED = "PARSE_FAILED"
    MISSING = "MISSING"


class PrimaryClass(str, Enum):
    COMPONENT_VALUE_CONSISTENT = "COMPONENT_VALUE_CONSISTENT"
    SAME_DATE_COMPONENT_MISSING = "SAME_DATE_COMPONENT_MISSING"
    VALUE_OR_UNIT_CONFLICT = "VALUE_OR_UNIT_CONFLICT"
    DATE_DIFFERENCE_EXPLAINED = "DATE_DIFFERENCE_EXPLAINED"
    DUPLICATE_REVISION_CANCEL = "DUPLICATE_REVISION_CANCEL"
    OUTSIDE_NORMALIZER_SCOPE = "OUTSIDE_NORMALIZER_SCOPE"
    GENUINE_SOURCE_EVENT_MISSING = "GENUINE_SOURCE_EVENT_MISSING"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class ReconciliationInputs:
    source_revision: str
    dividend_blob_sha: str
    official_blob_sha: str
    acquired_at: str


def _text(value: object) -> str:
    return "" if pd.isna(value) else str(value).strip()


def _num(value: object) -> float | None:
    out = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(out) else float(out)


def _component_sum(raw: pd.Series, first: str, second: str, fallback: str) -> float | None:
    values = []
    for name in (first, second):
        value = _num(raw.get(name))
        if value is not None:
            values.append(value)
    if values:
        return float(sum(values))
    return _num(raw.get(fallback))


def _date(value: object) -> pd.Timestamp | pd.NaT:
    out = pd.to_datetime(value, errors="coerce")
    return pd.NaT if pd.isna(out) else pd.Timestamp(out).normalize()


def _stable_id(prefix: str, *parts: object) -> str:
    raw = "\x1f".join(_text(x) for x in parts)
    return f"{prefix}:{sha256(raw.encode('utf-8')).hexdigest()[:24]}"


def announcement_precision(row: pd.Series) -> tuple[AnnouncementPrecision, pd.Timestamp | pd.NaT]:
    raw_date = _text(row.get("AnnouncementDate"))
    raw_time = _text(row.get("AnnouncementTime"))
    if raw_date and raw_time:
        ts = pd.to_datetime(f"{raw_date} {raw_time}", errors="coerce")
        if pd.notna(ts):
            return AnnouncementPrecision.EXACT_TIMESTAMP, pd.Timestamp(ts)
        return AnnouncementPrecision.PARSE_FAILED, pd.NaT
    if raw_date:
        ts = pd.to_datetime(raw_date, errors="coerce")
        if pd.notna(ts):
            return AnnouncementPrecision.DATE_ONLY, pd.Timestamp(ts).normalize()
        return AnnouncementPrecision.PARSE_FAILED, pd.NaT
    if raw_time:
        return AnnouncementPrecision.PARSE_FAILED, pd.NaT
    return AnnouncementPrecision.MISSING, pd.NaT


def finmind_source_rows(
    dividend: pd.DataFrame,
    *,
    source_revision: str,
    dividend_blob_sha: str,
) -> pd.DataFrame:
    """Preserve frozen FinMind rows and their source-specific semantics.

    The input repository already de-duplicates dividend rows by (stock_id, date)
    with keep-last semantics.  Therefore this function records current-state row
    identity but never claims that revision/cancellation history is absent.
    """

    rows: list[dict[str, object]] = []
    for source_row, row in dividend.reset_index(drop=True).iterrows():
        precision, parsed_announcement = announcement_precision(row)
        sid = _text(row.get("stock_id"))
        stable = _stable_id(
            "finmind-row",
            source_revision,
            dividend_blob_sha,
            source_row,
            sid,
            row.get("date"),
            row.get("CashExDividendTradingDate"),
            row.get("StockExDividendTradingDate"),
            row.get("CashEarningsDistribution"),
            row.get("CashStatutorySurplus"),
            row.get("StockEarningsDistribution"),
            row.get("StockStatutorySurplus"),
        )
        rows.append(
            {
                "source_row_id": stable,
                "source_row_number": int(source_row),
                "stock_id": sid,
                "security_type": "FOUR_DIGIT_COMMON_OR_OTHER"
                if pd.Series([sid]).str.fullmatch(r"[1-9]\d{3}", na=False).iloc[0]
                else "OUTSIDE_FOUR_DIGIT_RESEARCH_BASE",
                "source_name": "FinMind TaiwanStockDividend",
                "source_revision": source_revision,
                "source_blob_sha": dividend_blob_sha,
                "source_record_date": _date(row.get("date")),
                "cash_effective_date": _date(row.get("CashExDividendTradingDate")),
                "stock_effective_date": _date(row.get("StockExDividendTradingDate")),
                "cash_earnings": _num(row.get("CashEarningsDistribution")),
                "cash_statutory": _num(row.get("CashStatutorySurplus")),
                "cash_fallback": _num(row.get("CashDividend")),
                "stock_earnings": _num(row.get("StockEarningsDistribution")),
                "stock_statutory": _num(row.get("StockStatutorySurplus")),
                "stock_fallback": _num(row.get("StockDividend")),
                "announcement_date_raw": _text(row.get("AnnouncementDate")),
                "announcement_time_raw": _text(row.get("AnnouncementTime")),
                "announcement_precision": precision.value,
                "announcement_at": parsed_announcement,
                "available_date_raw": _text(row.get("available_date")),
                "revision_history_retained": False,
                "revision_history_note": "frozen builder de-duplicates stock_id+date keep-last",
            }
        )
    return pd.DataFrame(rows)


def finmind_components(
    dividend: pd.DataFrame,
    *,
    source_revision: str,
    dividend_blob_sha: str,
) -> pd.DataFrame:
    """Map frozen FinMind rows to cash/stock economic components.

    Stock distribution fields are source-specific NTD/share semantics.
    For this source only, NT$10 stock dividend equals one additional share per
    pre-event share, so multiplier = 1 + amount/10.  This rule MUST NOT be used
    for TPEx or any other source.
    """

    raw_rows = finmind_source_rows(
        dividend,
        source_revision=source_revision,
        dividend_blob_sha=dividend_blob_sha,
    )
    normalized = normalized_actions_frame(build_finmind_normalized_actions(dividend))
    if normalized.empty:
        return pd.DataFrame()

    result: list[dict[str, object]] = []
    for r in normalized.itertuples(index=False):
        source_row = int(r.source_row)
        raw = raw_rows.loc[raw_rows["source_row_number"].eq(source_row)].iloc[0]
        kind = str(r.event_kind)
        if kind == "CASH_DIVIDEND":
            economic_value = float(r.cash_per_share)
            multiplier = np.nan
            raw_distribution_value = _component_sum(
                raw, "cash_earnings", "cash_statutory", "cash_fallback"
            )
            unit = CASH_UNIT_SEMANTICS
        elif kind == "STOCK_DIVIDEND":
            economic_value = np.nan
            multiplier = float(r.share_multiplier)
            raw_distribution_value = _component_sum(
                raw, "stock_earnings", "stock_statutory", "stock_fallback"
            )
            unit = FINMIND_UNIT_SEMANTICS
        else:
            raise ValueError(f"unsupported normalized component {kind}")

        result.append(
            {
                "component_id": _stable_id(
                    "finmind-component",
                    raw["source_row_id"],
                    kind,
                    pd.Timestamp(r.effective_date).date().isoformat(),
                ),
                "source_row_id": raw["source_row_id"],
                "stock_id": str(r.stock_id),
                "security_type": raw["security_type"],
                "component_kind": kind,
                "effective_date": pd.Timestamp(r.effective_date).normalize(),
                "cash_per_share": economic_value,
                "share_multiplier": multiplier,
                "source_distribution_value": raw_distribution_value,
                "source_unit_semantics": unit,
                "known_at": pd.Timestamp(r.known_at) if pd.notna(r.known_at) else pd.NaT,
                "announcement_precision": raw["announcement_precision"],
                "source_record_date": raw["source_record_date"],
                "date_difference_explained": bool(
                    pd.notna(raw["source_record_date"])
                    and pd.Timestamp(raw["source_record_date"]).normalize()
                    != pd.Timestamp(r.effective_date).normalize()
                ),
                "source_name": "FinMind TaiwanStockDividend",
                "source_row_number": source_row,
                "source_revision": source_revision,
                "source_blob_sha": dividend_blob_sha,
            }
        )
    return pd.DataFrame(result)


def official_rows(
    official: pd.DataFrame,
    *,
    source_revision: str,
    official_blob_sha: str,
) -> pd.DataFrame:
    required = {
        "stock_id",
        "event_date",
        "event_type",
        "cash_per_share",
        "share_multiplier",
        "rights_ratio",
        "market",
        "source_url",
        "source_name",
    }
    missing = sorted(required - set(official.columns))
    if missing:
        raise ValueError(f"official source missing columns: {missing}")

    rows: list[dict[str, object]] = []
    for source_row, row in official.reset_index(drop=True).iterrows():
        sid = _text(row.get("stock_id"))
        event_date = _date(row.get("event_date"))
        market = _text(row.get("market"))
        source_name = _text(row.get("source_name"))
        cash = _num(row.get("cash_per_share"))
        multiplier = _num(row.get("share_multiplier"))
        rights_ratio = _num(row.get("rights_ratio"))
        if source_name == "TPEx exDailyQ":
            stock_raw_unit = TPEX_STOCK_UNIT_SEMANTICS
            expected_multiplier = (
                None if rights_ratio is None else 1.0 + rights_ratio / 1000.0
            )
            economics_capability = "CASH_AND_STOCK_COMPONENTS"
        elif source_name == "TWSE TWT49U":
            stock_raw_unit = "NOT_PRESENT_IN_FROZEN_TWT49U_INGEST"
            expected_multiplier = None
            economics_capability = "EVENT_DATE_PRESENCE_ONLY"
        else:
            stock_raw_unit = "SOURCE_SPECIFIC_UNVERIFIED"
            expected_multiplier = None
            economics_capability = "UNVERIFIED_SOURCE"

        rows.append(
            {
                "official_row_id": _stable_id(
                    "official-row",
                    source_revision,
                    official_blob_sha,
                    source_row,
                    sid,
                    event_date,
                    row.get("event_type"),
                    source_name,
                ),
                "source_row_number": int(source_row),
                "stock_id": sid,
                "security_type": "FOUR_DIGIT_COMMON_OR_OTHER"
                if pd.Series([sid]).str.fullmatch(r"[1-9]\d{3}", na=False).iloc[0]
                else "OUTSIDE_FOUR_DIGIT_RESEARCH_BASE",
                "event_date": event_date,
                "event_type": _text(row.get("event_type")),
                "cash_per_share": cash,
                "share_multiplier": multiplier,
                "rights_ratio": rights_ratio,
                "market": market,
                "source_url": _text(row.get("source_url")),
                "source_name": source_name,
                "economics_capability": economics_capability,
                "cash_unit_semantics": CASH_UNIT_SEMANTICS
                if source_name == "TPEx exDailyQ"
                else "NOT_PRESENT_OR_UNVERIFIED",
                "stock_unit_semantics": stock_raw_unit,
                "expected_multiplier_from_raw_unit": expected_multiplier,
                "known_at_precision": "MISSING_IN_FROZEN_OFFICIAL_INGEST"
                if not _text(row.get("known_date"))
                else "DATE_ONLY_OR_SOURCE_UNVERIFIED",
                "revision_history_retained": False,
                "revision_history_note": "frozen builder de-duplicates stock_id+event_date+event_type+source_name keep-last",
                "source_revision": source_revision,
                "source_blob_sha": official_blob_sha,
            }
        )
    return pd.DataFrame(rows)


def _close(a: object, b: object, *, atol: float = 1e-10) -> bool:
    if pd.isna(a) or pd.isna(b):
        return False
    return bool(np.isclose(float(a), float(b), rtol=0.0, atol=atol))


def _component_summary(g: pd.DataFrame) -> dict[str, object]:
    cash = g[g["component_kind"].eq("CASH_DIVIDEND")]
    stock = g[g["component_kind"].eq("STOCK_DIVIDEND")]
    return {
        "normalized_cash_present": bool(len(cash)),
        "normalized_stock_present": bool(len(stock)),
        "normalized_cash_per_share": (
            float(cash.iloc[0]["cash_per_share"]) if len(cash) == 1 else np.nan
        ),
        "normalized_share_multiplier": (
            float(stock.iloc[0]["share_multiplier"]) if len(stock) == 1 else np.nan
        ),
        "normalized_cash_count": int(len(cash)),
        "normalized_stock_count": int(len(stock)),
        "normalized_component_ids": ";".join(sorted(g["component_id"].astype(str))),
        "normalized_source_row_ids": ";".join(sorted(set(g["source_row_id"].astype(str)))),
        "announcement_precision_set": ";".join(
            sorted(set(g["announcement_precision"].astype(str)))
        ),
        "date_difference_explained": bool(g["date_difference_explained"].any()),
    }


def reconcile_dividend_components(
    dividend: pd.DataFrame,
    official: pd.DataFrame,
    *,
    inputs: ReconciliationInputs,
    start: str = "2015-01-01",
    end: str = "2021-12-31",
    research_tickers: Iterable[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return event reconciliation, FinMind raw-row mapping and component mapping.

    The primary counting unit is one (stock_id, effective/event date) economic
    event group.  Primary classes are mutually exclusive.  Independent issue
    flags remain separate and can overlap.
    """

    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    raw = finmind_source_rows(
        dividend,
        source_revision=inputs.source_revision,
        dividend_blob_sha=inputs.dividend_blob_sha,
    )
    comp = finmind_components(
        dividend,
        source_revision=inputs.source_revision,
        dividend_blob_sha=inputs.dividend_blob_sha,
    )
    off = official_rows(
        official,
        source_revision=inputs.source_revision,
        official_blob_sha=inputs.official_blob_sha,
    )

    if not comp.empty:
        comp = comp[comp["effective_date"].between(start_ts, end_ts)].copy()
    off = off[
        off["event_type"].eq("ex_right_dividend")
        & off["event_date"].between(start_ts, end_ts)
    ].copy()

    research_set = None if research_tickers is None else {str(x) for x in research_tickers}
    event_keys = set()
    event_keys.update(
        (str(r.stock_id), pd.Timestamp(r.effective_date).normalize())
        for r in comp.itertuples(index=False)
    )
    event_keys.update(
        (str(r.stock_id), pd.Timestamp(r.event_date).normalize())
        for r in off.itertuples(index=False)
        if pd.notna(r.event_date)
    )

    rows: list[dict[str, object]] = []
    for sid, day in sorted(event_keys, key=lambda x: (x[1], x[0])):
        cg = comp[
            comp["stock_id"].eq(sid) & comp["effective_date"].eq(day)
        ].copy()
        og = off[
            off["stock_id"].eq(sid) & off["event_date"].eq(day)
        ].copy()
        cs = _component_summary(cg) if len(cg) else {
            "normalized_cash_present": False,
            "normalized_stock_present": False,
            "normalized_cash_per_share": np.nan,
            "normalized_share_multiplier": np.nan,
            "normalized_cash_count": 0,
            "normalized_stock_count": 0,
            "normalized_component_ids": "",
            "normalized_source_row_ids": "",
            "announcement_precision_set": "",
            "date_difference_explained": False,
        }

        tpex = og[og["source_name"].eq("TPEx exDailyQ")]
        twse = og[og["source_name"].eq("TWSE TWT49U")]
        other = og[~og["source_name"].isin(["TPEx exDailyQ", "TWSE TWT49U"])]

        duplicate_current = bool(
            len(cg) > 2
            or cs["normalized_cash_count"] > 1
            or cs["normalized_stock_count"] > 1
            or len(tpex) > 1
            or len(twse) > 1
        )
        historical_revision_unknown = bool(len(cg) or len(og))

        expected_cash = False
        expected_stock = False
        official_cash = np.nan
        official_mult = np.nan
        unit_conflict = False
        value_conflict = False
        component_missing = False
        outside = False
        genuine_missing = False
        evidence_insufficient = False

        if len(tpex):
            r = tpex.iloc[0]
            official_cash = (
                float(r["cash_per_share"]) if pd.notna(r["cash_per_share"]) else np.nan
            )
            official_mult = (
                float(r["share_multiplier"]) if pd.notna(r["share_multiplier"]) else np.nan
            )
            expected_cash = bool(pd.notna(official_cash) and official_cash > 0)
            expected_stock = bool(pd.notna(official_mult) and official_mult > 1.0)
            if pd.notna(r["expected_multiplier_from_raw_unit"]) and pd.notna(official_mult):
                unit_conflict = not _close(
                    r["expected_multiplier_from_raw_unit"], official_mult
                )
            if not expected_cash and not expected_stock:
                outside = True
            elif not len(cg):
                genuine_missing = True
            else:
                if expected_cash and not cs["normalized_cash_present"]:
                    component_missing = True
                if expected_stock and not cs["normalized_stock_present"]:
                    component_missing = True
                if expected_cash and cs["normalized_cash_present"]:
                    value_conflict |= not _close(
                        official_cash, cs["normalized_cash_per_share"]
                    )
                if expected_stock and cs["normalized_stock_present"]:
                    value_conflict |= not _close(
                        official_mult, cs["normalized_share_multiplier"]
                    )
        elif len(twse):
            # Frozen TWT49U ingestion proves a market/date row, not its cash/share
            # economics. Matching a FinMind component on the date cannot certify
            # completeness or values.
            evidence_insufficient = True
        elif len(other):
            evidence_insufficient = True
        elif len(cg):
            # Bidirectional normalized-only group. The frozen official ingest is
            # not claimed complete, so absence is not upgraded to a true missing
            # official event.
            evidence_insufficient = True

        if duplicate_current:
            primary = PrimaryClass.DUPLICATE_REVISION_CANCEL
        elif outside:
            primary = PrimaryClass.OUTSIDE_NORMALIZER_SCOPE
        elif unit_conflict or value_conflict:
            primary = PrimaryClass.VALUE_OR_UNIT_CONFLICT
        elif component_missing:
            primary = PrimaryClass.SAME_DATE_COMPONENT_MISSING
        elif genuine_missing:
            primary = PrimaryClass.GENUINE_SOURCE_EVENT_MISSING
        elif evidence_insufficient:
            primary = PrimaryClass.INSUFFICIENT_EVIDENCE
        elif cs["date_difference_explained"] and not len(og):
            primary = PrimaryClass.DATE_DIFFERENCE_EXPLAINED
        else:
            primary = PrimaryClass.COMPONENT_VALUE_CONSISTENT

        rows.append(
            {
                "economic_event_id": _stable_id(
                    "economic-event",
                    inputs.source_revision,
                    sid,
                    day.date().isoformat(),
                ),
                "stock_id": sid,
                "event_date": day,
                "security_type": "FOUR_DIGIT_COMMON_OR_OTHER"
                if pd.Series([sid]).str.fullmatch(r"[1-9]\d{3}", na=False).iloc[0]
                else "OUTSIDE_FOUR_DIGIT_RESEARCH_BASE",
                "in_research_ticker_scope": (
                    pd.NA if research_set is None else sid in research_set
                ),
                "official_markets": ";".join(sorted(set(og["market"].astype(str)))),
                "official_sources": ";".join(sorted(set(og["source_name"].astype(str)))),
                "official_row_ids": ";".join(sorted(og["official_row_id"].astype(str))),
                **cs,
                "tpex_expected_cash": expected_cash,
                "tpex_expected_stock": expected_stock,
                "tpex_cash_per_share": official_cash,
                "tpex_share_multiplier": official_mult,
                "flag_component_missing": component_missing,
                "flag_value_conflict": value_conflict,
                "flag_unit_conflict": unit_conflict,
                "flag_current_duplicate": duplicate_current,
                "flag_historical_revision_cancel_unknown": historical_revision_unknown,
                "flag_official_economics_insufficient": evidence_insufficient,
                "flag_normalized_without_official": bool(len(cg) and not len(og)),
                "flag_official_without_normalized": bool(len(og) and not len(cg)),
                "primary_class": primary.value,
                "source_revision": inputs.source_revision,
                "dividend_blob_sha": inputs.dividend_blob_sha,
                "official_blob_sha": inputs.official_blob_sha,
                "transform_version": TRANSFORM_VERSION,
                "verification_acquired_at": inputs.acquired_at,
            }
        )

    events = pd.DataFrame(rows)
    if len(events):
        events["in_research_ticker_scope"] = pd.array(
            events["in_research_ticker_scope"], dtype="boolean"
        )
    return events, raw, comp


def aggregate_reconciliation(events: pd.DataFrame) -> pd.DataFrame:
    scopes: list[tuple[str, pd.Series]] = [
        ("SOURCE_ALL", pd.Series(True, index=events.index)),
        (
            "FOUR_DIGIT_RESEARCH_BASE",
            events["security_type"].eq("FOUR_DIGIT_COMMON_OR_OTHER"),
        ),
    ]
    if "in_research_ticker_scope" in events.columns and events[
        "in_research_ticker_scope"
    ].notna().any():
        scopes.append(
            (
                "ESTABLISHED_RESEARCH_TICKERS",
                events["in_research_ticker_scope"].fillna(False).astype(bool),
            )
        )

    rows: list[dict[str, object]] = []
    for scope, mask in scopes:
        g = events[mask]
        counts = g["primary_class"].value_counts()
        total = int(len(g))
        for cls in PrimaryClass:
            rows.append(
                {
                    "scope": scope,
                    "primary_class": cls.value,
                    "count": int(counts.get(cls.value, 0)),
                    "scope_total": total,
                }
            )
        if sum(r["count"] for r in rows if r["scope"] == scope) != total:
            raise AssertionError(f"primary-class conservation failed for {scope}")
    return pd.DataFrame(rows)
