#!/usr/bin/env python3
"""Evidence-only audit for the Layer-1 causal RAW v2 real-data gate.

This script reads the immutable source revision and emits aggregate/public
quality evidence only. It never computes strategy outcomes, returns, entries,
exits, or E2/E3 effects.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from astraquant.data.corporate_actions import (
    build_finmind_normalized_actions,
    normalized_actions_frame,
)

WARMUP_START = pd.Timestamp("2015-01-01")
E1_START = pd.Timestamp("2016-01-04")
E1_END = pd.Timestamp("2021-12-31")
SOURCE_REVISION = os.environ.get(
    "SOURCE_REVISION", "fb8b042b46dc38838d103544ca17da10286c7bfe"
)
SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "../minervini_picks/data"))
REPORT_PATH = Path(
    os.environ.get(
        "REPORT_PATH", "docs/PIT_FEATURE_LAYER1_CAUSAL_RAW_V2_GATE_EVIDENCE.md"
    )
)
SUMMARY_PATH = Path(
    os.environ.get(
        "SUMMARY_PATH", "out/layer1_causal_raw_v2_gate_evidence.csv"
    )
)
NONDIV_PATH = Path(
    os.environ.get(
        "NONDIV_PATH", "out/layer1_causal_raw_v2_nondividend_scope.csv"
    )
)
UNMATCHED_CA_PATH = Path(
    os.environ.get(
        "UNMATCHED_CA_PATH", "out/layer1_causal_raw_v2_unmatched_official_ca.csv"
    )
)
MANIFEST_PATH = Path(
    os.environ.get(
        "MANIFEST_PATH", "out/layer1_causal_raw_v2_gate_evidence_manifest.json"
    )
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def as_dt(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce")


def read_raw() -> tuple[pd.DataFrame, list[dict[str, object]], dict[str, str]]:
    parts: list[pd.DataFrame] = []
    summary: list[dict[str, object]] = []
    hashes: dict[str, str] = {}
    for year in range(2015, 2022):
        path = SOURCE_ROOT / "raw" / f"prices_raw_{year}.parquet"
        if not path.exists():
            raise SystemExit(f"missing required source: {path}")
        hashes[str(path.relative_to(SOURCE_ROOT))] = sha256(path)
        x = pd.read_parquet(path)
        required = {
            "date",
            "stock_id",
            "open",
            "max",
            "min",
            "close",
            "Trading_money",
            "source",
        }
        missing = sorted(required - set(x.columns))
        if missing:
            raise SystemExit(f"{path} missing required columns: {missing}")
        x = x.copy()
        x["date"] = as_dt(x["date"]).dt.normalize()
        x["stock_id"] = x["stock_id"].astype(str)
        x["year"] = year
        for c in ["open", "max", "min", "close", "Trading_money"]:
            x[c] = pd.to_numeric(x[c], errors="coerce")
        if x[["date", "stock_id"]].isna().any(axis=1).any():
            raise SystemExit(f"{path} has null logical keys")
        dup = int(x.duplicated(["date", "stock_id"]).sum())
        if dup:
            raise SystemExit(f"{path} has {dup} duplicate logical keys")
        parts.append(x)

        groups = x.groupby(
            [
                x.get("market", pd.Series("", index=x.index)).fillna("UNKNOWN"),
                x["source"].fillna("UNKNOWN"),
            ],
            dropna=False,
        )
        for (market, source), g in groups:
            summary.append(
                {
                    "section": "raw_source",
                    "year": year,
                    "market": str(market),
                    "source": str(source),
                    "rows": int(len(g)),
                    "distinct_tickers": int(g["stock_id"].nunique()),
                    "date_min": g["date"].min().date().isoformat(),
                    "date_max": g["date"].max().date().isoformat(),
                    "ohlc_null_rows": int(g[["open", "max", "min", "close"]].isna().any(axis=1).sum()),
                    "trading_money_null_rows": int(g["Trading_money"].isna().sum()),
                }
            )
    return pd.concat(parts, ignore_index=True), summary, hashes


def actual_calendar(raw: pd.DataFrame) -> pd.DatetimeIndex:
    dates = raw.loc[
        raw["date"].between(WARMUP_START, E1_END), "date"
    ].dropna().drop_duplicates().sort_values()
    return pd.DatetimeIndex(dates)


def first_session_on_or_after(
    date: pd.Timestamp, calendar: pd.DatetimeIndex
) -> pd.Timestamp | pd.NaT:
    pos = int(calendar.searchsorted(pd.Timestamp(date).normalize(), side="left"))
    if pos >= len(calendar):
        return pd.NaT
    return pd.Timestamp(calendar[pos]).normalize()


def next_session_after(
    date: pd.Timestamp, calendar: pd.DatetimeIndex
) -> pd.Timestamp | pd.NaT:
    pos = int(calendar.searchsorted(pd.Timestamp(date).normalize(), side="right"))
    if pos >= len(calendar):
        return pd.NaT
    return pd.Timestamp(calendar[pos]).normalize()


def affected_e1_window(
    event_date: pd.Timestamp, calendar: pd.DatetimeIndex, sessions_affected: int
) -> tuple[object, object, int]:
    start_pos = int(calendar.searchsorted(pd.Timestamp(event_date).normalize(), side="left"))
    if start_pos >= len(calendar):
        return "", "", 0
    end_pos = min(len(calendar) - 1, start_pos + sessions_affected - 1)
    dates = calendar[start_pos : end_pos + 1]
    e1 = dates[(dates >= E1_START) & (dates <= E1_END)]
    if not len(e1):
        return "", "", 0
    return (
        pd.Timestamp(e1[0]).date().isoformat(),
        pd.Timestamp(e1[-1]).date().isoformat(),
        int(len(e1)),
    )


def audit_tradability(
    raw: pd.DataFrame, hashes: dict[str, str]
) -> tuple[list[dict[str, object]], dict[str, int]]:
    path = SOURCE_ROOT / "reference" / "tradability.parquet"
    hashes[str(path.relative_to(SOURCE_ROOT))] = sha256(path)
    t = pd.read_parquet(path)
    required = {
        "date",
        "stock_id",
        "observed_trade",
        "valid_ohlc",
        "buy_blocked",
        "sell_blocked",
    }
    missing = sorted(required - set(t.columns))
    if missing:
        raise SystemExit(f"{path} missing required columns: {missing}")
    t = t.copy()
    t["date"] = as_dt(t["date"]).dt.normalize()
    t["stock_id"] = t["stock_id"].astype(str)
    t = t[t["date"].between(WARMUP_START, E1_END)].copy()
    if t.duplicated(["date", "stock_id"]).any():
        raise SystemExit("tradability has duplicate logical keys in warmup+E1")

    r = raw[
        raw["date"].between(WARMUP_START, E1_END)
        & raw["stock_id"].str.fullmatch(r"[1-9]\d{3}[A-Z]?", na=False)
    ][["date", "stock_id", "open", "max", "min", "close"]].copy()
    merged = t.merge(
        r,
        on=["date", "stock_id"],
        how="left",
        validate="one_to_one",
        indicator=True,
        suffixes=("", "_raw"),
    )
    numeric = merged[["open", "max", "min", "close"]].apply(
        pd.to_numeric, errors="coerce"
    )
    valid = (numeric > 0).all(axis=1)
    geom = numeric["max"].ge(numeric[["open", "close", "min"]].max(axis=1)) & numeric[
        "min"
    ].le(numeric[["open", "close", "max"]].min(axis=1))
    expected_valid = valid & geom
    observed = merged["observed_trade"].fillna(False).astype(bool)
    has_raw = merged["_merge"].eq("both")
    valid_mismatch = int(
        (
            has_raw
            & (
                merged["valid_ohlc"].fillna(False).astype(bool)
                != expected_valid
            )
        ).sum()
    )
    observed_without_raw = int((observed & ~has_raw).sum())
    raw_marked_unobserved = int((has_raw & ~observed).sum())

    summary: list[dict[str, object]] = []
    for year, g in t.groupby(t["date"].dt.year):
        summary.append(
            {
                "section": "tradability",
                "year": int(year),
                "rows": int(len(g)),
                "distinct_tickers": int(g["stock_id"].nunique()),
                "observed_false": int((~g["observed_trade"].fillna(False).astype(bool)).sum()),
                "valid_ohlc_false": int((~g["valid_ohlc"].fillna(False).astype(bool)).sum()),
                "buy_blocked": int(g["buy_blocked"].fillna(True).astype(bool).sum()),
                "sell_blocked": int(g["sell_blocked"].fillna(True).astype(bool).sum()),
            }
        )
    checks = {
        "tradability_rows": int(len(t)),
        "valid_ohlc_reconstruction_mismatches": valid_mismatch,
        "observed_trade_true_without_raw_key": observed_without_raw,
        "raw_key_marked_observed_false": raw_marked_unobserved,
        "derived_missing_rows": int((~observed).sum()),
    }
    return summary, checks


def normalized_dividends(
    calendar: pd.DatetimeIndex, hashes: dict[str, str]
) -> tuple[pd.DataFrame, list[dict[str, object]], dict[str, int]]:
    path = SOURCE_ROOT / "fundamentals" / "dividend.parquet"
    hashes[str(path.relative_to(SOURCE_ROOT))] = sha256(path)
    div = pd.read_parquet(path)
    actions = normalized_actions_frame(build_finmind_normalized_actions(div))
    if actions.empty:
        raise SystemExit("normalized dividend source is unexpectedly empty")
    actions["effective_date"] = as_dt(actions["effective_date"]).dt.normalize()
    actions["known_at"] = as_dt(actions["known_at"])
    x = actions[
        actions["effective_date"].between(WARMUP_START, E1_END)
    ].copy()

    first_obs = []
    cutoff = []
    cutoff_safe = []
    for q in x.itertuples(index=False):
        obs = first_session_on_or_after(pd.Timestamp(q.effective_date), calendar)
        nxt = next_session_after(obs, calendar) if pd.notna(obs) else pd.NaT
        first_obs.append(obs)
        cutoff.append(nxt)
        known = pd.Timestamp(q.known_at) if pd.notna(q.known_at) else pd.NaT
        cutoff_safe.append(bool(pd.notna(known) and pd.notna(nxt) and known < nxt))
    x["first_observation_session"] = first_obs
    x["first_observation_cutoff"] = cutoff
    x["known_before_first_observation_cutoff"] = cutoff_safe

    summary: list[dict[str, object]] = []
    for (year, kind), g in x.groupby(
        [x["effective_date"].dt.year, "event_kind"]
    ):
        summary.append(
            {
                "section": "normalized_dividend",
                "year": int(year),
                "event_kind": str(kind),
                "rows": int(len(g)),
                "distinct_tickers": int(g["stock_id"].nunique()),
                "known_at_missing": int(g["known_at"].isna().sum()),
                "known_after_effective_date": int(
                    (
                        g["known_at"].notna()
                        & (g["known_at"] > g["effective_date"])
                    ).sum()
                ),
                "not_known_before_first_observation_cutoff": int(
                    (~g["known_before_first_observation_cutoff"]).sum()
                ),
            }
        )
    checks = {
        "normalized_components_warmup_e1": int(len(x)),
        "normalized_distinct_tickers_warmup_e1": int(x["stock_id"].nunique()),
        "normalized_known_at_missing": int(x["known_at"].isna().sum()),
        "normalized_not_known_before_first_observation_cutoff": int(
            (~x["known_before_first_observation_cutoff"]).sum()
        ),
    }
    return x, summary, checks


def official_dividend_reconciliation(
    normalized: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    hashes: dict[str, str],
) -> tuple[list[dict[str, object]], pd.DataFrame, dict[str, int]]:
    path = SOURCE_ROOT / "reference" / "corporate_actions_official.csv"
    hashes[str(path.relative_to(SOURCE_ROOT))] = sha256(path)
    off = pd.read_csv(path, dtype=str).fillna("")
    required = {"stock_id", "event_date", "event_type", "source_name"}
    missing = sorted(required - set(off.columns))
    if missing:
        raise SystemExit(f"{path} missing required columns: {missing}")
    off["stock_id"] = off["stock_id"].astype(str).str.strip()
    off["event_date"] = as_dt(off["event_date"]).dt.normalize()
    off = off[
        off["event_type"].eq("ex_right_dividend")
        & off["event_date"].between(WARMUP_START, E1_END)
    ].copy()
    off = off.drop_duplicates(
        ["stock_id", "event_date", "event_type", "source_name"], keep="last"
    )

    norm_keys = normalized[
        ["stock_id", "effective_date"]
    ].drop_duplicates().rename(columns={"effective_date": "event_date"})
    keyed = off.merge(
        norm_keys.assign(normalized_match=True),
        on=["stock_id", "event_date"],
        how="left",
    )
    keyed["normalized_match"] = keyed["normalized_match"].fillna(False).astype(bool)

    summary: list[dict[str, object]] = []
    for (year, source), g in keyed.groupby(
        [keyed["event_date"].dt.year, "source_name"], dropna=False
    ):
        summary.append(
            {
                "section": "official_ca_reconciliation",
                "year": int(year),
                "source_name": str(source),
                "official_rows": int(len(g)),
                "distinct_tickers": int(g["stock_id"].nunique()),
                "matched_normalized_same_stock_date": int(g["normalized_match"].sum()),
                "unmatched_official_rows": int((~g["normalized_match"]).sum()),
            }
        )

    unmatched = keyed[~keyed["normalized_match"]].copy()
    scope_rows: list[dict[str, object]] = []
    for q in unmatched.itertuples(index=False):
        ma_s, ma_e, ma_n = affected_e1_window(
            pd.Timestamp(q.event_date), calendar, 119
        )
        n_s, n_e, n_n = affected_e1_window(
            pd.Timestamp(q.event_date), calendar, 61
        )
        scope_rows.append(
            {
                "stock_id": q.stock_id,
                "event_date": pd.Timestamp(q.event_date).date().isoformat(),
                "source_name": q.source_name,
                "reason": "OFFICIAL_EX_RIGHT_DIVIDEND_WITHOUT_NORMALIZED_SAME_STOCK_DATE",
                "ma120_e1_start": ma_s,
                "ma120_e1_end": ma_e,
                "ma120_e1_sessions": ma_n,
                "n60_e1_start": n_s,
                "n60_e1_end": n_e,
                "n60_e1_sessions": n_n,
            }
        )
    unmatched_scope = pd.DataFrame(scope_rows)
    if unmatched_scope.empty:
        unmatched_scope = pd.DataFrame(
            columns=[
                "stock_id",
                "event_date",
                "source_name",
                "reason",
                "ma120_e1_start",
                "ma120_e1_end",
                "ma120_e1_sessions",
                "n60_e1_start",
                "n60_e1_end",
                "n60_e1_sessions",
            ]
        )
    checks = {
        "official_ex_right_dividend_warmup_e1": int(len(keyed)),
        "official_ex_right_dividend_unmatched": int(len(unmatched_scope)),
        "official_ex_right_dividend_unmatched_tickers": int(
            unmatched_scope["stock_id"].nunique() if len(unmatched_scope) else 0
        ),
        "unmatched_with_ma120_e1_impact": int(
            (pd.to_numeric(unmatched_scope["ma120_e1_sessions"], errors="coerce") > 0).sum()
            if len(unmatched_scope)
            else 0
        ),
        "unmatched_with_n60_e1_impact": int(
            (pd.to_numeric(unmatched_scope["n60_e1_sessions"], errors="coerce") > 0).sum()
            if len(unmatched_scope)
            else 0
        ),
    }
    return summary, unmatched_scope, checks


def nondividend_scope(
    calendar: pd.DatetimeIndex, hashes: dict[str, str]
) -> tuple[list[dict[str, object]], pd.DataFrame, dict[str, int]]:
    path = SOURCE_ROOT / "reference" / "corporate_actions_ledger.parquet"
    hashes[str(path.relative_to(SOURCE_ROOT))] = sha256(path)
    x = pd.read_parquet(path)
    required = {
        "stock_id",
        "event_date",
        "known_date",
        "event_type",
        "share_multiplier",
        "cash_per_share",
        "source_name",
    }
    missing = sorted(required - set(x.columns))
    if missing:
        raise SystemExit(f"{path} missing required columns: {missing}")
    x = x.copy()
    x["stock_id"] = x["stock_id"].astype(str)
    x["event_date"] = as_dt(x["event_date"]).dt.normalize()
    x["known_date"] = as_dt(x["known_date"])
    x["share_multiplier"] = pd.to_numeric(x["share_multiplier"], errors="coerce")
    kinds = {
        "capital_reduction",
        "par_value_change_split",
        "capital_reduction_deficit",
    }
    x = x[
        x["event_type"].isin(kinds)
        & x["event_date"].between(WARMUP_START, E1_END)
    ].copy()
    x = x.drop_duplicates(
        ["stock_id", "event_date", "event_type", "source_name"], keep="last"
    )

    rows: list[dict[str, object]] = []
    for q in x.itertuples(index=False):
        ma_s, ma_e, ma_n = affected_e1_window(pd.Timestamp(q.event_date), calendar, 119)
        n_s, n_e, n_n = affected_e1_window(pd.Timestamp(q.event_date), calendar, 61)
        known_missing = pd.isna(q.known_date)
        multiplier_missing = pd.isna(q.share_multiplier) or float(q.share_multiplier) <= 0
        reasons = []
        if known_missing:
            reasons.append("KNOWN_DATE_MISSING")
        if multiplier_missing:
            reasons.append("SHARE_MULTIPLIER_MISSING_OR_INVALID")
        if str(q.event_type) not in {"capital_reduction", "par_value_change_split"}:
            reasons.append("EVENT_KIND_NOT_CERTIFIED_BY_CAUSAL_RAW_V2")
        if not reasons:
            reasons.append("NOT_WIRED_TO_CAUSAL_RAW_V2")
        rows.append(
            {
                "stock_id": q.stock_id,
                "event_date": pd.Timestamp(q.event_date).date().isoformat(),
                "event_type": q.event_type,
                "source_name": q.source_name,
                "known_date_missing": bool(known_missing),
                "share_multiplier_missing_or_invalid": bool(multiplier_missing),
                "reason": "|".join(reasons),
                "ma120_e1_start": ma_s,
                "ma120_e1_end": ma_e,
                "ma120_e1_sessions": ma_n,
                "n60_e1_start": n_s,
                "n60_e1_end": n_e,
                "n60_e1_sessions": n_n,
            }
        )
    scope = pd.DataFrame(rows)
    if scope.empty:
        scope = pd.DataFrame(
            columns=[
                "stock_id",
                "event_date",
                "event_type",
                "source_name",
                "known_date_missing",
                "share_multiplier_missing_or_invalid",
                "reason",
                "ma120_e1_start",
                "ma120_e1_end",
                "ma120_e1_sessions",
                "n60_e1_start",
                "n60_e1_end",
                "n60_e1_sessions",
            ]
        )

    summary: list[dict[str, object]] = []
    if len(scope):
        scope_dates = pd.to_datetime(scope["event_date"])
        for (year, kind), g in scope.groupby([scope_dates.dt.year, "event_type"]):
            summary.append(
                {
                    "section": "nondividend_share_event",
                    "year": int(year),
                    "event_type": str(kind),
                    "rows": int(len(g)),
                    "distinct_tickers": int(g["stock_id"].nunique()),
                    "known_date_missing": int(g["known_date_missing"].sum()),
                    "share_multiplier_missing_or_invalid": int(
                        g["share_multiplier_missing_or_invalid"].sum()
                    ),
                    "ma120_e1_impacted_events": int(
                        (pd.to_numeric(g["ma120_e1_sessions"], errors="coerce") > 0).sum()
                    ),
                    "n60_e1_impacted_events": int(
                        (pd.to_numeric(g["n60_e1_sessions"], errors="coerce") > 0).sum()
                    ),
                }
            )
    checks = {
        "nondividend_share_event_rows_warmup_e1": int(len(scope)),
        "nondividend_share_event_tickers_warmup_e1": int(
            scope["stock_id"].nunique() if len(scope) else 0
        ),
        "nondividend_known_date_missing": int(
            scope["known_date_missing"].sum() if len(scope) else 0
        ),
        "nondividend_multiplier_missing_or_invalid": int(
            scope["share_multiplier_missing_or_invalid"].sum() if len(scope) else 0
        ),
        "nondividend_events_with_ma120_e1_impact": int(
            (pd.to_numeric(scope["ma120_e1_sessions"], errors="coerce") > 0).sum()
            if len(scope)
            else 0
        ),
        "nondividend_events_with_n60_e1_impact": int(
            (pd.to_numeric(scope["n60_e1_sessions"], errors="coerce") > 0).sum()
            if len(scope)
            else 0
        ),
    }
    return summary, scope, checks


def finmind_gap_audit(hashes: dict[str, str]) -> tuple[list[dict[str, object]], dict[str, int]]:
    path = SOURCE_ROOT / "reference" / "finmind_gap_fill_audit.csv"
    if not path.exists():
        return [], {"finmind_gap_fill_rows_warmup_e1": -1}
    hashes[str(path.relative_to(SOURCE_ROOT))] = sha256(path)
    x = pd.read_csv(path)
    x = x[x["year"].between(2015, 2021)].copy()
    summary = []
    for q in x.itertuples(index=False):
        summary.append(
            {
                "section": "finmind_gap_fill",
                "year": int(q.year),
                "target_missing_before": int(q.target_missing_before),
                "finmind_rows_added": int(q.finmind_rows_added),
                "target_not_recovered": int(q.target_not_recovered),
                "existing_rows_overwritten": int(q.existing_rows_overwritten),
            }
        )
    checks = {
        "finmind_gap_fill_rows_warmup_e1": int(x["finmind_rows_added"].sum()),
        "finmind_gap_fill_unrecovered_warmup_e1": int(x["target_not_recovered"].sum()),
        "finmind_gap_fill_overwrites_warmup_e1": int(x["existing_rows_overwritten"].sum()),
    }
    return summary, checks


def md_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_none_"
    cols = list(df.columns)
    head = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    rows = []
    for _, r in df.iterrows():
        vals = []
        for c in cols:
            v = r[c]
            if pd.isna(v):
                vals.append("")
            else:
                vals.append(str(v).replace("|", "\\|"))
        rows.append("| " + " | ".join(vals) + " |")
    return "\n".join([head, sep, *rows])


def main() -> None:
    raw, raw_summary, hashes = read_raw()
    cal = actual_calendar(raw)
    if len(cal) == 0:
        raise SystemExit("empty warmup+E1 RAW calendar")
    trad_summary, trad_checks = audit_tradability(raw, hashes)
    norm, norm_summary, norm_checks = normalized_dividends(cal, hashes)
    off_summary, unmatched, off_checks = official_dividend_reconciliation(
        norm, cal, hashes
    )
    nondiv_summary, nondiv, nondiv_checks = nondividend_scope(cal, hashes)
    gap_summary, gap_checks = finmind_gap_audit(hashes)

    summary_rows = [
        *raw_summary,
        *gap_summary,
        *trad_summary,
        *norm_summary,
        *off_summary,
        *nondiv_summary,
    ]
    summary = pd.DataFrame(summary_rows)
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(SUMMARY_PATH, index=False, encoding="utf-8-sig")
    unmatched.to_csv(UNMATCHED_CA_PATH, index=False, encoding="utf-8-sig")
    nondiv.to_csv(NONDIV_PATH, index=False, encoding="utf-8-sig")

    raw_period = raw[raw["date"].between(WARMUP_START, E1_END)]
    raw_totals = {
        "rows_warmup_e1": int(len(raw_period)),
        "distinct_tickers_warmup_e1": int(raw_period["stock_id"].nunique()),
        "ohlc_null_rows_warmup_e1": int(
            raw_period[["open", "max", "min", "close"]].isna().any(axis=1).sum()
        ),
        "trading_money_null_rows_warmup_e1": int(
            raw_period["Trading_money"].isna().sum()
        ),
        "duplicate_keys_warmup_e1": int(
            raw_period.duplicated(["date", "stock_id"]).sum()
        ),
        "calendar_sessions_warmup_e1": int(len(cal)),
    }
    source_totals = (
        raw_period["source"].fillna("UNKNOWN").value_counts(dropna=False).to_dict()
    )

    all_checks = {
        **raw_totals,
        **trad_checks,
        **norm_checks,
        **off_checks,
        **nondiv_checks,
        **gap_checks,
    }

    manifest = {
        "evidence_version": "layer1_causal_raw_v2_gate_evidence_v1",
        "source_revision": SOURCE_REVISION,
        "period": {
            "warmup_start": WARMUP_START.date().isoformat(),
            "e1_start": E1_START.date().isoformat(),
            "e1_end": E1_END.date().isoformat(),
        },
        "input_sha256": hashes,
        "checks": all_checks,
        "raw_source_rows": {str(k): int(v) for k, v in source_totals.items()},
        "formal_e1_feature_artifact_built": False,
        "strategy_effects_computed": False,
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    raw_year = (
        raw_period.assign(year=raw_period["date"].dt.year)
        .groupby("year")
        .agg(
            rows=("stock_id", "size"),
            tickers=("stock_id", "nunique"),
            ohlc_null_rows=(
                "close",
                lambda s: int(
                    raw_period.loc[s.index, ["open", "max", "min", "close"]]
                    .isna()
                    .any(axis=1)
                    .sum()
                ),
            ),
            trading_money_null_rows=("Trading_money", lambda s: int(s.isna().sum())),
        )
        .reset_index()
    )
    raw_sources = (
        raw_period.groupby(["source"], dropna=False)
        .agg(rows=("stock_id", "size"), tickers=("stock_id", "nunique"))
        .reset_index()
        .sort_values("rows", ascending=False)
    )
    norm_year = pd.DataFrame(norm_summary)
    off_year = pd.DataFrame(off_summary)
    nondiv_year = pd.DataFrame(nondiv_summary)

    report = f"""# Layer 1 causal RAW v2 — real-data gate evidence

