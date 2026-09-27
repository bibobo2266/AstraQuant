#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import pandas as pd

SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/PIT_REFERENCE_AUDIT.md"))

def bcount(s: pd.Series) -> int:
    return int(s.fillna(False).astype(bool).sum())

def main() -> None:
    ref = SOURCE_ROOT / "reference"
    ca_p = ref / "corporate_actions_ledger.parquet"
    pit_p = ref / "industry_pit.parquet"
    snap_p = ref / "industry_monthly_snapshots.parquet"
    trad_p = ref / "tradability.parquet"
    for p in (ca_p, pit_p, snap_p, trad_p):
        if not p.exists():
            raise SystemExit("BLOCKED: missing " + str(p))

    ca = pd.read_parquet(ca_p)
    ca["stock_id"] = ca["stock_id"].astype(str)
    ca["event_date"] = pd.to_datetime(ca["event_date"], errors="coerce")
    ca["known_date"] = pd.to_datetime(ca["known_date"], errors="coerce")
    ca_dup = int(ca.duplicated(["stock_id","event_date","event_type","source_name"]).sum())
    ca_event_null = int(ca["event_date"].isna().sum())
    ca_known_null = int(ca["known_date"].isna().sum())
    ca_known_after_event = int((ca["known_date"].notna() & ca["event_date"].notna() & (ca["known_date"] > ca["event_date"])).sum())
    ca_source_missing = int(
        ca["source_name"].fillna("").astype(str).str.strip().eq("").sum()
    )

    pit = pd.read_parquet(pit_p)
    pit["stock_id"] = pit["stock_id"].astype(str)
    pit["valid_from"] = pd.to_datetime(pit["valid_from"], errors="coerce")
    pit["valid_to"] = pd.to_datetime(pit["valid_to"], errors="coerce")
    pit_dup = int(pit.duplicated(["stock_id","valid_from"]).sum())
    pit_from_null = int(pit["valid_from"].isna().sum())
    pit_bad_range = int((pit["valid_to"].notna() & (pit["valid_to"] < pit["valid_from"])).sum())
    pit_industry_empty = int(pit["industry"].fillna("").astype(str).str.strip().eq("").sum())
    pit_overlap = 0
    for _, g in pit.sort_values(["stock_id","valid_from"]).groupby("stock_id", sort=False):
        prev_to = None
        for r in g.itertuples(index=False):
            vf = r.valid_from
            vt = r.valid_to
            if prev_to is not None and pd.notna(vf) and vf <= prev_to:
                pit_overlap += 1
            if pd.isna(vt):
                prev_to = pd.Timestamp.max.normalize()
            else:
                prev_to = vt

    snap = pd.read_parquet(snap_p)
    snap["stock_id"] = snap["stock_id"].astype(str)
    snap["available_date"] = pd.to_datetime(snap["available_date"], errors="coerce")
    snap_key_null = int(snap[["stock_id","available_date"]].isna().any(axis=1).sum())
    snap_dup = int(snap.duplicated(["stock_id","available_date"]).sum())
    snap_industry_empty = int(snap["industry"].fillna("").astype(str).str.strip().eq("").sum())

    trad = pd.read_parquet(trad_p)
    trad["stock_id"] = trad["stock_id"].astype(str)
    trad["date"] = pd.to_datetime(trad["date"], errors="coerce")
    trad_key_null = int(trad[["stock_id","date"]].isna().any(axis=1).sum())
    trad_dup = int(trad.duplicated(["stock_id","date"]).sum())
    not_obs = ~trad["observed_trade"].fillna(False).astype(bool)
    invalid = ~trad["valid_ohlc"].fillna(False).astype(bool)
    trad_notobs_buy_allowed = int((not_obs & ~trad["buy_blocked"].fillna(False).astype(bool)).sum())
    trad_notobs_sell_allowed = int((not_obs & ~trad["sell_blocked"].fillna(False).astype(bool)).sum())
    trad_invalid_buy_allowed = int((invalid & ~trad["buy_blocked"].fillna(False).astype(bool)).sum())

    hard_fail = any([
        ca_dup, ca_event_null,
        pit_dup, pit_from_null, pit_bad_range, pit_industry_empty, pit_overlap,
        snap_key_null, snap_dup, snap_industry_empty,
        trad_key_null, trad_dup, trad_notobs_buy_allowed, trad_notobs_sell_allowed, trad_invalid_buy_allowed,
    ])
    status = "FAIL" if hard_fail else "PASS_WITH_LIMITATIONS"

    lines = [
        "# PIT / Reference Data Audit",
        "",
        "Status: **" + status + "**",
        "",
        "Scope: structural and temporal-integrity checks for corporate actions, PIT industry, monthly industry snapshots, and tradability.",
        "This audit does not infer unknown dates or backfill missing historical industry classifications.",
        "",
        "## Corporate actions ledger",
        "",
        f"- rows: {len(ca):,}",
        f"- duplicate canonical keys (stock_id,event_date,event_type,source_name): {ca_dup:,}",
        f"- null event_date: {ca_event_null:,}",
        f"- null/unknown known_date: {ca_known_null:,}",
        f"- known_date later than event_date: {ca_known_after_event:,} (reported, not automatically a failure)",
        f"- blank source_name: {ca_source_missing:,} (reported limitation)",
        "",
        "Unknown known_date remains UNKNOWN and must not be guessed. Rows only become PIT-usable when their availability semantics are explicit.",
        "",
        "## PIT industry intervals",
        "",
        f"- rows: {len(pit):,}",
        f"- IDs: {pit['stock_id'].nunique():,}",
        f"- duplicate (stock_id,valid_from): {pit_dup:,}",
        f"- null valid_from: {pit_from_null:,}",
        f"- invalid valid_to < valid_from: {pit_bad_range:,}",
        f"- overlapping intervals: {pit_overlap:,}",
        f"- blank industry: {pit_industry_empty:,}",
        "",
        "Historical dates before first known industry remain uncovered by design; no backward fill is permitted.",
        "",
        "## Industry monthly snapshots",
        "",
        f"- rows: {len(snap):,}",
        f"- key-null rows: {snap_key_null:,}",
        f"- duplicate (stock_id,available_date): {snap_dup:,}",
        f"- blank industry: {snap_industry_empty:,}",
        "",
        "## Tradability",
        "",
        f"- rows: {len(trad):,}",
        f"- duplicate (stock_id,date): {trad_dup:,}",
        f"- key-null rows: {trad_key_null:,}",
        f"- observed_trade=False but buy allowed: {trad_notobs_buy_allowed:,}",
        f"- observed_trade=False but sell allowed: {trad_notobs_sell_allowed:,}",
        f"- valid_ohlc=False but buy allowed: {trad_invalid_buy_allowed:,}",
        "",
        "## Hard gate",
        "",
        "Hard failures are duplicate/null temporal keys, overlapping PIT intervals, invalid interval ordering, empty industry labels, or tradability states that allow execution on non-observed/invalid rows.",
        "",
        "Corporate-action known_date gaps and late-known events are surfaced as limitations rather than silently repaired.",
        "",
        "## Next small task",
        "",
        "Audit PIT-bearing fundamental datasets (financials, monthly revenue, margin, dividend) for available_date nulls, ordering, duplicate logical keys, and impossible availability-before-period relationships.",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
