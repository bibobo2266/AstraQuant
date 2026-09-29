#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from astraquant.portfolio.policy import PortfolioPolicyConfig
from astraquant.research.parameter_sweep import ResearchParameterSweepRunner
from astraquant.research.signal_engine import SignalContext
from astraquant.research.universe_engine import UniverseContext

from source_eligible_universe_ca_coverage import eligible_turnover_universe
from source_strategy_integration_smoke import load_adjusted, load_tradability

SWEEP_PATH = Path(
    os.environ.get(
        "SWEEP_PATH",
        "configs/research/oneil_all_taiwan_surface.yaml",
    )
)
REPORT_PATH = Path(
    os.environ.get(
        "REPORT_PATH",
        "docs/SOURCE_CONFIG_SWEEP_REPORT.md",
    )
)
CSV_PATH = Path(
    os.environ.get(
        "CSV_PATH",
        "docs/SOURCE_CONFIG_SWEEP_RESULTS.csv",
    )
)
EXCLUSIONS_PATH = Path(
    os.environ.get(
        "EXCLUSIONS_PATH",
        "docs/SOURCE_CA_PIT_EXCLUSIONS.csv",
    )
)
EXPECTED_EXCLUSIONS_SHA256 = (
    "379d58f6a8aa06b1e020d56911930f4bc01861d3eeca109613d9e5b1e490d134"
)
EXPECTED_ELIGIBLE_TICKERS = 1986
SIGNAL_START = pd.Timestamp(os.environ.get("SIGNAL_START", "2016-01-04"))
SIGNAL_END = pd.Timestamp(os.environ.get("SIGNAL_END", "2026-06-30"))
FORWARD_SESSIONS = int(os.environ.get("FORWARD_SESSIONS", "250"))
OUTCOME_DIRECTION = os.environ.get("OUTCOME_DIRECTION", "LONG").upper()
if OUTCOME_DIRECTION not in {"LONG", "SHORT"}:
    raise SystemExit("OUTCOME_DIRECTION must be LONG or SHORT")


def _load_exclusions() -> set[str]:
    digest = hashlib.sha256(EXCLUSIONS_PATH.read_bytes()).hexdigest()
    if digest != EXPECTED_EXCLUSIONS_SHA256:
        raise SystemExit(
            "BLOCKED: frozen P2-060 exclusion ledger hash changed "
            f"(expected {EXPECTED_EXCLUSIONS_SHA256}, got {digest})"
        )
    frame = pd.read_csv(EXCLUSIONS_PATH, dtype={"ticker": str})
    return set(frame["ticker"].astype(str))


def _load_adjusted_volume(adjusted: pd.DataFrame) -> pd.DataFrame:
    source_root = Path(os.environ["SOURCE_ROOT"])
    years = sorted(
        set(pd.to_datetime(adjusted["date"], errors="coerce").dropna().dt.year.astype(int))
    )
    parts: list[pd.DataFrame] = []
    for year in years:
        path = source_root / "adj" / f"prices_adj_{year}.parquet"
        if not path.exists():
            raise SystemExit(f"BLOCKED: missing adjusted source file for volume: {path}")
        part = pd.read_parquet(
            path,
            columns=["date", "stock_id", "Trading_Volume"],
        )
        part["date"] = pd.to_datetime(part["date"], errors="coerce").dt.normalize()
        part["stock_id"] = part["stock_id"].astype(str)
        if part.duplicated(["date", "stock_id"]).any():
            raise SystemExit(
                f"BLOCKED: duplicate adjusted volume logical keys in {path}"
            )
        parts.append(part)
    volume = pd.concat(parts, ignore_index=True)
    return volume


def _research_panel() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    adjusted = load_adjusted()
    tradability = load_tradability(adjusted)
    volume = _load_adjusted_volume(adjusted)

    adjusted = adjusted.copy()
    adjusted["date"] = pd.to_datetime(adjusted["date"], errors="coerce").dt.normalize()
    adjusted["stock_id"] = adjusted["stock_id"].astype(str)
    tradability = tradability.copy()
    tradability["date"] = pd.to_datetime(tradability["date"], errors="coerce").dt.normalize()
    tradability["stock_id"] = tradability["stock_id"].astype(str)

    panel = adjusted.merge(
        volume,
        on=["date", "stock_id"],
        how="left",
        validate="one_to_one",
    )
    if panel["Trading_Volume"].isna().any():
        missing = int(panel["Trading_Volume"].isna().sum())
        raise SystemExit(
            f"BLOCKED: canonical adjusted volume missing for {missing} research rows"
        )
    panel = panel.merge(
        tradability[["date", "stock_id", "observed_trade", "valid_ohlc"]],
        on=["date", "stock_id"],
        how="left",
        validate="one_to_one",
    )
    panel["observed_trade"] = panel["observed_trade"].fillna(False).astype(bool)
    panel["valid_ohlc"] = panel["valid_ohlc"].fillna(False).astype(bool)
    return panel, adjusted, tradability


