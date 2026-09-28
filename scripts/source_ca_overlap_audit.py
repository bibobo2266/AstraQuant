#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/SOURCE_CA_OVERLAP_AUDIT.md"))


def main() -> None:
    path = SOURCE_ROOT / "reference" / "corporate_actions_ledger.parquet"
    df = pd.read_parquet(
        path,
        columns=[
            "stock_id", "event_date", "event_type", "cash_per_share",
            "share_multiplier", "rights_ratio", "source_name", "known_date",
        ],
    )
    df["stock_id"] = df["stock_id"].astype(str)
    df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce").dt.normalize()
    df["event_type"] = df["event_type"].fillna("UNKNOWN").astype(str)
    for c in ("cash_per_share", "share_multiplier", "rights_ratio"):
        df[c] = pd.to_numeric(df[c], errors="coerce")

    rows = []
    overlap_groups = 0
    both_cash = 0
    cash_agree = 0
    cash_conflict = 0
    tpex_official_overlap = 0

    for (ticker, day), g in df.groupby(["stock_id", "event_date"], sort=True):
        types = set(g["event_type"])
        if not {"dividend", "ex_right_dividend"}.issubset(types):
            continue
        overlap_groups += 1
        div = g[g["event_type"].eq("dividend")]
        exr = g[g["event_type"].eq("ex_right_dividend")]

        div_cash = sorted(set(round(float(v), 8) for v in div["cash_per_share"].dropna()))
        exr_cash = sorted(set(round(float(v), 8) for v in exr["cash_per_share"].dropna()))
        if div_cash and exr_cash:
            both_cash += 1
            agree = any(abs(a - b) <= 1e-6 for a in div_cash for b in exr_cash)
            if agree:
                cash_agree += 1
            else:
                cash_conflict += 1
        if exr["source_name"].astype(str).str.contains("TPEx exDailyQ", regex=False).any():
            tpex_official_overlap += 1

        if len(rows) < 25:
            rows.append({
                "ticker": ticker,
                "date": day.date(),
                "div_cash": div_cash,
                "exr_cash": exr_cash,
                "div_rights": sorted(set(round(float(v), 8) for v in div["rights_ratio"].dropna())),
                "exr_mult": sorted(set(round(float(v), 10) for v in exr["share_multiplier"].dropna())),
                "div_sources": "; ".join(sorted(set(div["source_name"].astype(str)))),
                "exr_sources": "; ".join(sorted(set(exr["source_name"].astype(str)))),
            })

    q1 = df[
        df["event_date"].between(pd.Timestamp("2026-01-02"), pd.Timestamp("2026-04-02"))
    ]
    q1_groups = []
    for (ticker, day), g in q1.groupby(["stock_id", "event_date"], sort=True):
        types = set(g["event_type"])
        if {"dividend", "ex_right_dividend"}.issubset(types):
            q1_groups.append((ticker, day, len(g)))

    status = "PASS_WITH_DEDUP_REQUIRED" if overlap_groups else "PASS_NO_OVERLAP"
    lines = [
        "# Source Corporate-Action Overlap Audit",
        "",
        f"Status: **{status}**",
        "",
        "Purpose: determine whether dividend and official ex_right_dividend rows can represent the same economic event and would therefore double-count cash/share effects if consumed independently.",
        "",
        f"- total ledger rows: {len(df):,}",
        f"- same ticker/date groups containing both event types: {overlap_groups:,}",
        f"- overlap groups with cash populated on both representations: {both_cash:,}",
        f"- cash values agreeing within 1e-6: {cash_agree:,}",
        f"- cash values conflicting: {cash_conflict:,}",
        f"- overlap groups containing TPEx exDailyQ official rows: {tpex_official_overlap:,}",
        f"- overlap groups in 2026-01-02 through 2026-04-02: {len(q1_groups):,}",
        "",
        "## Sample overlap groups",
        "",
        "| Ticker | Date | dividend cash | ex_right cash | dividend rights_ratio | ex_right multiplier | dividend source | ex_right source |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['ticker']} | {r['date']} | {r['div_cash']} | {r['exr_cash']} | "
            f"{r['div_rights']} | {r['exr_mult']} | {r['div_sources']} | {r['exr_sources']} |"
        )

    lines += [
        "",
        "## Consumer implication",
        "",
        "Rows that describe the same ticker/date dividend/ex-right event must be normalized into one economic event before portfolio accounting. They must not be independently accrued.",
        "",
        "Official exchange values should be preferred for economic cash/share fields when populated. FinMind dividend rows may supply known/announcement timing and detailed fields where the exchange row lacks them, but that provenance merge must not duplicate the economic event.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
