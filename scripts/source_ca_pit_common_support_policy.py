#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pandas as pd

from astraquant.data.corporate_actions import build_finmind_normalized_actions
from source_eligible_universe_ca_coverage import eligible_turnover_universe
from source_strategy_integration_smoke import (
    SIGNAL_END,
    SIGNAL_START,
    load_adjusted,
    load_tradability,
)

SOURCE_ROOT = Path(
    os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")
).resolve()
REPORT_PATH = Path(
    os.environ.get(
        "REPORT_PATH",
        "docs/SOURCE_CA_PIT_COMMON_SUPPORT_POLICY.md",
    )
)
EXCLUSIONS_PATH = Path(
    os.environ.get(
        "EXCLUSIONS_PATH",
        "docs/SOURCE_CA_PIT_EXCLUSIONS.csv",
    )
)

SHARE_MUTATION_TYPES = {
    "capital_reduction",
    "par_value_change_split",
}


def main() -> None:
    adjusted = load_adjusted()
    tradability = load_tradability(adjusted)
    eligible = eligible_turnover_universe(adjusted, tradability)
    if eligible.empty:
        raise SystemExit("BLOCKED: eligible turnover universe is empty")

    scope_tickers = set(eligible["stock_id"].astype(str))
    start = SIGNAL_START.normalize()
    end = SIGNAL_END.normalize()

    dividend = pd.read_parquet(SOURCE_ROOT / "fundamentals" / "dividend.parquet")
    normalized = build_finmind_normalized_actions(dividend)
    late_rows: list[dict[str, object]] = []
    for a in normalized:
        if (
            a.ticker in scope_tickers
            and start.date() <= a.effective_date <= end.date()
            and a.known_at is not None
            and a.known_at.date() > a.effective_date
        ):
            late_rows.append(
                {
                    "ticker": str(a.ticker),
                    "effective_date": str(a.effective_date),
                    "event_type": str(a.kind.value),
                    "known_at": a.known_at.date().isoformat(),
                    "policy_reason": "NORMALIZED_KNOWN_AFTER_EFFECTIVE",
                    "source": str(a.source_name),
                }
            )

    ledger = pd.read_parquet(
        SOURCE_ROOT / "reference" / "corporate_actions_ledger.parquet",
        columns=[
            "stock_id",
            "event_date",
            "known_date",
            "event_type",
            "source_name",
        ],
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
        & ledger["event_date"].between(start, end, inclusive="both")
        & ledger["event_type"].astype(str).isin(SHARE_MUTATION_TYPES)
        & ledger["known_date"].isna()
    ].copy()

    unknown_rows = [
        {
            "ticker": str(row.stock_id),
            "effective_date": pd.Timestamp(row.event_date).date().isoformat(),
            "event_type": str(row.event_type),
            "known_at": "",
            "policy_reason": "SHARE_MUTATION_KNOWN_DATE_MISSING",
            "source": str(row.source_name),
        }
        for row in nondiv.itertuples(index=False)
    ]

    exclusions = pd.DataFrame(
        late_rows + unknown_rows,
        columns=[
            "ticker",
            "effective_date",
            "event_type",
            "known_at",
            "policy_reason",
            "source",
        ],
    ).sort_values(
        ["policy_reason", "event_type", "effective_date", "ticker"],
        kind="stable",
    )
    exclusions = exclusions.drop_duplicates().reset_index(drop=True)

    late_count = int(
        exclusions["policy_reason"].eq(
            "NORMALIZED_KNOWN_AFTER_EFFECTIVE"
        ).sum()
    )
    missing_count = int(
        exclusions["policy_reason"].eq(
            "SHARE_MUTATION_KNOWN_DATE_MISSING"
        ).sum()
    )
    if late_count != 4:
        raise SystemExit(
            f"BLOCKED: expected 4 late-known normalized rows, found {late_count}"
        )
    if missing_count != 478:
        raise SystemExit(
            f"BLOCKED: expected 478 unknown-known-date share mutations, found {missing_count}"
        )

    excluded_tickers = sorted(set(exclusions["ticker"].astype(str)))
    event_breakdown = (
        exclusions.groupby(["policy_reason", "event_type"], dropna=False)
        .agg(
            rows=("ticker", "size"),
            tickers=("ticker", "nunique"),
            first_date=("effective_date", "min"),
            last_date=("effective_date", "max"),
        )
        .reset_index()
        .sort_values(["policy_reason", "event_type"], kind="stable")
    )

    EXCLUSIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    exclusions.to_csv(EXCLUSIONS_PATH, index=False)
    digest = hashlib.sha256(EXCLUSIONS_PATH.read_bytes()).hexdigest()

    lines = [
        "# Full-Universe CA/PIT Common-Support Policy",
        "",
        "Status: **FROZEN**",
        "",
        "Purpose: freeze the corporate-action PIT common-support exclusion set before any deterministic policy/capacity attribution is run. This is a source-governance decision, not a strategy parameter and not a result-driven filter.",
        "",
        "## Frozen rule",
        "",
        "1. Preserve corporate actions on their economic effective-date coordinate; do not move an economic share/cash mutation to a later information date because doing so would distort interim RAW wealth accounting.",
        "2. A normalized dividend component whose known_at is later than its effective date is PIT-unsafe for this attribution universe.",
        "3. A capital_reduction or par_value_change_split row with missing known_date is PIT-unsafe because it changes share quantity and its information availability cannot be proven from the canonical source.",
        "4. Derive one ticker exclusion set from the event-level ledger below and remove that same set from baseline breakout candidates and every matched/control/deterministic-capacity rule before simulation.",
        "5. The exclusion set is frozen before attribution. It may not be changed in response to attribution performance. A newly discovered source blocker invalidates the run and requires a new audited policy version.",
        "6. No adjusted-price fallback and no silent ticker exclusion are permitted.",
        "",
        "## Source-derived blocker breakdown",
        "",
        "| Policy reason | Event type | Rows | Distinct tickers | First date | Last date |",
        "|---|---|---:|---:|---|---|",
    ]
    for row in event_breakdown.itertuples(index=False):
        lines.append(
            f"| {row.policy_reason} | {row.event_type} | {int(row.rows):,} "
            f"| {int(row.tickers):,} | {row.first_date} | {row.last_date} |"
        )

    lines += [
        "",
        f"- event-level exclusions: {len(exclusions):,}",
        f"- distinct excluded tickers: {len(excluded_tickers):,}",
        f"- exclusion ledger: `{EXCLUSIONS_PATH.as_posix()}`",
        f"- exclusion ledger SHA-256: `{digest}`",
        "",
        "## Common-support application",
        "",
        "The future attribution runner must load the frozen exclusion ledger, derive the exact ticker set, and assert that neither baseline nor any control/ranking rule contains an excluded ticker. The assertion is a hard gate, not a warning.",
        "",
        "The event-level CSV is the authoritative explicit list. Each excluded event is named by ticker, effective date, event type, source, and reason. Duplicate ticker events remain separate rows for auditability.",
        "",
        "## Decision boundary",
        "",
        "This policy does not promote a strategy, select a capacity rule, alter signal parameters, or unlock locked OOS. It only defines the common-support universe required before policy/capacity attribution.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
