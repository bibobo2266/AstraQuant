#!/usr/bin/env python3
from __future__ import annotations
import os
from pathlib import Path
import pandas as pd

SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/SOURCE_2823_RAW_GAP_AUDIT.md"))
TICKER = "2823"
START = pd.Timestamp("2021-12-01")
END = pd.Timestamp("2022-01-10")


def slice_file(path: Path, columns=None):
    if not path.exists():
        return pd.DataFrame()
    d = pd.read_parquet(path, columns=columns)
    if "stock_id" in d.columns:
        d["stock_id"] = d["stock_id"].astype(str)
        d = d[d["stock_id"].eq(TICKER)]
    for c in ("date", "event_date", "known_date"):
        if c in d.columns:
            d[c] = pd.to_datetime(d[c], errors="coerce").dt.normalize()
    date_col = "date" if "date" in d.columns else ("event_date" if "event_date" in d.columns else None)
    if date_col:
        d = d[d[date_col].between(START, END)]
    return d


raw = slice_file(SOURCE_ROOT / "raw" / "prices_raw_2021.parquet")
adj = slice_file(SOURCE_ROOT / "adj" / "prices_adj_2021.parquet")
trad = slice_file(SOURCE_ROOT / "reference" / "tradability.parquet")
ledger = slice_file(SOURCE_ROOT / "reference" / "corporate_actions_ledger.parquet")

def fmt(df):
    if df.empty:
        return "_none_"
    keep=[c for c in ["date","event_date","known_date","stock_id","open","max","min","close","Trading_money","observed_trade","valid_ohlc","buy_blocked","sell_blocked","reason","event_type","source_type","source_name","source_url","cash_per_share","share_multiplier"] if c in df.columns]
    return df[keep].to_markdown(index=False)

lines=[
"# 2823 RAW Gap / Terminal-Semantics Audit","",
"Status: **SOURCE_AUDIT_ONLY**","",
"Purpose: investigate the P2-062 blocker without adjusted-price fallback or silent ticker exclusion. The observed failure was an unavailable canonical RAW mark for 2823 on 2021-12-20 while the reverse breakout-strength rule held the security.","",
"## RAW rows", "", fmt(raw), "",
"## Adjusted rows (diagnostic only; never execution fallback)", "", fmt(adj), "",
"## Tradability rows", "", fmt(trad), "",
"## Corporate-action ledger rows", "", fmt(ledger), "",
"## Decision boundary","",
"This audit does not authorize excluding 2823 and does not authorize using adjusted prices as RAW marks. If the source shows a terminal/security-conversion event that AstraQuant has not modeled, that event must be accounted explicitly and then P2-062 rerun on the unchanged frozen common-support policy.",
]
REPORT_PATH.write_text("\n".join(lines)+"\n",encoding="utf-8")
