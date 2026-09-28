#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import pandas as pd

SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/SOURCE_TERMINAL_SECURITY_AUDIT.md"))
TICKER = os.environ.get("TICKER", "4141")
TARGET = pd.Timestamp(os.environ.get("TARGET_DATE", "2022-04-27")).normalize()


def main() -> None:
    lines = [
        "# Source Terminal Security Audit",
        "",
        f"- ticker: {TICKER}",
        f"- target date: {TARGET.date()}",
        "",
    ]

    candidates = [
        SOURCE_ROOT / "reference" / "finmind_suspended.parquet",
        SOURCE_ROOT / "universe.parquet",
    ]
    for path in candidates:
        lines += [f"## {path.name}", ""]
        if not path.exists():
            lines += ["- missing", ""]
            continue
        d = pd.read_parquet(path)
        lines.append(f"- rows: {len(d):,}")
        lines.append(f"- columns: {', '.join(map(str, d.columns))}")
        if "stock_id" in d.columns:
            x = d[d["stock_id"].astype(str).eq(TICKER)].copy()
        elif "code" in d.columns:
            x = d[d["code"].astype(str).eq(TICKER)].copy()
        else:
            x = pd.DataFrame()
        lines.append(f"- ticker rows: {len(x):,}")
        if not x.empty:
            lines += ["", "TEXT_BEGIN", x.to_string(index=False), "TEXT_END"]
        lines.append("")

    raw_parts = []
    for year in [TARGET.year - 1, TARGET.year, TARGET.year + 1]:
        p = SOURCE_ROOT / "raw" / f"prices_raw_{year}.parquet"
        if p.exists():
            d = pd.read_parquet(
                p,
                columns=["date", "stock_id", "open", "max", "min", "close"],
            )
            d["stock_id"] = d["stock_id"].astype(str)
            raw_parts.append(d[d["stock_id"].eq(TICKER)])
    raw = pd.concat(raw_parts, ignore_index=True) if raw_parts else pd.DataFrame()
    if not raw.empty:
        raw["date"] = pd.to_datetime(raw["date"], errors="coerce").dt.normalize()
        raw = raw.sort_values("date")
        lines += [
            "## RAW terminal span",
            "",
            f"- first RAW date: {raw['date'].min().date()}",
            f"- last RAW date: {raw['date'].max().date()}",
            f"- RAW rows: {len(raw):,}",
            "",
            "### Last 10 RAW rows",
            "",
            "TEXT_BEGIN",
            raw.tail(10).to_string(index=False),
            "TEXT_END",
            "",
        ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