Status: **EVIDENCE AUDIT COMPLETE / FORMAL E1 ARTIFACT NOT BUILT**

This is a source/data-quality audit for item 5 only. It uses source revision
`{SOURCE_REVISION}`, warmup 2015 plus E1 through 2021-12-31. It computes no
strategy outcome, E2/E3 effect, return, win rate, or expectancy.

## RAW / Trading_money coverage

{md_table(raw_year)}

Source rows in the frozen RAW files:

{md_table(raw_sources)}

The frozen RAW files have zero duplicate logical keys in warmup+E1. Null OHLC
rows remain explicit; they are not compressed or filled.

The source repository's own gap-fill ledger reports
**{gap_checks["finmind_gap_fill_rows_warmup_e1"]:,}** FinMind rows added across
2015-2021, with **{gap_checks["finmind_gap_fill_unrecovered_warmup_e1"]:,}**
target rows left unrecovered and **{gap_checks["finmind_gap_fill_overwrites_warmup_e1"]:,}**
existing rows overwritten by that fill. This distinguishes official-source rows
from later FinMind gap reconstruction; it is not availability certification.

## Tradability derivation

{md_table(pd.DataFrame(trad_summary))}

Cross-checks against RAW:
- valid_ohlc reconstruction mismatches on observed RAW keys: **{trad_checks["valid_ohlc_reconstruction_mismatches"]:,}**
- observed_trade=True without RAW key: **{trad_checks["observed_trade_true_without_raw_key"]:,}**
- RAW key marked observed_trade=False: **{trad_checks["raw_key_marked_observed_false"]:,}**
- explicit derived missing rows: **{trad_checks["derived_missing_rows"]:,}**

