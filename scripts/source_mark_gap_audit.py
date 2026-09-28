#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from astraquant.data.corporate_actions import build_finmind_normalized_actions

SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/SOURCE_MARK_GAP_AUDIT.md"))
TICKER = os.environ.get("TICKER", "8271")
TARGET = pd.Timestamp(os.environ.get("TARGET_DATE", "2016-09-13")).normalize()


def main() -> None:
    raw_parts = []
    for year in sorted({TARGET.year - 1, TARGET.year, TARGET.year + 1}):
        p = SOURCE_ROOT / "raw" / f"prices_raw_{year}.parquet"
        if p.exists():
            raw_parts.append(pd.read_parquet(
                p,
                columns=["date", "stock_id", "open", "max", "min", "close"],
            ))
    if not raw_parts:
        raise SystemExit("BLOCKED: no RAW files around target")

    raw = pd.concat(raw_parts, ignore_index=True)
    raw["stock_id"] = raw["stock_id"].astype(str)
    raw["date"] = pd.to_datetime(raw["date"], errors="coerce").dt.normalize()
    raw = raw[raw["stock_id"].eq(TICKER)].sort_values("date")

    trad = pd.read_parquet(
        SOURCE_ROOT / "reference" / "tradability.parquet",
        columns=[
            "date", "stock_id", "observed_trade", "valid_ohlc",
            "buy_blocked", "sell_blocked", "reason",
        ],
    )
    trad["stock_id"] = trad["stock_id"].astype(str)
    trad["date"] = pd.to_datetime(trad["date"], errors="coerce").dt.normalize()
    trad = trad[trad["stock_id"].eq(TICKER)].sort_values("date")

    ca = pd.read_parquet(
        SOURCE_ROOT / "reference" / "corporate_actions_ledger.parquet",
        columns=[
            "stock_id", "event_date", "event_type", "cash_per_share",
            "share_multiplier", "source_name",
        ],
    )
    ca["stock_id"] = ca["stock_id"].astype(str)
    ca["event_date"] = pd.to_datetime(ca["event_date"], errors="coerce").dt.normalize()
    ca = ca[
        ca["stock_id"].eq(TICKER)
        & ca["event_date"].between(TARGET - pd.Timedelta(days=60), TARGET + pd.Timedelta(days=60))
    ].sort_values("event_date")

    dividend = pd.read_parquet(SOURCE_ROOT / "fundamentals" / "dividend.parquet")
    normalized = [
        a for a in build_finmind_normalized_actions(dividend)
        if a.ticker == TICKER
        and TARGET.date() - pd.Timedelta(days=60) <= pd.Timestamp(a.effective_date)
        and pd.Timestamp(a.effective_date) <= TARGET.date() + pd.Timedelta(days=60)
    ]

    target_trad = trad[trad["date"].eq(TARGET)]
    prev_raw = raw[raw["date"].lt(TARGET)].tail(5)
    next_raw = raw[raw["date"].gt(TARGET)].head(5)
    local_trad = trad[
        trad["date"].between(TARGET - pd.Timedelta(days=15), TARGET + pd.Timedelta(days=15))
    ]

    lines = [
        "# Source RAW Mark Gap Audit",
        "",
        f"- ticker: {TICKER}",
        f"- target session: {TARGET.date()}",
        "",
        "## Target tradability",
        "",
    ]
    if target_trad.empty:
        lines.append("- no tradability row")
    else:
        r = target_trad.iloc[0]
        lines += [
            f"- observed_trade: {bool(r['observed_trade'])}",
            f"- valid_ohlc: {bool(r['valid_ohlc'])}",
            f"- buy_blocked: {bool(r['buy_blocked'])}",
            f"- sell_blocked: {bool(r['sell_blocked'])}",
            f"- reason: {r['reason']}",
        ]

    lines += [
        "",
        "## Previous RAW observations",
        "",
        "| Date | Open | High | Low | Close |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in prev_raw.itertuples(index=False):
        lines.append(f"| {r.date.date()} | {r.open} | {r.max} | {r.min} | {r.close} |")

    lines += [
        "",
        "## Next RAW observations",
        "",
        "| Date | Open | High | Low | Close |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in next_raw.itertuples(index=False):
        lines.append(f"| {r.date.date()} | {r.open} | {r.max} | {r.min} | {r.close} |")

    lines += [
        "",
        "## Local tradability sequence",
        "",
        "| Date | Observed | Valid | Buy blocked | Sell blocked | Reason |",
        "|---|---|---|---|---|---|",
    ]
    for r in local_trad.itertuples(index=False):
        lines.append(
            f"| {r.date.date()} | {bool(r.observed_trade)} | {bool(r.valid_ohlc)} | "
            f"{bool(r.buy_blocked)} | {bool(r.sell_blocked)} | {r.reason} |"
        )

    lines += [
        "",
        "## Corporate actions ±60 days",
        "",
        "| Event date | Type | Cash/share | Share multiplier | Source |",
        "|---|---|---:|---:|---|",
    ]
    for r in ca.itertuples(index=False):
        lines.append(
            f"| {r.event_date.date()} | {r.event_type} | {r.cash_per_share} | "
            f"{r.share_multiplier} | {r.source_name} |"
        )
    if ca.empty:
        lines.append("| — | none | — | — | — |")

    lines += [
        "",
        "## Normalized FinMind actions ±60 days",
        "",
        "| Effective date | Kind | Cash/share | Share multiplier | Known at | Payment at |",
        "|---|---|---:|---:|---|---|",
    ]
    for a in normalized:
        lines.append(
            f"| {a.effective_date} | {a.kind.value} | {a.cash_per_share} | "
            f"{a.share_multiplier} | {a.known_at} | {a.payment_at} |"
        )
    if not normalized:
        lines.append("| — | none | — | — | — | — |")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
