#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from astraquant.data.corporate_actions import (
    NormalizedCorporateActionKind,
    build_finmind_normalized_actions,
)

from source_strategy_integration_smoke import (
    SIGNAL_END,
    SIGNAL_START,
    build_supported_ca,
    load_adjusted,
    load_tradability,
)

REPORT_PATH = Path(
    os.environ.get(
        "REPORT_PATH",
        "docs/SOURCE_ELIGIBLE_UNIVERSE_CA_COVERAGE.md",
    )
)


def eligible_turnover_universe(
    adjusted: pd.DataFrame,
    tradability: pd.DataFrame,
) -> pd.DataFrame:
    trad = tradability[
        ["date", "stock_id", "observed_trade", "valid_ohlc"]
    ].copy()
    merged = adjusted.merge(
        trad,
        on=["date", "stock_id"],
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    numeric_id = merged["stock_id"].astype(str).str.fullmatch(
        r"[1-9]\d{3}",
        na=False,
    )
    positive = (merged[["open", "max", "min", "close"]] > 0).all(axis=1)
    geometry = (
        merged["max"] >= merged[["open", "close", "min"]].max(axis=1)
    ) & (
        merged["min"] <= merged[["open", "close", "max"]].min(axis=1)
    )
    turnover = pd.to_numeric(
        merged["Trading_money"],
        errors="coerce",
    ).gt(0)
    tradable = (
        merged["_merge"].eq("both")
        & merged["observed_trade"].fillna(False).astype(bool)
        & merged["valid_ohlc"].fillna(False).astype(bool)
    )
    eligible = merged[
        numeric_id & positive & geometry & turnover & tradable
    ].copy()
    eligible["turnover_percentile"] = eligible.groupby(
        "date"
    )["Trading_money"].rank(
        pct=True,
        ascending=False,
        method="average",
    )
    return eligible[
        eligible["turnover_percentile"].le(0.25)
        & eligible["date"].between(SIGNAL_START, SIGNAL_END)
    ][["date", "stock_id"]].drop_duplicates()


def main() -> None:
    adjusted = load_adjusted()
    tradability = load_tradability(adjusted)
    eligible = eligible_turnover_universe(adjusted, tradability)
    if eligible.empty:
        raise SystemExit("BLOCKED: eligible turnover universe is empty")

    scope_tickers = set(eligible["stock_id"].astype(str))
    market_sessions = [
        pd.Timestamp(x)
        for x in adjusted["date"].dropna().drop_duplicates().sort_values().tolist()
        if pd.Timestamp(x) >= SIGNAL_START
    ]
    end_pos = max(i for i, x in enumerate(market_sessions) if x <= SIGNAL_END)
    sim_sessions = market_sessions[: min(len(market_sessions), end_pos + 6)]
    session_set = set(sim_sessions)

    dividend = pd.read_parquet(
        Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data"))
        / "fundamentals"
        / "dividend.parquet"
    )
    normalized = [
        a
        for a in build_finmind_normalized_actions(dividend)
        if a.ticker in scope_tickers
        and min(session_set).date() <= a.effective_date <= max(session_set).date()
    ]
    normalized_unknown_known = [a for a in normalized if a.known_at is None]
    normalized_late_known = [
        a
        for a in normalized
        if a.known_at is not None and a.known_at.date() > a.effective_date
    ]
    cash_unknown_payment = [
        a
        for a in normalized
        if a.kind is NormalizedCorporateActionKind.CASH_DIVIDEND
        and a.payment_at is None
    ]

    instructions, unsupported_count, unsupported_summary = build_supported_ca(
        candidate_tickers=set(scope_tickers),
        sessions=session_set,
    )

    source_root = Path(
        os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")
    )
    ledger = pd.read_parquet(
        source_root / "reference" / "corporate_actions_ledger.parquet",
        columns=["stock_id", "event_date", "known_date", "event_type"],
    )
    ledger["stock_id"] = ledger["stock_id"].astype(str)
    ledger["event_date"] = pd.to_datetime(
        ledger["event_date"], errors="coerce"
    ).dt.normalize()
    ledger["known_date"] = pd.to_datetime(
        ledger["known_date"], errors="coerce"
    )
    nondiv = ledger[
        ledger["stock_id"].isin(scope_tickers)
        & ledger["event_date"].between(
            min(session_set),
            max(session_set),
            inclusive="both",
        )
        & ledger["event_type"].astype(str).isin(
            {
                "capital_reduction",
                "capital_reduction_deficit",
                "par_value_change_split",
            }
        )
    ].copy()
    nondiv_unknown = nondiv[nondiv["known_date"].isna()].copy()
    nondiv_unknown["event_year"] = nondiv_unknown["event_date"].dt.year.astype("Int64")
    nondiv_breakdown = (
        nondiv_unknown.groupby("event_type", dropna=False)
        .agg(
            rows=("stock_id", "size"),
            tickers=("stock_id", "nunique"),
            first_year=("event_year", "min"),
            last_year=("event_year", "max"),
        )
        .reset_index()
        .sort_values(["event_type"], kind="stable")
    )
    nondiv_unknown_known = int(len(nondiv_unknown))
    nondiv_late_known = int(
        (
            nondiv["known_date"].notna()
            & nondiv["event_date"].notna()
            & (nondiv["known_date"].dt.normalize() > nondiv["event_date"])
        ).sum()
    )

    checks = {
        "eligible_universe_nonempty": len(eligible) > 0,
        "ca_builder_completed_for_full_eligible_ticker_scope": True,
        "instruction_event_ids_unique": len(
            {x.event.event_id for x in instructions}
        )
        == len(instructions),
    }
    status = "PASS_AUDIT_WITH_BLOCKERS" if unsupported_count else "PASS_AUDIT"

    lines = [
        "# Eligible-Universe Corporate-Action Coverage Audit",
        "",
        f"Status: **{status}**",
        "",
        "Purpose: measure whether the full same-day tradable top-25%-turnover universe can support portfolio-level random/null controls under the canonical RAW/CA accounting path. This audit does not run a placebo portfolio and does not change the signal definition.",
        "",
        "## Scope",
        "",
        f"- signal window: {SIGNAL_START.date()} through {SIGNAL_END.date()}",
        f"- eligible date-ticker pairs: {len(eligible):,}",
        f"- distinct eligible tickers: {len(scope_tickers):,}",
        f"- simulation/CA horizon: {min(session_set).date()} through {max(session_set).date()}",
        "",
        "## Normalized dividend CA coverage",
        "",
        f"- normalized components in eligible ticker scope: {len(normalized):,}",
        f"- known_at missing: {len(normalized_unknown_known):,}",
        f"- known_at after effective date: {len(normalized_late_known):,}",
        f"- cash components with unknown payment_at: {len(cash_unknown_payment):,}",
        "",
        "## Non-dividend canonical-ledger timing",
        "",
        f"- supported non-dividend rows in eligible ticker scope: {len(nondiv):,}",
        f"- known_date missing: {nondiv_unknown_known:,}",
        f"- known_date after event_date: {nondiv_late_known:,}",
        "",
        "### Missing-known-date breakdown",
        "",
        "| Event type | Rows | Distinct tickers | First year | Last year |",
        "|---|---:|---:|---:|---:|",
    ]
    if nondiv_breakdown.empty:
        lines.append("| — | 0 | 0 | — | — |")
    else:
        for row in nondiv_breakdown.itertuples(index=False):
            first_year = "—" if pd.isna(row.first_year) else str(int(row.first_year))
            last_year = "—" if pd.isna(row.last_year) else str(int(row.last_year))
            lines.append(
                f"| {row.event_type} | {int(row.rows):,} | {int(row.tickers):,} | {first_year} | {last_year} |"
            )
    lines += [
        "",
        "The table above is descriptive source evidence only. Event types are not assigned one blanket PIT treatment here; P2-060 must freeze event-type-specific handling before any portfolio-level attribution run.",
        "",
        "## Canonical builder result",
        "",
        f"- generated instructions: {len(instructions):,}",
        f"- builder unsupported count: {unsupported_count:,}",
        f"- builder unsupported summary: {unsupported_summary}",
        "",
        "Unknown payment dates are not automatically blockers because canonical accounting can retain receivables without guessing settlement. Unknown or post-effective information timing is a PIT issue and must be explicitly quarantined or otherwise source-audited before portfolio-level null controls use those names.",
        "",
        "## Operational gates",
        "",
        "| Gate | Result |",
        "|---|---|",
    ]
    for name, ok in checks.items():
        lines.append(f"| {name} | {'PASS' if ok else 'FAIL'} |")

    lines += [
        "",
        "## Decision boundary",
        "",
        "This file is an audit of the expanded null-universe accounting scope. A nonzero unsupported count is adverse/source-blocking evidence, not permission to fall back to adjusted prices or silently omit affected names. Portfolio-level policy/capacity attribution remains locked until the blocker is explicitly accounted for on a common-support basis.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if not all(checks.values()):
        raise SystemExit("FAIL: eligible-universe CA coverage audit did not complete")


if __name__ == "__main__":
    main()
