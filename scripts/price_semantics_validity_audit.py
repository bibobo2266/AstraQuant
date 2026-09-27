#!/usr/bin/env python3
from __future__ import annotations

import os
import re
from pathlib import Path

import pandas as pd

SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/PRICE_SEMANTICS_VALIDITY_AUDIT.md"))

KEYS = ["date", "stock_id"]
OHLC = ["open", "max", "min", "close"]

def year_from_name(path: Path) -> int:
    m = re.search(r"(20\d{2})", path.name)
    if not m:
        raise ValueError(path.name)
    return int(m.group(1))

def normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["stock_id"] = df["stock_id"].astype(str)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for c in OHLC:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

def valid_ohlc(df: pd.DataFrame) -> pd.Series:
    positive = (df[OHLC] > 0).all(axis=1)
    geom = (
        (df["max"] >= df[["open", "close", "min"]].max(axis=1))
        & (df["min"] <= df[["open", "close", "max"]].min(axis=1))
    )
    return positive & geom

def main() -> None:
    raw_files = sorted((SOURCE_ROOT / "raw").glob("prices_raw_*.parquet"))
    adj_files = sorted((SOURCE_ROOT / "adj").glob("prices_adj_*.parquet"))
    trad_path = SOURCE_ROOT / "reference" / "tradability.parquet"
    gate_path = SOURCE_ROOT / "reference" / "EXECUTION_READINESS_GATE.csv"
    if not raw_files or not adj_files or not trad_path.exists():
        raise SystemExit("BLOCKED: required price/tradability source missing")

    trad = pd.read_parquet(
        trad_path,
        columns=["date", "stock_id", "valid_ohlc", "buy_blocked", "sell_blocked", "observed_trade", "reason"],
    )
    trad["stock_id"] = trad["stock_id"].astype(str)
    trad["date"] = pd.to_datetime(trad["date"], errors="coerce")

    rows = []
    hard_fail = False
    for rp in raw_files:
        y = year_from_name(rp)
        raw = normalize(pd.read_parquet(rp, columns=KEYS + OHLC))
        raw = raw[raw["stock_id"].str.fullmatch(r"[1-9]\d{3}", na=False)].copy()
        raw["calc_valid"] = valid_ohlc(raw)
        raw["any_ohlc_null"] = raw[OHLC].isna().any(axis=1)

        ty = trad[trad["date"].dt.year.eq(y)].copy()
        m = raw.merge(ty, on=KEYS, how="left", validate="one_to_one", indicator=True)
        trad_missing = int((m["_merge"] != "both").sum())
        disagreement = int((m["_merge"].eq("both") & (m["calc_valid"] != m["valid_ohlc"].fillna(False))).sum())
        null_rows = int(m["any_ohlc_null"].sum())
        null_not_buy_blocked = int((m["any_ohlc_null"] & ~m["buy_blocked"].fillna(False)).sum())
        null_not_sell_blocked = int((m["any_ohlc_null"] & ~m["sell_blocked"].fillna(False)).sum())
        invalid = int((~m["calc_valid"]).sum())
        invalid_not_buy_blocked = int((~m["calc_valid"] & ~m["buy_blocked"].fillna(False)).sum())
        if trad_missing or disagreement or null_not_buy_blocked or null_not_sell_blocked or invalid_not_buy_blocked:
            hard_fail = True
        rows.append({
            "year": y,
            "raw_numeric_rows": len(m),
            "raw_null_ohlc": null_rows,
            "calc_invalid_ohlc": invalid,
            "tradability_missing": trad_missing,
            "validity_disagreement": disagreement,
            "null_not_buy_blocked": null_not_buy_blocked,
            "null_not_sell_blocked": null_not_sell_blocked,
            "invalid_not_buy_blocked": invalid_not_buy_blocked,
        })

    adj_rows = []
    for ap in adj_files:
        y = year_from_name(ap)
        adj = normalize(pd.read_parquet(ap, columns=KEYS + OHLC))
        adj = adj[adj["stock_id"].str.fullmatch(r"[1-9]\d{3}", na=False)].copy()
        nulls = int(adj[OHLC].isna().any(axis=1).sum())
        invalid = int((~valid_ohlc(adj)).sum())
        if nulls or invalid:
            hard_fail = True
        adj_rows.append({"year": y, "rows": len(adj), "null_ohlc": nulls, "invalid_ohlc": invalid})

    gate_detail = "NOT_READ"
    if gate_path.exists():
        gate = pd.read_csv(gate_path)
        hit = gate[gate["dataset"].astype(str).eq("raw_history")]
        if len(hit):
            gate_detail = str(hit.iloc[0]["status"]) + " — " + str(hit.iloc[0]["detail"])

    status = "FAIL" if hard_fail else "PASS"

    lines = [
        "# Price Semantics Validity Audit",
        "",
        "Status: **" + status + "**",
        "",
        "Purpose: verify that RAW price anomalies are explicitly blocked by the tradability layer and that adjusted OHLC is internally valid.",
        "",
        "Frozen execution-readiness gate: " + gate_detail,
        "",
        "## RAW vs tradability",
        "",
        "| Year | Numeric RAW rows | Any OHLC null | Calculated invalid OHLC | Missing tradability row | Validity disagreement | Null but buy allowed | Null but sell allowed | Invalid but buy allowed |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['year']} | {r['raw_numeric_rows']:,} | {r['raw_null_ohlc']:,} | {r['calc_invalid_ohlc']:,} | "
            f"{r['tradability_missing']:,} | {r['validity_disagreement']:,} | {r['null_not_buy_blocked']:,} | "
            f"{r['null_not_sell_blocked']:,} | {r['invalid_not_buy_blocked']:,} |"
        )

    lines += [
        "",
        "## Adjusted OHLC intrinsic validity",
        "",
        "| Year | Numeric ADJ rows | Any OHLC null | Invalid OHLC |",
        "|---:|---:|---:|---:|",
    ]
    for r in adj_rows:
        lines.append(f"| {r['year']} | {r['rows']:,} | {r['null_ohlc']:,} | {r['invalid_ohlc']:,} |")

    lines += [
        "",
        "## Gate",
        "",
        "PASS requires:",
        "- every numeric RAW row has a matching tradability row;",
        "- independently calculated RAW OHLC validity agrees with tradability.valid_ohlc;",
        "- RAW null/invalid OHLC rows are blocked from buying (and null rows are blocked from selling);",
        "- adjusted numeric-stock OHLC has no null or invalid geometry in this scope.",
        "",
        "This does not yet prove corporate-action accounting correctness or PIT safety of adjusted history.",
        "",
        "## Next small task",
        "",
        "Audit reference/PIT datasets (industry, corporate actions, tradability) for key uniqueness, required temporal fields, nulls, and ordering constraints.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
