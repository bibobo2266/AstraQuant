#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/CORPORATE_ACTION_SOURCE_PROFILE.md"))


def main() -> None:
    path = SOURCE_ROOT / "reference" / "corporate_actions_ledger.parquet"
    if not path.exists():
        raise SystemExit("BLOCKED: corporate_actions_ledger.parquet missing")

    df = pd.read_parquet(path)
    required = {
        "stock_id", "event_date", "known_date", "event_type", "cash_per_share",
        "share_multiplier", "rights_ratio", "subscription_price", "source_name",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise SystemExit("BLOCKED: missing required columns: " + ",".join(missing))

    df["stock_id"] = df["stock_id"].astype(str)
    df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce")
    df["known_date"] = pd.to_datetime(df["known_date"], errors="coerce")

    for c in ("cash_per_share", "share_multiplier", "rights_ratio", "subscription_price"):
        df[c] = pd.to_numeric(df[c], errors="coerce")

    grouped = []
    for event_type, g in df.groupby(df["event_type"].fillna("UNKNOWN").astype(str), dropna=False):
        grouped.append({
            "event_type": event_type,
            "rows": len(g),
            "ids": g["stock_id"].nunique(),
            "known_date": int(g["known_date"].notna().sum()),
            "cash": int(g["cash_per_share"].notna().sum()),
            "share_multiplier": int(g["share_multiplier"].notna().sum()),
            "rights_ratio": int(g["rights_ratio"].notna().sum()),
            "subscription_price": int(g["subscription_price"].notna().sum()),
        })

    grouped.sort(key=lambda r: (-r["rows"], r["event_type"]))

    event_date_null = int(df["event_date"].isna().sum())
    known_date_null = int(df["known_date"].isna().sum())
    known_after_event = int(
        (df["known_date"].notna() & df["event_date"].notna() & (df["known_date"] > df["event_date"])).sum()
    )
    payment_cols = [c for c in df.columns if "payment" in c.lower() or "pay_date" in c.lower()]
    record_cols = [c for c in df.columns if "record" in c.lower()]

    lines = [
        "# Corporate-Action Source Profile",
        "",
        "Status: **DONE — semantic inventory**",
        "",
        "Purpose: profile the frozen canonical corporate-action ledger before implementing non-cash mutations or source-backed CA replay.",
        "",
        f"- rows: {len(df):,}",
        f"- unique stock IDs: {df['stock_id'].nunique():,}",
        f"- event_date null: {event_date_null:,}",
        f"- known_date null: {known_date_null:,}",
        f"- known_date > event_date: {known_after_event:,}",
        f"- payment-date-like columns present: {', '.join(payment_cols) if payment_cols else 'NONE'}",
        f"- record-date-like columns present: {', '.join(record_cols) if record_cols else 'NONE'}",
        "",
        "## Event-type field coverage",
        "",
        "| Event type | Rows | IDs | known_date populated | cash/share | share multiplier | rights ratio | subscription price |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in grouped:
        lines.append(
            f"| {r['event_type']} | {r['rows']:,} | {r['ids']:,} | {r['known_date']:,} | "
            f"{r['cash']:,} | {r['share_multiplier']:,} | {r['rights_ratio']:,} | {r['subscription_price']:,} |"
        )

    lines += [
        "",
        "## Accounting implications",
        "",
        "- The ledger can support event-date/economic-event replay only for fields actually populated by event type.",
        "- Unknown known_date remains a PIT limitation and is never inferred.",
        "- If no payment-date field exists, a cash-dividend source replay can accrue a receivable at the effective/ex date but cannot move it to settled cash on a guessed payment date.",
        "- Non-cash share mutations must be implemented only for event types with explicit, interpretable share-mutation fields.",
        "- Event types with insufficient economic fields remain accounting-limited rather than reverse-engineered from adjusted prices.",
        "",
        "## Next small task",
        "",
        "Implement generic share-multiplier mutation with explicit corporate-action provenance, then source-test only event types whose ledger fields support that mutation.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
