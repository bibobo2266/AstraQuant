#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import pandas as pd

SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/SOURCE_2823_CONVERSION_AUDIT.md"))


def main() -> None:
    tickers = ["2823", "2883", "2883B"]
    frames = []
    for year in [2021, 2022]:
        p = SOURCE_ROOT / "raw" / f"prices_raw_{year}.parquet"
        if not p.exists():
            continue
        d = pd.read_parquet(p, columns=["date", "stock_id", "open", "max", "min", "close"])
        d["date"] = pd.to_datetime(d["date"], errors="coerce").dt.normalize()
        d["stock_id"] = d["stock_id"].astype(str)
        frames.append(d[d["stock_id"].isin(tickers) & d["date"].between(pd.Timestamp("2021-12-15"), pd.Timestamp("2022-01-07"))])
    raw = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    trad = pd.read_parquet(SOURCE_ROOT / "reference" / "tradability.parquet", columns=["date", "stock_id", "observed_trade", "valid_ohlc", "buy_blocked", "sell_blocked", "reason"])
    trad["date"] = pd.to_datetime(trad["date"], errors="coerce").dt.normalize()
    trad["stock_id"] = trad["stock_id"].astype(str)
    trad = trad[trad["stock_id"].isin(tickers) & trad["date"].between(pd.Timestamp("2021-12-15"), pd.Timestamp("2022-01-07"))]

    lines = ["# Source 2823 Share-Conversion Audit", "", "Purpose: verify successor-security RAW/tradability coverage around the 2823 -> 2883 + 2883B + cash conversion.", "", "## RAW observations", ""]
    lines.append(raw.sort_values(["stock_id", "date"]).to_string(index=False) if not raw.empty else "- none")
    lines += ["", "## Tradability observations", ""]
    lines.append(trad.sort_values(["stock_id", "date"]).to_string(index=False) if not trad.empty else "- none")

    for ticker in tickers:
        x = raw[raw["stock_id"].eq(ticker)]
        lines += ["", f"## {ticker} summary", "", f"- RAW rows in window: {len(x):,}", f"- first RAW date: {x['date'].min().date() if not x.empty else 'NONE'}", f"- last RAW date: {x['date'].max().date() if not x.empty else 'NONE'}"]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()