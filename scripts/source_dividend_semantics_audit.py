#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/SOURCE_DIVIDEND_SEMANTICS_AUDIT.md"))
DIVIDEND_PATH = SOURCE_ROOT / "fundamentals" / "dividend.parquet"
LEDGER_PATH = SOURCE_ROOT / "reference" / "corporate_actions_ledger.parquet"


def dt(series):
    return pd.to_datetime(series, errors="coerce").dt.normalize()


def num(series, index):
    return pd.to_numeric(series, errors="coerce") if series is not None else pd.Series(float("nan"), index=index)


def main():
    if not DIVIDEND_PATH.exists():
        raise SystemExit(f"BLOCKED: missing {DIVIDEND_PATH}")
    if not LEDGER_PATH.exists():
        raise SystemExit(f"BLOCKED: missing {LEDGER_PATH}")

    div = pd.read_parquet(DIVIDEND_PATH).copy()
    div["stock_id"] = div["stock_id"].astype(str)
    if "date" not in div.columns:
        raise SystemExit("BLOCKED: dividend.parquet missing date")

    source_date = dt(div["date"])
    cash_ex = dt(div["CashExDividendTradingDate"]) if "CashExDividendTradingDate" in div.columns else pd.Series(pd.NaT, index=div.index)
    stock_ex = dt(div["StockExDividendTradingDate"]) if "StockExDividendTradingDate" in div.columns else pd.Series(pd.NaT, index=div.index)

    cash_mask = cash_ex.notna()
    stock_mask = stock_ex.notna()
    cash_same = int((source_date[cash_mask] == cash_ex[cash_mask]).sum())
    stock_same = int((source_date[stock_mask] == stock_ex[stock_mask]).sum())

    cash_earn = num(div["CashEarningsDistribution"] if "CashEarningsDistribution" in div.columns else None, div.index)
    cash_stat = num(div["CashStatutorySurplus"] if "CashStatutorySurplus" in div.columns else None, div.index)
    stock_earn = num(div["StockEarningsDistribution"] if "StockEarningsDistribution" in div.columns else None, div.index)
    stock_stat = num(div["StockStatutorySurplus"] if "StockStatutorySurplus" in div.columns else None, div.index)

    def populated(col):
        return int(div[col].notna().sum()) if col in div.columns else 0

    ledger = pd.read_parquet(LEDGER_PATH).copy()
    ledger["stock_id"] = ledger["stock_id"].astype(str)
    ledger["event_date"] = dt(ledger["event_date"])
    ledger["event_type"] = ledger["event_type"].astype(str)
    ledger["source_name"] = ledger["source_name"].astype(str)

    finmind = ledger[
        ledger["event_type"].eq("dividend")
        & ledger["source_name"].str.contains("FinMind", case=False, na=False)
    ].copy()
    twse = ledger[
        ledger["event_type"].eq("ex_right_dividend")
        & ledger["source_name"].str.contains("TWSE", case=False, na=False)
    ].copy()
    tpex = ledger[
        ledger["event_type"].eq("ex_right_dividend")
        & ledger["source_name"].str.contains("TPEx", case=False, na=False)
    ].copy()

    source_keys = pd.DataFrame({
        "stock_id": div["stock_id"],
        "source_date": source_date,
        "cash_ex_date": cash_ex,
        "stock_ex_date": stock_ex,
    })
    cmp = finmind[["stock_id", "event_date"]].merge(
        source_keys,
        left_on=["stock_id", "event_date"],
        right_on=["stock_id", "source_date"],
        how="left",
    )
    cash_known = cmp["cash_ex_date"].notna()
    stock_known = cmp["stock_ex_date"].notna()
    finmind_cash_same = int((cmp.loc[cash_known, "event_date"] == cmp.loc[cash_known, "cash_ex_date"]).sum())
    finmind_stock_same = int((cmp.loc[stock_known, "event_date"] == cmp.loc[stock_known, "stock_ex_date"]).sum())

    def missing_num(frame, col):
        if col not in frame.columns:
            return len(frame)
        return int(pd.to_numeric(frame[col], errors="coerce").isna().sum())

    status = "PASS_WITH_CORRECTIONS_REQUIRED"
    lines = [
        "# Source Dividend Semantics Audit",
        "",
        f"Status: **{status}**",
        "",
        "Purpose: directly inspect the frozen read-only dividend parquet and current corporate-action ledger before any AstraQuant normalization change.",
        "",
        "## Dividend parquet",
        "",
        f"- rows: {len(div):,}",
        f"- columns: {len(div.columns):,}",
        f"- AnnouncementDate populated: {populated('AnnouncementDate'):,}",
        f"- available_date populated: {populated('available_date'):,}",
        f"- CashDividendPaymentDate populated: {populated('CashDividendPaymentDate'):,}",
        f"- CashExDividendTradingDate populated: {populated('CashExDividendTradingDate'):,}",
        f"- StockExDividendTradingDate populated: {populated('StockExDividendTradingDate'):,}",
        "",
        "## Date semantics",
        "",
        f"- rows with CashExDividendTradingDate: {int(cash_mask.sum()):,}",
        f"- source date == CashExDividendTradingDate: {cash_same:,}",
        f"- cash ex-date match rate: {cash_same / max(1, int(cash_mask.sum())):.4%}",
        f"- rows with StockExDividendTradingDate: {int(stock_mask.sum()):,}",
        f"- source date == StockExDividendTradingDate: {stock_same:,}",
        f"- stock ex-date match rate: {stock_same / max(1, int(stock_mask.sum())):.4%}",
        "",
        "## Distribution components",
        "",
        f"- CashEarningsDistribution > 0: {int(cash_earn.fillna(0).gt(0).sum()):,}",
        f"- CashStatutorySurplus > 0: {int(cash_stat.fillna(0).gt(0).sum()):,}",
        f"- rows changed by adding cash statutory surplus: {int(cash_stat.fillna(0).abs().gt(1e-12).sum()):,}",
        f"- StockEarningsDistribution > 0: {int(stock_earn.fillna(0).gt(0).sum()):,}",
        f"- StockStatutorySurplus > 0: {int(stock_stat.fillna(0).gt(0).sum()):,}",
        f"- rows changed by adding stock statutory surplus: {int(stock_stat.fillna(0).abs().gt(1e-12).sum()):,}",
        "",
        "## Current FinMind ledger mapping",
        "",
        f"- FinMind dividend ledger rows: {len(finmind):,}",
        f"- matched rows with cash ex-date available: {int(cash_known.sum()):,}",
        f"- current ledger event_date == cash ex-date: {finmind_cash_same:,}",
        f"- matched rows with stock ex-date available: {int(stock_known.sum()):,}",
        f"- current ledger event_date == stock ex-date: {finmind_stock_same:,}",
        "",
        "## Official ex-right/dividend completeness",
        "",
        f"- TWSE official rows: {len(twse):,}",
        f"- TWSE cash_per_share missing: {missing_num(twse, 'cash_per_share'):,}",
        f"- TWSE share_multiplier missing: {missing_num(twse, 'share_multiplier'):,}",
        f"- TWSE rights_ratio missing: {missing_num(twse, 'rights_ratio'):,}",
        f"- TPEx official rows: {len(tpex):,}",
        f"- TPEx cash_per_share missing: {missing_num(tpex, 'cash_per_share'):,}",
        f"- TPEx share_multiplier missing: {missing_num(tpex, 'share_multiplier'):,}",
        f"- TPEx rights_ratio missing: {missing_num(tpex, 'rights_ratio'):,}",
        "",
        "## Decision",
        "",
        "- Do not normalize FinMind dividend economics until source-specific date/unit semantics are corrected.",
        "- Do not apply TPEx /1000 stock-distribution logic to FinMind rows.",
        "- Do not treat TWSE official ex-right/dividend rows as complete economic packages without a verified detail join.",
        "- Payment/announcement enrichment requires a one-to-one PIT-safe event join.",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\\n".join(lines) + "\\n", encoding="utf-8")


if __name__ == "__main__":
    main()
