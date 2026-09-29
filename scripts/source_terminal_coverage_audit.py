#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path

import pandas as pd


def _load_strategy_smoke_module():
    path = Path(__file__).resolve().with_name("source_strategy_integration_smoke.py")
    spec = importlib.util.spec_from_file_location(
        "source_strategy_integration_smoke_terminal_audit",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError("cannot load source_strategy_integration_smoke.py")
    spec.loader.exec_module(module)
    return module


_STRATEGY_SMOKE = _load_strategy_smoke_module()
CURATED_COMPOSITE_CONVERSIONS = _STRATEGY_SMOKE.CURATED_COMPOSITE_CONVERSIONS
CURATED_SUCCESSOR_CONVERSIONS = _STRATEGY_SMOKE.CURATED_SUCCESSOR_CONVERSIONS
CURATED_TERMINAL_EVENTS = _STRATEGY_SMOKE.CURATED_TERMINAL_EVENTS

SOURCE_ROOT = Path(
    os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")
).resolve()
REPORT_PATH = Path(
    os.environ.get("REPORT_PATH", "docs/SOURCE_TERMINAL_COVERAGE_AUDIT.md")
)
EXCLUSIONS_PATH = Path(
    os.environ.get("EXCLUSIONS_PATH", "docs/SOURCE_CA_PIT_EXCLUSIONS.csv")
)
P2_060_START = pd.Timestamp("2016-01-04")
P2_060_END = pd.Timestamp("2026-06-30")
AUDIT_END = pd.Timestamp("2026-07-07")
EXPECTED_EXCLUSION_SHA256 = (
    "379d58f6a8aa06b1e020d56911930f4bc01861d3eeca109613d9e5b1e490d134"
)
EXPECTED_ELIGIBLE_TICKERS = 1986
EXPECTED_EXCLUSION_ROWS = 482
EXPECTED_EXCLUDED_TICKERS = 355


def _read_year_parts(family: str, stem: str, columns: list[str]) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    root = SOURCE_ROOT / family
    for path in sorted(root.glob(f"{stem}_*.parquet")):
        part = pd.read_parquet(path, columns=columns)
        part["date"] = pd.to_datetime(part["date"], errors="coerce").dt.normalize()
        part["stock_id"] = part["stock_id"].astype(str)
        parts.append(part)
    if not parts:
        raise SystemExit(f"BLOCKED: no source files for {family}/{stem}_*.parquet")
    return pd.concat(parts, ignore_index=True)


def load_frozen_exclusions() -> tuple[set[str], str]:
    digest = hashlib.sha256(EXCLUSIONS_PATH.read_bytes()).hexdigest()
    if digest != EXPECTED_EXCLUSION_SHA256:
        raise SystemExit(
            "BLOCKED: P2-060 exclusion SHA changed "
            f"(expected {EXPECTED_EXCLUSION_SHA256}, got {digest})"
        )
    exclusions = pd.read_csv(EXCLUSIONS_PATH, dtype={"ticker": str})
    if len(exclusions) != EXPECTED_EXCLUSION_ROWS:
        raise SystemExit(
            f"BLOCKED: P2-060 exclusion row count changed: {len(exclusions)}"
        )
    tickers = set(exclusions["ticker"].astype(str))
    if len(tickers) != EXPECTED_EXCLUDED_TICKERS:
        raise SystemExit(
            f"BLOCKED: P2-060 excluded ticker count changed: {len(tickers)}"
        )
    return tickers, digest


def build_p2_060_eligible_scope() -> set[str]:
    adjusted = _read_year_parts(
        "adj",
        "prices_adj",
        ["date", "stock_id", "open", "max", "min", "close", "Trading_money"],
    )
    adjusted = adjusted[
        adjusted["date"].between(P2_060_START, P2_060_END, inclusive="both")
    ].copy()

    trad = pd.read_parquet(
        SOURCE_ROOT / "reference" / "tradability.parquet",
        columns=["date", "stock_id", "observed_trade", "valid_ohlc"],
    )
    trad["date"] = pd.to_datetime(trad["date"], errors="coerce").dt.normalize()
    trad["stock_id"] = trad["stock_id"].astype(str)

    merged = adjusted.merge(
        trad,
        on=["date", "stock_id"],
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    numeric_id = merged["stock_id"].str.fullmatch(r"[1-9]\d{3}", na=False)
    positive = (merged[["open", "max", "min", "close"]] > 0).all(axis=1)
    geometry = (
        merged["max"] >= merged[["open", "close", "min"]].max(axis=1)
    ) & (
        merged["min"] <= merged[["open", "close", "max"]].min(axis=1)
    )
    turnover = pd.to_numeric(merged["Trading_money"], errors="coerce").gt(0)
    tradable = (
        merged["_merge"].eq("both")
        & merged["observed_trade"].fillna(False).astype(bool)
        & merged["valid_ohlc"].fillna(False).astype(bool)
    )
    eligible = merged[
        numeric_id & positive & geometry & turnover & tradable
    ].copy()
    eligible["turnover_percentile"] = eligible.groupby("date")[
        "Trading_money"
    ].rank(pct=True, ascending=False, method="average")
    eligible = eligible[eligible["turnover_percentile"].le(0.25)]
    tickers = set(eligible["stock_id"].astype(str))
    if len(tickers) != EXPECTED_ELIGIBLE_TICKERS:
        raise SystemExit(
            "BLOCKED: frozen eligible-universe distinct ticker count changed "
            f"(expected {EXPECTED_ELIGIBLE_TICKERS}, got {len(tickers)})"
        )
    return tickers


def load_raw_last_dates() -> pd.DataFrame:
    raw = _read_year_parts("raw", "prices_raw", ["date", "stock_id"])
    raw = raw[raw["date"].notna()].copy()
    return (
        raw.groupby("stock_id", as_index=False)["date"]
        .max()
        .rename(columns={"date": "last_raw_date"})
    )


def modeled_terminal_map() -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for item in CURATED_TERMINAL_EVENTS:
        out[str(item["ticker"])] = {
            "event_type": "CASH_MERGER_EXTINGUISHMENT",
            "terminal_stale_from": pd.Timestamp(item["terminal_stale_from"]),
            "effective_at": pd.Timestamp(item["effective_at"]).normalize(),
            "source": str(item["source"]),
            "source_url": str(item["source_url"]),
        }
    for item in CURATED_SUCCESSOR_CONVERSIONS:
        out[str(item["ticker"])] = {
            "event_type": "SUCCESSOR_SHARE_CONVERSION",
            "terminal_stale_from": pd.Timestamp(item["terminal_stale_from"]),
            "effective_at": pd.Timestamp(item["effective_at"]).normalize(),
            "source": str(item["source"]),
            "source_url": str(item["source_url"]),
        }
    for item in CURATED_COMPOSITE_CONVERSIONS:
        out[str(item["ticker"])] = {
            "event_type": "MULTI_LEG_SHARE_CONVERSION_PLUS_CASH",
            "terminal_stale_from": pd.Timestamp(item["terminal_stale_from"]),
            "effective_at": pd.Timestamp(item["effective_at"]).normalize(),
            "source": str(item["source"]),
            "source_url": str(item["source_url"]),
        }
    return out


def _load_suspensions() -> pd.DataFrame:
    path = SOURCE_ROOT / "reference" / "finmind_suspended.parquet"
    if not path.exists():
        return pd.DataFrame(
            columns=[
                "date",
                "stock_id",
                "suspension_time",
                "resumption_date",
                "resumption_time",
            ]
        )
    d = pd.read_parquet(path)
    d["stock_id"] = d["stock_id"].astype(str)
    d["date"] = pd.to_datetime(d["date"], errors="coerce").dt.normalize()
    if "resumption_date" in d.columns:
        d["resumption_date"] = pd.to_datetime(
            d["resumption_date"], errors="coerce"
        ).dt.normalize()
    return d


def _load_ca_ledger() -> pd.DataFrame:
    path = SOURCE_ROOT / "reference" / "corporate_actions_ledger.parquet"
    d = pd.read_parquet(
        path,
        columns=[
            "stock_id",
            "event_date",
            "known_date",
            "event_type",
            "cash_per_share",
            "share_multiplier",
            "source_name",
            "source_url",
        ],
    )
    d["stock_id"] = d["stock_id"].astype(str)
    d["event_date"] = pd.to_datetime(d["event_date"], errors="coerce").dt.normalize()
    return d


def _load_tradability_coverage() -> pd.DataFrame:
    path = SOURCE_ROOT / "reference" / "tradability_coverage.csv"
    if not path.exists():
        return pd.DataFrame(columns=["stock_id", "start_date", "end_date"])
    d = pd.read_csv(path, dtype={"stock_id": str})
    for col in ("start_date", "end_date"):
        if col in d.columns:
            d[col] = pd.to_datetime(d[col], errors="coerce").dt.normalize()
    return d


def classify_missing_event(
    *,
    ticker: str,
    last_raw_date: pd.Timestamp,
    suspensions: pd.DataFrame,
    ledger: pd.DataFrame,
) -> tuple[str, str, str]:
    susp = suspensions[suspensions["stock_id"].eq(ticker)].copy()
    if not susp.empty:
        near = susp[
            susp["date"].between(
                last_raw_date - pd.Timedelta(days=30),
                last_raw_date + pd.Timedelta(days=120),
                inclusive="both",
            )
        ]
        if not near.empty:
            rows = []
            for row in near.itertuples(index=False):
                resume = getattr(row, "resumption_date", pd.NaT)
                resume_text = (
                    "unknown" if pd.isna(resume)
                    else str(pd.Timestamp(resume).date())
                )
                rows.append(
                    f"suspend={pd.Timestamp(row.date).date()},resume={resume_text}"
                )
            return (
                "TERMINAL_SUSPENSION_LIFECYCLE",
                "FinMind suspended source present",
                "; ".join(rows),
            )

    ca = ledger[ledger["stock_id"].eq(ticker)].copy()
    near_ca = ca[
        ca["event_date"].between(
            last_raw_date - pd.Timedelta(days=30),
            last_raw_date + pd.Timedelta(days=120),
            inclusive="both",
        )
    ]
    if not near_ca.empty:
        event_types = sorted(set(near_ca["event_type"].astype(str)))
        if any(x.startswith("capital_reduction") for x in event_types):
            missing = "CAPITAL_REDUCTION_TERMINAL_OR_RESUMPTION_SEMANTICS"
        elif "par_value_change_split" in event_types:
            missing = "PAR_VALUE_CHANGE_TERMINAL_OR_RESUMPTION_SEMANTICS"
        else:
            missing = "TERMINAL_CA_ECONOMICS_OR_SUCCESSOR_MAPPING"
        facts = []
        for row in near_ca.sort_values("event_date").itertuples(index=False):
            facts.append(
                f"{pd.Timestamp(row.event_date).date()}:{row.event_type}:{row.source_name}"
            )
        return (
            missing,
            "canonical CA ledger has nearby event(s)",
            "; ".join(facts),
        )

    return (
        "UNKNOWN_TERMINAL_LIFECYCLE",
        "no nearby canonical suspension/CA row",
        "external TWSE/MOPS lifecycle audit required",
    )


def build_audit_table(
    *,
    common_support_tickers: set[str],
    raw_last: pd.DataFrame,
    modeled: dict[str, dict[str, object]],
    suspensions: pd.DataFrame,
    ledger: pd.DataFrame,
    coverage: pd.DataFrame,
) -> pd.DataFrame:
    scoped = raw_last[raw_last["stock_id"].isin(common_support_tickers)].copy()
    missing_raw_scope = common_support_tickers - set(scoped["stock_id"])
    if missing_raw_scope:
        raise SystemExit(
            "BLOCKED: common-support tickers absent from RAW source: "
            f"{sorted(missing_raw_scope)[:20]}"
        )

    terminal = scoped[scoped["last_raw_date"].lt(AUDIT_END)].copy()
    coverage_map = {}
    if not coverage.empty and "end_date" in coverage.columns:
        coverage_map = dict(
            zip(coverage["stock_id"].astype(str), coverage["end_date"])
        )

    rows: list[dict[str, object]] = []
    for row in terminal.sort_values(
        ["last_raw_date", "stock_id"]
    ).itertuples(index=False):
        ticker = str(row.stock_id)
        last_raw = pd.Timestamp(row.last_raw_date).normalize()
        model = modeled.get(ticker)
        if model is not None:
            stale_from = pd.Timestamp(model["terminal_stale_from"]).normalize()
            effective = pd.Timestamp(model["effective_at"]).normalize()
            status = "MODELED"
            event_type = str(model["event_type"])
            source_availability = str(model["source"])
            source_detail = str(model["source_url"])
            missing_event = "—"
            model_alignment = (
                "PASS"
                if last_raw < stale_from <= effective
                else "REVIEW_MODEL_DATE_ALIGNMENT"
            )
        else:
            (
                missing_event,
                source_availability,
                source_detail,
            ) = classify_missing_event(
                ticker=ticker,
                last_raw_date=last_raw,
                suspensions=suspensions,
                ledger=ledger,
            )
            status = "UNMODELED"
            event_type = "—"
            model_alignment = "—"

        trad_end = coverage_map.get(ticker, pd.NaT)
        rows.append(
            {
                "ticker": ticker,
                "last_raw_date": last_raw,
                "status": status,
                "event_type": event_type,
                "missing_event": missing_event,
                "model_alignment": model_alignment,
                "tradability_coverage_end": trad_end,
                "source_availability": source_availability,
                "source_detail": source_detail,
            }
        )
    return pd.DataFrame(rows)


def _md_date(value: object) -> str:
    if value is None or pd.isna(value):
        return "—"
    return str(pd.Timestamp(value).date())


def main() -> None:
    excluded, exclusion_digest = load_frozen_exclusions()
    eligible_tickers = build_p2_060_eligible_scope()
    common_support = eligible_tickers - excluded

    raw_last = load_raw_last_dates()
    modeled = modeled_terminal_map()
    suspensions = _load_suspensions()
    ledger = _load_ca_ledger()
    coverage = _load_tradability_coverage()

    audit = build_audit_table(
        common_support_tickers=common_support,
        raw_last=raw_last,
        modeled=modeled,
        suspensions=suspensions,
        ledger=ledger,
        coverage=coverage,
    )
    modeled_rows = audit[audit["status"].eq("MODELED")].copy()
    unmodeled_rows = audit[audit["status"].eq("UNMODELED")].copy()
    modeled_outside_scope = sorted(set(modeled) - common_support)

    status = (
        "PASS_AUDIT_WITH_UNVERIFIED_FALLBACK"
        if len(unmodeled_rows)
        else "PASS_AUDIT"
    )
    lines = [
        "# Source Terminal Coverage Audit",
        "",
        f"Status: **{status}**",
        "",
        "Purpose: one-time terminal-security lifecycle coverage inventory for the frozen P2-060 common-support universe. This audit does not change candidates, exclusions, execution, accounting, valuation, or OOS governance.",
        "",
        "## Frozen scope gates",
        "",
        f"- P2-060 eligible-universe window: {P2_060_START.date()} through {P2_060_END.date()}",
        f"- terminal coverage window: {P2_060_START.date()} through {AUDIT_END.date()}",
        f"- frozen eligible distinct tickers: {len(eligible_tickers):,} (expected {EXPECTED_ELIGIBLE_TICKERS:,})",
        f"- P2-060 exclusion rows / distinct tickers: {EXPECTED_EXCLUSION_ROWS:,} / {len(excluded):,}",
        f"- P2-060 exclusion SHA256: {exclusion_digest}",
        f"- common-support distinct tickers audited: {len(common_support):,}",
        "",
        "A security is classified as RAW-terminal here only when its maximum RAW date in the currently available source is earlier than 2026-07-07. A temporary gap that later resumes in the source is therefore not mislabeled as terminal.",
        "",
        "Hard rules: no adjusted-price fallback, no stale RAW mark outside an explicit modeled terminal window, and no silent ticker exclusion.",
        "",
        "## Summary",
        "",
        f"- RAW-terminal tickers in common support: {len(audit):,}",
        f"- modeled: {len(modeled_rows):,}",
        f"- unmodeled: {len(unmodeled_rows):,}",
        f"- conservative fallback coverage: {len(unmodeled_rows):,}",
        (
            "- row-count reconciliation: summary and rendered table are generated "
            f"from the same dataframe; current unmodeled count = {len(unmodeled_rows):,}. "
            "The earlier 72-row presentation discrepancy is corrected."
        ),
        "",
        "## Modeled terminal securities",
        "",
        "| Ticker | Last RAW | Modeled event | Date alignment | Tradability coverage end | Source availability |",
        "|---|---|---|---|---|---|",
    ]
    if modeled_rows.empty:
        lines.append("| — | — | — | — | — | — |")
    else:
        for row in modeled_rows.itertuples(index=False):
            lines.append(
                f"| {row.ticker} | {_md_date(row.last_raw_date)} | "
                f"{row.event_type} | {row.model_alignment} | "
                f"{_md_date(row.tradability_coverage_end)} | "
                f"{row.source_availability} |"
            )

    lines += [
        "",
        "## Unmodeled terminal securities",
        "",
        "| Ticker | Last RAW | Missing lifecycle event | Tradability coverage end | Source availability | Source detail |",
        "|---|---|---|---|---|---|---|",
    ]
    if unmodeled_rows.empty:
        lines.append("| — | — | — | — | — | — |")
    else:
        for row in unmodeled_rows.itertuples(index=False):
            detail = str(row.source_detail).replace("|", "/")
            lines.append(
                f"| {row.ticker} | {_md_date(row.last_raw_date)} | "
                f"{row.missing_event} | "
                f"{_md_date(row.tradability_coverage_end)} | "
                f"{row.source_availability} | {detail} |"
            )

    lines += [
        "",
        "## Canonical modeled feed outside frozen common support",
        "",
        "These are already curated in the engine but are not counted in the common-support modeled/unmodeled totals above.",
        "",
        f"- tickers: {', '.join(modeled_outside_scope) if modeled_outside_scope else '—'}",
        "",
        "## Interpretation and next gate",
        "",
        "Two-track policy is active. A CONFIRMED row in data/research/terminal_events.csv overrides the conservative fallback. PARTIAL and NOT_FOUND rows do not override it.",
        "",
        "For every still-unmodeled terminal security, AstraQuant applies UNVERIFIED_TERMINAL_CASHOUT at the final observed RAW trading-session close using that RAW close as cash consideration. Cash mergers often include a premium, so this fallback is conservative and tends to understate rather than overstate strategy return.",
        "",
        "No adjusted-price fallback, post-terminal stale RAW mark, synthetic trade, or silent ticker exclusion is permitted. External verification can replace fallback economics by updating the CSV without code changes.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