def _forward_outcomes(panel: pd.DataFrame) -> pd.DataFrame:
    x = panel[["date", "stock_id", "close"]].copy()
    x = x.sort_values(["stock_id", "date"], kind="stable").reset_index(drop=True)
    future = x.groupby("stock_id", sort=False)["close"].shift(-FORWARD_SESSIONS)
    x["forward_return"] = future / x["close"] - 1.0
    return x[["date", "stock_id", "forward_return"]]


def _metrics(candidate_returns: pd.Series) -> dict[str, float | int]:
    r = pd.to_numeric(candidate_returns, errors="coerce").dropna()
    winners = r[r > 0]
    losers = r[r < 0]
    avg_win = float(winners.mean()) if len(winners) else float("nan")
    avg_loss = float(losers.mean()) if len(losers) else float("nan")
    payoff = (
        avg_win / abs(avg_loss)
        if len(winners) and len(losers) and avg_loss != 0
        else float("nan")
    )
    return {
        "valid_outcomes": int(len(r)),
        "win_rate": float((r > 0).mean()) if len(r) else float("nan"),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "payoff": payoff,
        "expectancy": float(r.mean()) if len(r) else float("nan"),
        "median_return": float(r.median()) if len(r) else float("nan"),
    }


def _parameter_columns(frame: pd.DataFrame) -> pd.DataFrame:
    params = frame["parameters"].map(json.loads)
    keys = sorted({k for item in params for k in item})
    out = frame.copy()
    for key in keys:
        out[key] = params.map(lambda d, k=key: d.get(k))
    return out


