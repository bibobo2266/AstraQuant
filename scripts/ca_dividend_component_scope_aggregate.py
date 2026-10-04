#!/usr/bin/env python3
"""Aggregate scope for private CA reconciliation rows.

Consumes row-level event reconciliation in a private path and emits only
aggregate scope/count-conservation data suitable for the public repository.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

WARMUP_START = pd.Timestamp("2015-01-01")
E1_START = pd.Timestamp("2016-01-04")
E1_END = pd.Timestamp("2021-12-31")


def load_panel(source_root: Path) -> pd.DataFrame:
    raw_parts = []
    for year in range(2015, 2022):
        p = source_root / "raw" / f"prices_raw_{year}.parquet"
        x = pd.read_parquet(p, columns=["date", "stock_id", "close", "Trading_money"])
        x["date"] = pd.to_datetime(x["date"], errors="coerce").dt.normalize()
        x["stock_id"] = x["stock_id"].astype(str)
        raw_parts.append(x)
    raw = pd.concat(raw_parts, ignore_index=True)
    raw = raw[raw["date"].between(WARMUP_START, E1_END)].copy()

    trad = pd.read_parquet(
        source_root / "reference" / "tradability.parquet",
        columns=["date", "stock_id", "observed_trade", "valid_ohlc"],
    )
    trad["date"] = pd.to_datetime(trad["date"], errors="coerce").dt.normalize()
    trad["stock_id"] = trad["stock_id"].astype(str)
    trad = trad[trad["date"].between(WARMUP_START, E1_END)].copy()
    out = raw.merge(trad, on=["date", "stock_id"], how="left", validate="one_to_one")
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    out["Trading_money"] = pd.to_numeric(out["Trading_money"], errors="coerce")
    return out


def research_tickers(panel: pd.DataFrame, exclusions_path: Path) -> set[str]:
    x = panel[panel["date"].between(E1_START, E1_END)].copy()
    exclusions = pd.read_csv(exclusions_path, dtype={"ticker": str})
    excluded = set(exclusions["ticker"].astype(str))
    base = (
        x["stock_id"].str.fullmatch(r"[1-9]\d{3}", na=False)
        & x["close"].ge(10).fillna(False)
        & x["observed_trade"].fillna(False).astype(bool)
        & x["valid_ohlc"].fillna(False).astype(bool)
        & ~x["stock_id"].isin(excluded)
    )
    pct = x["Trading_money"].where(base).groupby(x["date"]).rank(
        pct=True, ascending=False, method="average"
    )
    counts = base & pct.le(0.25).fillna(False)
    return set(x.loc[counts, "stock_id"].astype(str))


def theoretical_overlap(day: pd.Timestamp, sessions: pd.DatetimeIndex, width: int) -> bool:
    pos = int(sessions.searchsorted(pd.Timestamp(day).normalize(), side="left"))
    if pos >= len(sessions):
        return False
    affected = sessions[pos : min(len(sessions), pos + width)]
    return bool(((affected >= E1_START) & (affected <= E1_END)).any())


def conservation(events: pd.DataFrame, mask: pd.Series) -> dict[str, object]:
    g = events[mask]
    classes = {str(k): int(v) for k, v in g["primary_class"].value_counts().items()}
    if sum(classes.values()) != len(g):
        raise SystemExit("primary class conservation failed")
    return {
        "event_groups": int(len(g)),
        "distinct_tickers": int(g["stock_id"].nunique()),
        "classes": classes,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", required=True)
    ap.add_argument("--source-root", required=True)
    ap.add_argument("--exclusions", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    events = pd.read_csv(args.events, dtype={"stock_id": str})
    events["event_date"] = pd.to_datetime(events["event_date"], errors="coerce").dt.normalize()
    required = ["economic_event_id", "stock_id", "event_date", "primary_class"]
    if events[required].isna().any(axis=1).any():
        raise SystemExit("private event reconciliation has null required keys")
    if events["economic_event_id"].duplicated().any():
        raise SystemExit("private event reconciliation has duplicate economic_event_id")

    panel = load_panel(Path(args.source_root))
    rt = research_tickers(panel, Path(args.exclusions))
    valid = (
        panel["observed_trade"].fillna(False).astype(bool)
        & panel["valid_ohlc"].fillna(False).astype(bool)
    )
    active = (
        panel[valid]
        .groupby("stock_id", as_index=False)
        .agg(active_first=("date", "min"), active_last=("date", "max"))
    )
    x = events.merge(active, on="stock_id", how="left", validate="many_to_one")
    x["in_established_e1_all_liquid_ticker_set"] = x["stock_id"].isin(rt)
    x["inside_observed_valid_active_span"] = (
        x["active_first"].notna()
        & x["active_last"].notna()
        & x["event_date"].between(x["active_first"], x["active_last"])
    )

    sessions = pd.DatetimeIndex(sorted(panel["date"].dropna().unique()))
    x["theoretical_ma120_e1_dependency"] = x["event_date"].map(
        lambda d: theoretical_overlap(d, sessions, 119)
    )
    x["theoretical_n60_e1_dependency"] = x["event_date"].map(
        lambda d: theoretical_overlap(d, sessions, 61)
    )
    x["warmup_event"] = x["event_date"].lt(E1_START)

    scopes = {
        "SOURCE_ALL_WARMUP_PLUS_E1": pd.Series(True, index=x.index),
        "FOUR_DIGIT_RESEARCH_SECURITY_BASE": x["security_scope"].eq("RESEARCH_TICKER_PATTERN"),
        "ESTABLISHED_E1_ALL_LIQUID_TICKERS": x["in_established_e1_all_liquid_ticker_set"],
        "WARMUP_EVENTS_WITH_MA120_E1_DEPENDENCY": x["warmup_event"] & x["theoretical_ma120_e1_dependency"],
        "WARMUP_EVENTS_WITH_N60_E1_DEPENDENCY": x["warmup_event"] & x["theoretical_n60_e1_dependency"],
    }
    result = {
        "scope_contract": {
            "established_e1_all_liquid": "four-digit ID; RAW close>=10; observed_trade; valid_ohlc; frozen P2-060 exclusions; same-day top-25% Trading_money",
            "population_changed": False,
        },
        "established_e1_all_liquid_distinct_tickers": int(len(rt)),
        "scope_conservation": {name: conservation(x, mask) for name, mask in scopes.items()},
        "active_coverage": {
            "event_groups_inside_observed_valid_active_span": int(x["inside_observed_valid_active_span"].sum()),
            "event_groups_outside_or_without_active_span": int((~x["inside_observed_valid_active_span"]).sum()),
        },
        "theoretical_dependency": {
            "ma120_event_groups_overlapping_e1": int(x["theoretical_ma120_e1_dependency"].sum()),
            "n60_event_groups_overlapping_e1": int(x["theoretical_n60_e1_dependency"].sum()),
            "is_actual_builder_block_count": False,
        },
        "actual_builder_contract": {
            "unknown_known_at": "effective unresolved event blocks current coordinate and later events; unknown remains blocked",
            "known_not_before_cutoff": "blocks until known_at < decision_cutoff_at",
            "recovery_rule_changed": False,
            "existing_minimal_case": "tests/test_causal_raw_v2.py::test_earlier_unresolved_event_prevents_later_event_from_applying_out_of_order",
        },
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "established_e1_all_liquid_distinct_tickers": result["established_e1_all_liquid_distinct_tickers"],
        "active_coverage": result["active_coverage"],
        "theoretical_dependency": result["theoretical_dependency"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