For the causal-v2 feature/universe builder, `observed_trade` and
`valid_ohlc` are the required fields. `buy_blocked` / `sell_blocked`
remain execution-layer evidence and are not treated as a prerequisite for
constructing MA120/N60/prior20 feature rows.

## Normalized cash / stock dividend components

{md_table(norm_year)}

Warmup+E1 normalized components: **{norm_checks["normalized_components_warmup_e1"]:,}**;
distinct tickers: **{norm_checks["normalized_distinct_tickers_warmup_e1"]:,}**;
known_at missing: **{norm_checks["normalized_known_at_missing"]:,}**;
not known before the first affected observation's machine cutoff:
**{norm_checks["normalized_not_known_before_first_observation_cutoff"]:,}**.

This is field-level timing evidence only. It does not prove that every economic
event is represented, so an independent official-event reconciliation follows.

## Independent official ex-right/dividend reconciliation

{md_table(off_year)}

Detection method: start from the independent official
`corporate_actions_official.csv` ex-right/dividend rows, then left-match the
normalized FinMind cash/stock components by stock and economic ex-date. This
can discover official events absent from the normalized source; it does not
merely validate rows already present in FinMind.

Official rows without any normalized same-stock/ex-date component:
**{off_checks["official_ex_right_dividend_unmatched"]:,}** across
**{off_checks["official_ex_right_dividend_unmatched_tickers"]:,}** tickers.
Among them, **{off_checks["unmatched_with_ma120_e1_impact"]:,}** events overlap
an E1 MA120 dependency window and **{off_checks["unmatched_with_n60_e1_impact"]:,}**
overlap an E1 N60 dependency window. Exact scope is in
`{UNMATCHED_CA_PATH.as_posix()}`.

