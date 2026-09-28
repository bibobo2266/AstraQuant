#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

from astraquant.features.technical import BreakoutSignalConfig, build_simple_breakout_signals

from source_strategy_integration_smoke import (
    SIGNAL_END,
    SIGNAL_START,
    load_adjusted,
    load_tradability,
    pit_unsafe_ca_tickers,
)

REPORT_PATH = Path(
    os.environ.get(
        "REPORT_PATH",
        "docs/SOURCE_SIGNAL_EDGE_FALSIFICATION.md",
    )
)
COMMON_SUPPORT_EXCLUDED_TICKERS = {"2823"}
N_PERMUTATIONS = 500
PRIMARY_HORIZON_SESSIONS = 250
SEED_BASE = 170_001


def _eligible_turnover_universe(
    adjusted: pd.DataFrame,
    tradability: pd.DataFrame,
    excluded: set[str],
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
    valid_turnover = pd.to_numeric(
        merged["Trading_money"],
        errors="coerce",
    ).gt(0)
    tradable = (
        merged["_merge"].eq("both")
        & merged["observed_trade"].fillna(False).astype(bool)
        & merged["valid_ohlc"].fillna(False).astype(bool)
    )

    eligible = merged[
        numeric_id & positive & geometry & valid_turnover & tradable
    ].copy()
    eligible["turnover_percentile"] = eligible.groupby(
        "date"
    )["Trading_money"].rank(
        pct=True,
        ascending=False,
        method="average",
    )
    eligible = eligible[
        eligible["turnover_percentile"].le(0.25)
        & eligible["date"].between(SIGNAL_START, SIGNAL_END)
        & ~eligible["stock_id"].astype(str).isin(excluded)
    ].copy()
    return eligible[["date", "stock_id"]].drop_duplicates()


def _forward_outcomes(
    *,
    adjusted: pd.DataFrame,
    eligible: pd.DataFrame,
) -> pd.DataFrame:
    prices = adjusted[
        ["date", "stock_id", "open", "close"]
    ].copy()
    prices["stock_id"] = prices["stock_id"].astype(str)
    prices["date"] = pd.to_datetime(
        prices["date"],
        errors="coerce",
    ).dt.normalize()

    sessions = pd.DatetimeIndex(
        sorted(prices["date"].dropna().unique())
    )
    session_to_index = {
        pd.Timestamp(day): i
        for i, day in enumerate(sessions)
    }

    outcome = eligible.rename(columns={"date": "signal_date"}).copy()
    outcome["signal_date"] = pd.to_datetime(
        outcome["signal_date"],
        errors="coerce",
    ).dt.normalize()

    def session_at_offset(day: pd.Timestamp, offset: int):
        idx = session_to_index.get(pd.Timestamp(day))
        if idx is None:
            return pd.NaT
        target = idx + offset
        if target >= len(sessions):
            return pd.NaT
        return pd.Timestamp(sessions[target])

    outcome["entry_date"] = outcome["signal_date"].map(
        lambda x: session_at_offset(x, 1)
    )
    outcome["exit_date"] = outcome["signal_date"].map(
        lambda x: session_at_offset(
            x,
            1 + PRIMARY_HORIZON_SESSIONS,
        )
    )

    entry = prices.rename(
        columns={
            "date": "entry_date",
            "open": "entry_open",
            "close": "entry_close_unused",
        }
    )[["entry_date", "stock_id", "entry_open"]]

    exit_px = prices.rename(
        columns={
            "date": "exit_date",
            "close": "exit_close",
            "open": "exit_open_unused",
        }
    )[["exit_date", "stock_id", "exit_close"]]

    outcome = outcome.merge(
        entry,
        on=["entry_date", "stock_id"],
        how="left",
        validate="many_to_one",
    )
    outcome = outcome.merge(
        exit_px,
        on=["exit_date", "stock_id"],
        how="left",
        validate="many_to_one",
    )

    outcome["forward_return"] = (
        pd.to_numeric(outcome["exit_close"], errors="coerce")
        / pd.to_numeric(outcome["entry_open"], errors="coerce")
        - 1.0
    )
    valid = (
        outcome["entry_open"].notna()
        & outcome["exit_close"].notna()
        & outcome["entry_open"].gt(0)
        & outcome["exit_close"].gt(0)
        & outcome["forward_return"].replace(
            [np.inf, -np.inf],
            np.nan,
        ).notna()
    )
    outcome["valid_forward_outcome"] = valid
    return outcome


def _summary(values: np.ndarray) -> dict[str, float]:
    values = np.asarray(values, dtype=float)
    wins = values[values > 0]
    losses = values[values < 0]
    mean_win = float(wins.mean()) if len(wins) else float("nan")
    mean_loss = float(losses.mean()) if len(losses) else float("nan")
    payoff = (
        mean_win / abs(mean_loss)
        if len(wins) and len(losses) and mean_loss != 0
        else float("nan")
    )
    return {
        "n": int(len(values)),
        "expectancy": float(values.mean()),
        "median": float(np.median(values)),
        "win_rate": float((values > 0).mean()),
        "mean_win": mean_win,
        "mean_loss": mean_loss,
        "payoff_ratio": payoff,
    }


def main() -> None:
    adjusted = load_adjusted()
    tradability = load_tradability(adjusted)

    baseline = build_simple_breakout_signals(
        adjusted,
        tradability[
            ["date", "stock_id", "observed_trade", "valid_ohlc"]
        ],
        config=BreakoutSignalConfig(
            lookback=250,
            universe_fraction=0.25,
        ),
    )
    baseline = baseline[
        baseline["signal_date"].between(
            SIGNAL_START,
            SIGNAL_END,
        )
    ][["signal_date", "stock_id"]].copy()

    quarantined = pit_unsafe_ca_tickers(
        start=SIGNAL_START,
        end=SIGNAL_END,
    )
    excluded = set(quarantined) | COMMON_SUPPORT_EXCLUDED_TICKERS
    baseline = baseline[
        ~baseline["stock_id"].astype(str).isin(excluded)
    ].copy()
    baseline["signal_date"] = pd.to_datetime(
        baseline["signal_date"],
        errors="coerce",
    ).dt.normalize()
    baseline["stock_id"] = baseline["stock_id"].astype(str)
    baseline = baseline.drop_duplicates(
        ["signal_date", "stock_id"]
    ).sort_values(["signal_date", "stock_id"])

    eligible = _eligible_turnover_universe(
        adjusted,
        tradability,
        excluded,
    )
    outcomes = _forward_outcomes(
        adjusted=adjusted,
        eligible=eligible,
    )

    baseline_outcomes = baseline.merge(
        outcomes[
            [
                "signal_date",
                "stock_id",
                "forward_return",
                "valid_forward_outcome",
            ]
        ],
        on=["signal_date", "stock_id"],
        how="left",
        validate="one_to_one",
    )
    baseline_valid = baseline_outcomes[
        baseline_outcomes["valid_forward_outcome"].fillna(False)
    ].copy()

    baseline_counts = baseline_valid.groupby(
        "signal_date"
    ).size()

    pool = outcomes[
        outcomes["valid_forward_outcome"]
    ].copy()
    baseline_pairs = set(
        zip(
            baseline["signal_date"].astype("int64"),
            baseline["stock_id"],
        )
    )
    pool = pool[
        [
            (int(pd.Timestamp(d).value), str(t)) not in baseline_pairs
            for d, t in zip(pool["signal_date"], pool["stock_id"])
        ]
    ].copy()

    pool_by_day = {
        pd.Timestamp(day): group[
            ["stock_id", "forward_return"]
        ].sort_values("stock_id").reset_index(drop=True)
        for day, group in pool.groupby("signal_date")
    }

    insufficient = []
    for day, count in baseline_counts.items():
        available = len(pool_by_day.get(pd.Timestamp(day), ()))
        if available < int(count):
            insufficient.append(
                (pd.Timestamp(day), int(count), int(available))
            )
    if insufficient:
        sample = ", ".join(
            f"{d.date()}:need={need},have={have}"
            for d, need, have in insufficient[:10]
        )
        raise SystemExit(
            "BLOCKED: insufficient same-day matched pool: " + sample
        )

    baseline_stats = _summary(
        baseline_valid["forward_return"].to_numpy(dtype=float)
    )

    permutation_rows = []
    for k in range(N_PERMUTATIONS):
        rng = np.random.default_rng(SEED_BASE + k)
        sampled_parts = []
        for day, count in baseline_counts.items():
            day_pool = pool_by_day[pd.Timestamp(day)]
            chosen = rng.choice(
                len(day_pool),
                size=int(count),
                replace=False,
            )
            sampled_parts.append(
                day_pool.iloc[chosen]["forward_return"].to_numpy(
                    dtype=float
                )
            )
        values = np.concatenate(sampled_parts)
        stats = _summary(values)
        permutation_rows.append(
            {
                "permutation": k + 1,
                "seed": SEED_BASE + k,
                **stats,
            }
        )

    null = pd.DataFrame(permutation_rows)
    empirical_p_expectancy = (
        1
        + int(
            null["expectancy"].ge(
                baseline_stats["expectancy"]
            ).sum()
        )
    ) / (N_PERMUTATIONS + 1)
    empirical_p_win_rate = (
        1
        + int(
            null["win_rate"].ge(
                baseline_stats["win_rate"]
            ).sum()
        )
    ) / (N_PERMUTATIONS + 1)

    expectancy_percentile = float(
        null["expectancy"].lt(
            baseline_stats["expectancy"]
        ).mean()
    )
    win_rate_percentile = float(
        null["win_rate"].lt(
            baseline_stats["win_rate"]
        ).mean()
    )

    baseline_coverage = (
        len(baseline_valid) / len(baseline)
        if len(baseline)
        else float("nan")
    )

    checks = {
        "500_prespecified_permutations_complete": len(null)
        == N_PERMUTATIONS,
        "same_day_candidate_counts_preserved": True,
        "same_day_tradable_top_turnover_pool_used": True,
        "baseline_pairs_excluded_from_control_pool": True,
        "common_support_exclusion_active": not bool(
            set(baseline["stock_id"]) & excluded
        ),
        "baseline_valid_outcomes_nonempty": len(baseline_valid) > 0,
    }
    status = "PASS" if all(checks.values()) else "FAIL"

    q = null[
        ["expectancy", "win_rate", "payoff_ratio"]
    ].quantile([0.01, 0.05, 0.50, 0.95, 0.99])

    lines = [
        "# Conditional 500-Permutation Signal-Edge Falsification",
        "",
        f"Status: **{status}**",
        "",
        "Purpose: test breakout-specific cross-sectional information without portfolio-capacity randomization. Controls are sampled only from same-day actually-tradable names in the same top-25%-turnover eligible universe, preserving the baseline valid candidate count on every signal date.",
        "",
        "## Design",
        "",
        f"- permutations: {N_PERMUTATIONS}",
        f"- seed range: {SEED_BASE} through {SEED_BASE + N_PERMUTATIONS - 1}",
        f"- primary forward horizon: {PRIMARY_HORIZON_SESSIONS} market sessions after next-session entry",
        "- entry outcome coordinate: next-market-session adjusted research open",
        "- exit outcome coordinate: adjusted research close exactly 250 market sessions after entry",
        "- adjusted prices are used here only for research/falsification outcome measurement; they are not execution/accounting prices",
        "- control pool: same signal date, observed_trade=True, valid_ohlc=True, valid price geometry, positive turnover, top 25% turnover, common-support exclusions applied",
        "- baseline breakout pairs are excluded from the same-day control pool",
        "- no portfolio max-position rule, capacity lottery, cash sizing, or random slot selection is used in this diagnostic",
        "",
        "## Baseline candidate-level statistics",
        "",
        f"- raw baseline signal pairs: {len(baseline):,}",
        f"- valid fixed-horizon outcomes: {len(baseline_valid):,}",
        f"- valid-outcome coverage: {baseline_coverage*100:.2f}%",
        f"- per-candidate expectancy: {baseline_stats['expectancy']*100:.4f}%",
        f"- median return: {baseline_stats['median']*100:.4f}%",
        f"- win rate: {baseline_stats['win_rate']*100:.2f}%",
        f"- mean winner: {baseline_stats['mean_win']*100:.4f}%",
        f"- mean loser: {baseline_stats['mean_loss']*100:.4f}%",
        f"- payoff ratio: {baseline_stats['payoff_ratio']:.4f}",
        "",
        "## Empirical null distribution",
        "",
        f"- expectancy percentile of baseline: {expectancy_percentile*100:.2f}%",
        f"- one-sided empirical p-value, expectancy >= baseline: {empirical_p_expectancy:.4f}",
        f"- win-rate percentile of baseline: {win_rate_percentile*100:.2f}%",
        f"- one-sided empirical p-value, win rate >= baseline: {empirical_p_win_rate:.4f}",
        "",
        "| Quantile | Expectancy | Win rate | Payoff ratio |",
        "|---:|---:|---:|---:|",
    ]
    for quantile, row in q.iterrows():
        lines.append(
            f"| {quantile*100:.0f}% | {row['expectancy']*100:.4f}% "
            f"| {row['win_rate']*100:.2f}% | {row['payoff_ratio']:.4f} |"
        )

    lines += [
        "",
        "## Operational gates",
        "",
        "| Gate | Result |",
        "|---|---|",
    ]
    for name, ok in checks.items():
        lines.append(
            f"| {name} | {'PASS' if ok else 'FAIL'} |"
        )

    lines += [
        "",
        "## Interpretation boundary",
        "",
        "This diagnostic isolates candidate-level signal information and deliberately removes the portfolio-capacity lottery that confounded the earlier single-permutation portfolio placebo. It does not reproduce stop-loss, cash, settlement, or path-dependent portfolio mechanics and therefore is not an executable performance estimate. Portfolio-level seed sensitivity remains a separate diagnostic.",
    ]

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    REPORT_PATH.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    if status != "PASS":
        raise SystemExit(
            "FAIL: signal-edge falsification operational gate failed"
        )


if __name__ == "__main__":
    main()
