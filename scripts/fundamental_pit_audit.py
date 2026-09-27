#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import pandas as pd

SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/FUNDAMENTAL_PIT_AUDIT.md"))

SPECS = {
    "financials": {
        "path": "fundamentals/financials.parquet",
        "keys": ["stock_id", "date", "type"],
        "relation": "available_on_or_after_period",
    },
    "month_revenue": {
        "path": "fundamentals/month_revenue.parquet",
        "keys": ["stock_id", "date"],
        "relation": "available_on_or_after_period",
    },
    "margin": {
        "path": "fundamentals/margin.parquet",
        "keys": ["stock_id", "date"],
        "relation": "available_same_date",
    },
    "dividend": {
        "path": "fundamentals/dividend.parquet",
        "keys": ["stock_id", "date"],
        "relation": "announcement_may_precede_event",
    },
}

def main() -> None:
    results = []
    hard_fail = False

    for name, spec in SPECS.items():
        path = SOURCE_ROOT / spec["path"]
        if not path.exists():
            raise SystemExit("BLOCKED: missing " + str(path))

        df = pd.read_parquet(path)
        for c in ("date", "available_date"):
            if c not in df.columns:
                raise SystemExit(f"BLOCKED: {name} missing required column {c}")
            df[c] = pd.to_datetime(df[c], errors="coerce")

        if "stock_id" not in df.columns:
            raise SystemExit(f"BLOCKED: {name} missing stock_id")
        df["stock_id"] = df["stock_id"].astype(str)

        keys = spec["keys"]
        missing_key_cols = [c for c in keys if c not in df.columns]
        if missing_key_cols:
            raise SystemExit(f"BLOCKED: {name} missing key columns {missing_key_cols}")

        key_null = int(df[keys].isna().any(axis=1).sum())
        duplicates = int(df.duplicated(keys).sum())
        available_null = int(df["available_date"].isna().sum())
        date_null = int(df["date"].isna().sum())
        numeric_ids = int(df["stock_id"].str.fullmatch(r"[1-9]\d{3}", na=False).sum())

        before = int(
            (df["available_date"].notna() & df["date"].notna() & (df["available_date"] < df["date"])).sum()
        )
        after = int(
            (df["available_date"].notna() & df["date"].notna() & (df["available_date"] > df["date"])).sum()
        )
        same = int(
            (df["available_date"].notna() & df["date"].notna() & (df["available_date"] == df["date"])).sum()
        )

        relation_fail = 0
        if spec["relation"] == "available_on_or_after_period":
            relation_fail = before
        elif spec["relation"] == "available_same_date":
            relation_fail = before + after

        type_empty = 0
        if name == "financials":
            type_empty = int(df["type"].fillna("").astype(str).str.strip().eq("").sum())

        this_fail = key_null + duplicates + available_null + date_null + relation_fail + type_empty
        if this_fail:
            hard_fail = True

        results.append({
            "name": name,
            "rows": len(df),
            "numeric_ids": numeric_ids,
            "key_null": key_null,
            "duplicates": duplicates,
            "date_null": date_null,
            "available_null": available_null,
            "available_before": before,
            "available_same": same,
            "available_after": after,
            "relation_fail": relation_fail,
            "type_empty": type_empty,
        })

    status = "FAIL" if hard_fail else "PASS_WITH_LIMITATIONS"

    lines = [
        "# Fundamental PIT Audit",
        "",
        "Status: **" + status + "**",
        "",
        "Scope: PIT-bearing fundamental datasets only. Checks logical-key uniqueness, temporal completeness, and the dataset-specific availability rule used by the source builder.",
        "",
        "| Dataset | Rows | Numeric-ID rows | Key-null | Duplicate logical keys | date null | available_date null | avail < date | avail = date | avail > date | Rule failures |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        lines.append(
            f"| {r['name']} | {r['rows']:,} | {r['numeric_ids']:,} | {r['key_null']:,} | {r['duplicates']:,} | "
            f"{r['date_null']:,} | {r['available_null']:,} | {r['available_before']:,} | "
            f"{r['available_same']:,} | {r['available_after']:,} | {r['relation_fail']:,} |"
        )

    fin = next(r for r in results if r["name"] == "financials")
    div = next(r for r in results if r["name"] == "dividend")

    lines += [
        "",
        "## Dataset-specific rules",
        "",
        "- financials: logical key is (stock_id,date,type); available_date must not precede period date.",
        "- month_revenue: logical key is (stock_id,date); available_date must not precede period date.",
        "- margin: logical key is (stock_id,date); source convention requires available_date = date for T-close -> T+1-open use.",
        "- dividend: available_date is intended to be the announcement/known date and may legitimately precede the ex/event date; ordering is reported but not hard-failed.",
        "",
        f"Financial rows with blank type: {fin['type_empty']:,}.",
        f"Dividend rows where available_date = event date: {div['available_same']:,}; these can include fallback cases and must not automatically be treated as announcement-date evidence.",
        "",
        "## Known limitations retained from source semantics",
        "",
        "- Financial-statement available dates use statutory deadline approximations; some financial institutions can report later, so financial-stock PIT use needs an additional conservative rule or exclusion.",
        "- Historical financial values may reflect vendor/current revisions rather than the exact originally published figures.",
        "- Dividend rows whose announcement date was unavailable may have fallen back to event date; such rows are not safe as announcement-timing features without explicit provenance.",
        "",
        "## Next small task",
        "",
        "Freeze the Phase-1 data audit summary and explicit limitations, then move to systematic execution-coordinate replacement without inspecting strategy performance.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