def main() -> None:
    excluded = _load_exclusions()
    panel, adjusted, tradability = _research_panel()

    eligible = eligible_turnover_universe(adjusted, tradability)
    eligible_count = int(eligible["stock_id"].astype(str).nunique())
    if eligible_count != EXPECTED_ELIGIBLE_TICKERS:
        raise SystemExit(
            "BLOCKED: frozen eligible-universe ticker count changed "
            f"(expected {EXPECTED_ELIGIBLE_TICKERS}, got {eligible_count})"
        )

    source_revision = os.environ.get("SOURCE_REVISION", "source-checkout")
    theme_root = Path(os.environ.get("THEME_ROOT", "themes")).resolve()
    runner = ResearchParameterSweepRunner()
    stream = runner.stream_sweep(
        sweep_config_path=SWEEP_PATH,
        root=Path("."),
        panel=panel,
        universe_context=UniverseContext(
            p2_060_excluded_tickers=frozenset(excluded),
            p2_060_exclusion_sha256=EXPECTED_EXCLUSIONS_SHA256,
            theme_root=theme_root if theme_root.exists() else None,
        ),
        signal_context=SignalContext(source_revision=source_revision),
        base_policy=PortfolioPolicyConfig(
            position_fraction=0.10,
            max_positions=10,
            stop_fraction=0.12,
            max_hold_sessions=250,
        ),
    )

    outcomes = _forward_outcomes(panel)
    rows: list[dict[str, object]] = []

    for item in stream.runs:
        run = item.prepared
        signals = run.signal_frame[
            run.signal_frame["counts_as_candidate"]
            & run.signal_frame["signal_date"].between(
                SIGNAL_START, SIGNAL_END, inclusive="both"
            )
        ][["signal_date", "stock_id"]].copy()
        signals = signals.rename(columns={"signal_date": "date"})
        joined = signals.merge(
            outcomes,
            on=["date", "stock_id"],
            how="left",
            validate="one_to_one",
        )
        directional_return = (
            joined["forward_return"]
            if OUTCOME_DIRECTION == "LONG"
            else -joined["forward_return"]
        )
        metric = _metrics(directional_return)
        rows.append(
            {
                "run_name": run.run_config.run_name,
                "universe": item.universe,
                "parameters": json.dumps(
                    item.parameters, ensure_ascii=False, sort_keys=True
                ),
                "signals": int(len(signals)),
                "valid_outcomes": metric["valid_outcomes"],
                "outcome_coverage": (
                    float(metric["valid_outcomes"]) / len(signals)
                    if len(signals)
                    else float("nan")
                ),
                "win_rate": metric["win_rate"],
                "avg_win": metric["avg_win"],
                "avg_loss": metric["avg_loss"],
                "payoff": metric["payoff"],
                "expectancy": metric["expectancy"],
                "median_return": metric["median_return"],
            }
        )

    results = _parameter_columns(pd.DataFrame(rows))
    if results.empty:
        raise SystemExit("FAIL: sweep produced no configurations")
    if not bool(results["signals"].gt(0).any()):
        raise SystemExit("FAIL: sweep produced no signal candidates")

    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(CSV_PATH, index=False)

    valid = results[results["valid_outcomes"].gt(0)].copy()
    exp = pd.to_numeric(valid["expectancy"], errors="coerce").dropna()
    coverage = pd.to_numeric(valid["outcome_coverage"], errors="coerce").dropna()

    lines = [
        "# Source-backed Config Sweep",
        "",
        "Status: **PASS**",
        "",
        "## Research boundary",
        "",
        "- This is a candidate-level research screen, not executable portfolio evidence.",
        f"- Outcome: {OUTCOME_DIRECTION.lower()}-direction adjusted close-to-close return {FORWARD_SESSIONS} source sessions after the signal date.",
        "- No RAW fill, capacity, corporate-action path, FIFO path, stop execution, or portfolio sequencing is represented here.",
        "- The sweep does not select or promote a winning parameter combination.",
        "- Locked OOS remains locked.",
        "",
        "## Frozen gates",
        "",
        f"- P2-060 exclusion SHA: {EXPECTED_EXCLUSIONS_SHA256}",
        f"- eligible-universe distinct tickers: {eligible_count:,} (expected {EXPECTED_ELIGIBLE_TICKERS:,})",
        f"- signal window: {SIGNAL_START.date()} through {SIGNAL_END.date()}",
        f"- declared Cartesian combinations: {stream.declared_combinations:,}",
        f"- structurally invalid combinations skipped by preregistered constraints: {stream.skipped_by_constraints:,}",
        f"- evaluated parameter combinations: {len(results):,}",
        f"- feature-cache hits / misses: {runner.engine.feature_cache.hits:,} / {runner.engine.feature_cache.misses:,}",
        "",
        "## Parameter-surface summary",
        "",
        f"- combinations with at least one valid forward outcome: {len(valid):,}/{len(results):,}",
        f"- total signal candidates across combinations: {int(results['signals'].sum()):,}",
        f"- median outcome coverage: {coverage.median()*100:.2f}%" if len(coverage) else "- median outcome coverage: n/a",
        f"- expectancy q10 / median / q90 across combinations: "
        f"{exp.quantile(0.10)*100:.2f}% / {exp.median()*100:.2f}% / {exp.quantile(0.90)*100:.2f}%" if len(exp) else "- expectancy distribution: n/a",
        f"- fraction of combinations with positive expectancy: {(exp > 0).mean()*100:.2f}%" if len(exp) else "- positive-expectancy fraction: n/a",
        "",
        "## Marginal parameter summaries",
        "",
        "These are medians across the other declared axes; they are descriptive and are not winner selection.",
        "",
    ]

    param_cols = [
        c for c in results.columns
        if c.startswith("filter:") or c.startswith("trigger.") or c.startswith("exit:") or c.startswith("universe:")
    ]
    for col in param_cols:
        lines += [f"### {col}", "", "| Value | Configs | Median signals | Median expectancy | Positive expectancy configs |", "|---|---:|---:|---:|---:|"]
        for value, group in valid.groupby(col, dropna=False, sort=True):
            gx = pd.to_numeric(group["expectancy"], errors="coerce").dropna()
            lines.append(
                f"| {value} | {len(group):,} | {group['signals'].median():.0f} "
                f"| {gx.median()*100:.2f}% "
                f"| {(gx > 0).mean()*100:.1f}% |"
            )
        lines.append("")

    lines += [
        "## Full results",
        "",
        f"Machine-readable table: `{CSV_PATH.as_posix()}`.",
        "",
        "The next valid step is robustness analysis over neighboring cells / calendar regimes. Do not infer a Taiwan-optimal parameter from the maximum cell.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