An unmatched official row is a blocker candidate, not an automatically inferred
cash/share transform. No multiplier, cash amount, or known_at is guessed.

## Non-dividend share-changing events

{md_table(nondiv_year)}

Warmup+E1 rows: **{nondiv_checks["nondividend_share_event_rows_warmup_e1"]:,}**;
distinct tickers: **{nondiv_checks["nondividend_share_event_tickers_warmup_e1"]:,}**;
known_date missing: **{nondiv_checks["nondividend_known_date_missing"]:,}**;
share multiplier missing/invalid: **{nondiv_checks["nondividend_multiplier_missing_or_invalid"]:,}**.

Events overlapping E1 rolling-price dependency windows:
MA120 **{nondiv_checks["nondividend_events_with_ma120_e1_impact"]:,}**,
N60 **{nondiv_checks["nondividend_events_with_n60_e1_impact"]:,}**.
Exact affected ticker/event/window rows are in
`{NONDIV_PATH.as_posix()}`. These are diagnostics only and do not authorize
dropping those tickers or changing the research population.

## Artifact boundary

Evidence artifacts:
- `{SUMMARY_PATH.as_posix()}`
- `{UNMATCHED_CA_PATH.as_posix()}`
- `{NONDIV_PATH.as_posix()}`
- `{MANIFEST_PATH.as_posix()}`

No formal E1 feature artifact is built by this audit. The manifest explicitly
records `formal_e1_feature_artifact_built=false` and
`strategy_effects_computed=false`.
"""
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")

    print(report)
    print("\nManifest checks:")
    print(json.dumps(all_checks, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
