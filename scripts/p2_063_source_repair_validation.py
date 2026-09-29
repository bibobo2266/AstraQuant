#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
from datetime import date
from pathlib import Path

import pandas as pd

from astraquant.data.source_adapter import SourceDataAdapter
from astraquant.execution.market_data import ExecutionAvailability, ExecutionMarketData

from source_eligible_universe_ca_coverage import eligible_turnover_universe
from source_strategy_integration_smoke import load_adjusted, load_tradability

SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
EXCLUSIONS_PATH = Path(os.environ.get("EXCLUSIONS_PATH", "docs/SOURCE_CA_PIT_EXCLUSIONS.csv"))
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/P2_063_SOURCE_REPAIR_VALIDATION.md"))
EXPECTED_SHA = "379d58f6a8aa06b1e020d56911930f4bc01861d3eeca109613d9e5b1e490d134"
EXPECTED_ELIGIBLE = 1986
TICKER = "2883B"
START = pd.Timestamp("2021-12-30")
END = pd.Timestamp("2026-07-07")


def main() -> None:
    digest = hashlib.sha256(EXCLUSIONS_PATH.read_bytes()).hexdigest()
    hash_ok = digest == EXPECTED_SHA

    adjusted = load_adjusted()
    tradability = load_tradability(adjusted)
    eligible = eligible_turnover_universe(adjusted, tradability)
    eligible_ids = eligible["stock_id"].astype(str)
    eligible_count = int(eligible_ids.nunique())
    candidate_numeric_only = bool(
        eligible_ids.str.fullmatch(r"[1-9]\d{3}", na=False).all()
    )

    raw_parts = []
    for year in range(2021, 2027):
        path = SOURCE_ROOT / "raw" / f"prices_raw_{year}.parquet"
        if not path.exists():
            raise SystemExit(f"BLOCKED: missing RAW file {path}")
        part = pd.read_parquet(
            path,
            columns=["date", "stock_id", "open", "max", "min", "close"],
        )
        part["date"] = pd.to_datetime(part["date"], errors="coerce").dt.normalize()
        part["stock_id"] = part["stock_id"].astype(str)
        raw_parts.append(part[part["stock_id"].eq(TICKER)].copy())
    raw = pd.concat(raw_parts, ignore_index=True)
    raw = raw[raw["date"].between(START, END, inclusive="both")].copy()
    if raw.duplicated(["date", "stock_id"]).any():
        raise SystemExit("FAIL: duplicate 2883B RAW logical keys")

    trad = pd.read_parquet(
        SOURCE_ROOT / "reference" / "tradability.parquet",
        columns=["date", "stock_id", "observed_trade", "valid_ohlc"],
    )
    trad["date"] = pd.to_datetime(trad["date"], errors="coerce").dt.normalize()
    trad["stock_id"] = trad["stock_id"].astype(str)
    trad = trad[
        trad["stock_id"].eq(TICKER)
        & trad["date"].between(START, END, inclusive="both")
    ].copy()
    if trad.duplicated(["date", "stock_id"]).any():
        raise SystemExit("FAIL: duplicate 2883B tradability logical keys")

    raw_dates = set(raw["date"])
    trad_dates = set(trad["date"])
    coverage_ok = (
        len(raw) > 0
        and len(trad) > 0
        and raw["date"].min() == START
        and raw["date"].max() == END
        and raw_dates == trad_dates
    )

    gateway = ExecutionMarketData(
        SourceDataAdapter(SOURCE_ROOT),
        ticker_scope={TICKER},
    )
    mark = gateway.resolve_mark(
        ticker=TICKER,
        session_date=date(2021, 12, 30),
        field="close",
    )
    suffix_mark_ok = (
        mark.availability is ExecutionAvailability.EXECUTABLE
        and mark.price is not None
        and float(mark.price) > 0
    )
    valuation_only_ok = candidate_numeric_only and TICKER not in set(eligible_ids)

    checks = {
        "p2_060_exclusion_sha_unchanged": hash_ok,
        "frozen_top25_eligible_ticker_count_1986": eligible_count == EXPECTED_ELIGIBLE,
        "2883b_raw_tradability_window_covered": coverage_ok,
        "suffix_security_markable_but_not_candidate": valuation_only_ok and suffix_mark_ok,
    }
    status = "PASS" if all(checks.values()) else "FAIL"

    lines = [
        "# P2-063 Source Repair Validation",
        "",
        f"Status: **{status}**",
        "",
        f"- P2-060 exclusions SHA256: {digest}",
        f"- eligible distinct tickers: {eligible_count:,}",
        f"- candidate IDs pure four-digit numeric: {candidate_numeric_only}",
        f"- 2883B RAW rows: {len(raw):,}",
        f"- 2883B tradability rows: {len(trad):,}",
        f"- 2883B RAW range: {raw['date'].min().date() if len(raw) else 'n/a'} → {raw['date'].max().date() if len(raw) else 'n/a'}",
        f"- 2883B canonical RAW mark on 2021-12-30: {mark.price if suffix_mark_ok else 'NOT_EXECUTABLE'}",
        "",
        "## Four hard checks",
        "",
        "| Check | Result |",
        "|---|---|",
    ]
    for name, ok in checks.items():
        lines.append(f"| {name} | {'PASS' if ok else 'FAIL'} |")

    lines += [
        "",
        "Research candidate construction remains four-digit ordinary-share only. 2883B is admitted solely to the valuation/execution path when received through an explicit corporate action.",
        "",
        "No adjusted-price fallback or synthetic trade is used by this validation.",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if status != "PASS":
        raise SystemExit("FAIL: P2-063 source-repair hard check failed")


if __name__ == "__main__":
    main()
