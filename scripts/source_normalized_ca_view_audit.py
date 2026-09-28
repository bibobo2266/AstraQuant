#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from astraquant.data.corporate_actions import (
    build_finmind_normalized_actions,
    normalized_actions_frame,
)

SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/SOURCE_NORMALIZED_CA_VIEW_AUDIT.md"))


def main() -> None:
    dividend_path = SOURCE_ROOT / "fundamentals" / "dividend.parquet"
    ledger_path = SOURCE_ROOT / "reference" / "corporate_actions_ledger.parquet"
    if not dividend_path.exists() or not ledger_path.exists():
        raise SystemExit("BLOCKED: required frozen source files are missing")

    dividend = pd.read_parquet(dividend_path)
    actions = build_finmind_normalized_actions(dividend)
    frame = normalized_actions_frame(actions)

    if frame.empty:
        raise SystemExit("FAIL: normalized corporate-action view is empty")

    logical_key = ["stock_id", "effective_date", "event_kind"]
    duplicate_rows = int(frame.duplicated(logical_key, keep=False).sum())
    duplicate_groups = int(
        frame.loc[frame.duplicated(logical_key, keep=False)]
        .groupby(logical_key)
        .ngroups
    )

    cash = frame[frame["event_kind"].eq("CASH_DIVIDEND")].copy()
    stock = frame[frame["event_kind"].eq("STOCK_DIVIDEND")].copy()

    bad_cash = int(
        (pd.to_numeric(cash["cash_per_share"], errors="coerce").fillna(0) <= 0).sum()
    )
    bad_mult = int(
        (pd.to_numeric(stock["share_multiplier"], errors="coerce").fillna(0) <= 1).sum()
    )

    known_after_effective = int(
        (
            frame["known_at"].notna()
            & (frame["known_at"].dt.normalize() > frame["effective_date"])
        ).sum()
    )
    payment_before_effective = int(
        (
            cash["payment_at"].notna()
            & (cash["payment_at"].dt.normalize() < cash["effective_date"])
        ).sum()
    )

    ledger = pd.read_parquet(
        ledger_path,
        columns=[
            "stock_id", "event_date", "event_type", "source_name",
        ],
    ).copy()
    ledger["stock_id"] = ledger["stock_id"].astype(str)
    ledger["event_date"] = pd.to_datetime(
        ledger["event_date"], errors="coerce"
    ).dt.normalize()
    official = ledger[ledger["event_type"].astype(str).eq("ex_right_dividend")].copy()

    component_counts = (
        frame.groupby(["stock_id", "effective_date"])
        .size()
        .rename("normalized_components")
        .reset_index()
    )
    joined = official.merge(
        component_counts,
        left_on=["stock_id", "event_date"],
        right_on=["stock_id", "effective_date"],
        how="left",
    )
    joined["normalized_components"] = joined["normalized_components"].fillna(0).astype(int)

    twse = joined[joined["source_name"].astype(str).str.contains("TWSE", case=False, na=False)]
    tpex = joined[joined["source_name"].astype(str).str.contains("TPEx", case=False, na=False)]

    def matched_count(df: pd.DataFrame) -> int:
        return int(df["normalized_components"].gt(0).sum())

    hard_fail = bool(duplicate_rows or bad_cash or bad_mult or payment_before_effective)
    status = "FAIL" if hard_fail else "PASS_WITH_JOIN_LIMITATIONS"

    lines = [
        "# Source Normalized Corporate-Action View Audit",
        "",
        f"Status: **{status}**",
        "",
        "Purpose: validate the AstraQuant-side normalized FinMind cash/stock dividend view against the frozen read-only source before integrating it into strategy/accounting replay.",
        "",
        "## Normalized view",
        "",
        f"- normalized component rows: {len(frame):,}",
        f"- cash-dividend components: {len(cash):,}",
        f"- stock-dividend components: {len(stock):,}",
        f"- unique stock IDs: {frame['stock_id'].nunique():,}",
        f"- logical duplicate rows (stock/effective-date/kind): {duplicate_rows:,}",
        f"- logical duplicate groups: {duplicate_groups:,}",
        f"- nonpositive cash components: {bad_cash:,}",
        f"- invalid stock multipliers (<= 1): {bad_mult:,}",
        "",
        "## PIT/payment fields",
        "",
        f"- components with known_at: {int(frame['known_at'].notna().sum()):,}",
        f"- known_at after effective date: {known_after_effective:,}",
        f"- cash components with payment_at: {int(cash['payment_at'].notna().sum()):,}",
        f"- payment_at before effective date: {payment_before_effective:,}",
        "",
        "## Official-date linkage (date identity only; not yet an economic merge)",
        "",
        f"- TWSE official ex_right_dividend rows: {len(twse):,}",
        f"- TWSE rows with >=1 normalized FinMind component on same stock/ex-date: {matched_count(twse):,}",
        f"- TPEx official ex_right_dividend rows: {len(tpex):,}",
        f"- TPEx rows with >=1 normalized FinMind component on same stock/ex-date: {matched_count(tpex):,}",
        "",
        "## Semantics",
        "",
        "- Cash uses CashExDividendTradingDate and opening/pre-event share entitlement.",
        "- Stock uses StockExDividendTradingDate and FinMind currency-per-share conversion to share_multiplier.",
        "- CashEarningsDistribution and CashStatutorySurplus are additive when present.",
        "- StockEarningsDistribution and StockStatutorySurplus are additive when present.",
        "- Payment dates come from CashDividendPaymentDate; no guessed settlement date is introduced.",
        "- Official-event linkage above is diagnostic only. It does not silently replace or merge source rows.",
        "",
        "## PIT exceptions",
        "",
    ]
    late = frame[
        frame["known_at"].notna()
        & (frame["known_at"].dt.normalize() > frame["effective_date"])
    ].copy()
    if late.empty:
        lines.append("- none")
    else:
        for row in late.itertuples(index=False):
            lines.append(
                f"- {row.stock_id} {pd.Timestamp(row.effective_date).date()} "
                f"{row.event_kind} known_at={pd.Timestamp(row.known_at).isoformat()}"
            )
    lines += [
        "",
        "## Gate",
        "",
        "The view is eligible for the next integration step only if logical keys are unique, economic values are valid, and no payment precedes its effective date. Date-join misses remain explicit source limitations rather than guessed matches.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if hard_fail:
        raise SystemExit("FAIL: normalized corporate-action source gate failed")


if __name__ == "__main__":
    main()
