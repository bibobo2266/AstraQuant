#!/usr/bin/env python3
from __future__ import annotations

import os
import re
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/RAW_ADJ_QUALITY_AUDIT.md"))

PRICE_COLS = ["open", "max", "min", "close"]
KEYS = ["date", "stock_id"]

def esc(v: object) -> str:
    return str(v).replace("|", "/").replace("\n", " ")

def year_from_name(path: Path) -> int:
    m = re.search(r"(20\d{2})", path.name)
    if not m:
        raise ValueError("year missing from filename: " + path.name)
    return int(m.group(1))

def read_price_file(path: Path) -> pd.DataFrame:
    cols = pq.ParquetFile(path).schema_arrow.names
    need = [c for c in KEYS + PRICE_COLS if c in cols]
    df = pd.read_parquet(path, columns=need)
    df["stock_id"] = df["stock_id"].astype(str)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df

def intrinsic(path: Path, kind: str) -> dict[str, object]:
    df = read_price_file(path)
    year = year_from_name(path)
    numeric_stock = df["stock_id"].str.fullmatch(r"[1-9]\d{3}", na=False)
    key_null = int(df[KEYS].isna().any(axis=1).sum())
    dup = int(df.duplicated(KEYS).sum())
    out = {
        "kind": kind,
        "year": year,
        "file": path.relative_to(SOURCE_ROOT).as_posix(),
        "rows": len(df),
        "unique_tickers": int(df["stock_id"].nunique(dropna=True)),
        "numeric_stock_rows": int(numeric_stock.sum()),
        "key_null_rows": key_null,
        "duplicate_keys": dup,
        "offyear_rows": int((df["date"].dt.year != year).fillna(True).sum()),
    }
    for c in PRICE_COLS:
        if c in df.columns:
            out[c + "_null"] = int(df[c].isna().sum())
            out[c + "_nonpositive"] = int((pd.to_numeric(df[c], errors="coerce") <= 0).fillna(False).sum())
        else:
            out[c + "_null"] = "MISSING_COLUMN"
            out[c + "_nonpositive"] = "MISSING_COLUMN"
    return out

def keyset(path: Path) -> pd.MultiIndex:
    df = pd.read_parquet(path, columns=KEYS)
    df["stock_id"] = df["stock_id"].astype(str)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[df["stock_id"].str.fullmatch(r"[1-9]\d{3}", na=False)].dropna(subset=KEYS)
    return pd.MultiIndex.from_frame(df[KEYS].drop_duplicates())

def main() -> None:
    raw_files = sorted((SOURCE_ROOT / "raw").glob("prices_raw_*.parquet"))
    adj_files = sorted((SOURCE_ROOT / "adj").glob("prices_adj_*.parquet"))
    if not raw_files or not adj_files:
        raise SystemExit("BLOCKED: RAW or adjusted files missing")

    raw_map = {year_from_name(p): p for p in raw_files}
    adj_map = {year_from_name(p): p for p in adj_files}
    years = sorted(set(raw_map) | set(adj_map))

    intrinsic_rows = []
    for p in raw_files:
        intrinsic_rows.append(intrinsic(p, "RAW"))
    for p in adj_files:
        intrinsic_rows.append(intrinsic(p, "ADJ"))

    compare_rows = []
    for y in years:
        rp, ap = raw_map.get(y), adj_map.get(y)
        if rp is None or ap is None:
            compare_rows.append({
                "year": y, "raw_numeric_keys": "N/A", "adj_numeric_keys": "N/A",
                "intersection": "N/A", "adj_missing_raw": "N/A", "raw_missing_adj": "N/A",
                "note": "one side missing",
            })
            continue
        rk = keyset(rp)
        ak = keyset(ap)
        inter = rk.intersection(ak)
        compare_rows.append({
            "year": y,
            "raw_numeric_keys": len(rk),
            "adj_numeric_keys": len(ak),
            "intersection": len(inter),
            "adj_missing_raw": len(ak.difference(rk)),
            "raw_missing_adj": len(rk.difference(ak)),
            "note": "informational; universe/date coverage may differ",
        })

    hard_fail = any(
        (r["key_null_rows"] != 0 or r["duplicate_keys"] != 0 or r["offyear_rows"] != 0)
        for r in intrinsic_rows
    )
    status = "FAIL" if hard_fail else "PASS_WITH_SCOPE_LIMITATION"

    lines = [
        "# RAW / Adjusted Daily Price Quality Audit",
        "",
        "Status: **" + status + "**",
        "",
        "Scope: targeted intrinsic quality checks for yearly RAW and adjusted daily price parquet files.",
        "This task does not validate corporate-action economics or decide whether RAW and adjusted universes must be identical.",
        "",
        "## Intrinsic file checks",
        "",
        "| Kind | Year | Rows | Unique tickers | Numeric-stock rows | Key-null rows | Duplicate (date,stock_id) | Off-year rows | open null | high/max null | low/min null | close null |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in intrinsic_rows:
        lines.append(
            "| {kind} | {year} | {rows:,} | {unique_tickers:,} | {numeric_stock_rows:,} | {key_null_rows} | {duplicate_keys} | {offyear_rows} | {open_null} | {max_null} | {min_null} | {close_null} |".format(**r)
        )

    lines += [
        "",
        "## Numeric 4-digit stock key overlap",
        "",
        "This table is descriptive. Differences can be legitimate because the two coordinates may have different historical coverage/universe rules.",
        "",
        "| Year | RAW keys | ADJ keys | Intersection | ADJ keys missing RAW | RAW keys missing ADJ |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for r in compare_rows:
        lines.append(
            f"| {r['year']} | {r['raw_numeric_keys']} | {r['adj_numeric_keys']} | {r['intersection']} | {r['adj_missing_raw']} | {r['raw_missing_adj']} |"
        )

    lines += [
        "",
        "## Hard-gate definition for this task",
        "",
        "- key-null rows must be 0",
        "- duplicate (date, stock_id) rows must be 0",
        "- yearly files must not contain off-year dates",
        "",
        "Price null/nonpositive counts are reported separately and require semantic interpretation before becoming hard failures.",
        "RAW/ADJ key-set mismatch is not automatically a failure; execution eligibility is governed by the frozen historical-eligibility gate.",
        "",
        "## Next small task",
        "",
        "If intrinsic keys pass, audit price-value validity and RAW/ADJ overlap semantics on the eligible stock-day denominator before moving to reference/fundamental quality checks.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
