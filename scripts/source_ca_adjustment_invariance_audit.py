#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd
import yaml

from astraquant.research.ca_adjustment_audit import (
    asof_metrics_from_raw_and_events,
    classify_feature_rows,
    future_factor,
    metrics_for_close,
    valid_adjustment_events,
)
from astraquant.research.config_io import load_universe_config
from astraquant.research.universe_engine import UniverseCompiler, UniverseContext


ROOT = Path(".").resolve()
CONFIG_PATH = Path(os.environ.get(
    "CA_INVARIANCE_CONFIG",
    "configs/quality/ca_adjustment_invariance_audit_v1.yaml",
))
SOURCE_ROOT = Path(os.environ.get(
    "SOURCE_ROOT",
    "source_runtime/minervini_picks/data",
)).resolve()
EXCLUSIONS_PATH = Path("docs/SOURCE_CA_PIT_EXCLUSIONS.csv")
DICTIONARY_PATH = Path("out/pit_feature_matrix_layer1_v1_dictionary.csv")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _read_years(kind: str, years: range) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for year in years:
        path = SOURCE_ROOT / kind / (
            f"prices_adj_{year}.parquet"
            if kind == "adj"
            else f"prices_raw_{year}.parquet"
        )
        if not path.exists():
            raise SystemExit(f"BLOCKED: missing source file {path}")
        cols = [
            "date", "stock_id", "open", "max", "min", "close",
            "Trading_Volume", "Trading_money",
        ]
        frame = pd.read_parquet(path, columns=cols)
        frame["date"] = pd.to_datetime(
            frame["date"], errors="coerce"
        ).dt.normalize()
        frame["stock_id"] = frame["stock_id"].astype(str)
        if frame.duplicated(["date", "stock_id"]).any():
            raise SystemExit(
                f"BLOCKED: duplicate source keys in {path}"
            )
        parts.append(frame)
    return pd.concat(parts, ignore_index=True)


def _load_tradability(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    path = SOURCE_ROOT / "reference" / "tradability.parquet"
    frame = pd.read_parquet(
        path,
        columns=["date", "stock_id", "observed_trade", "valid_ohlc"],
    )
    frame["date"] = pd.to_datetime(
        frame["date"], errors="coerce"
    ).dt.normalize()
    frame["stock_id"] = frame["stock_id"].astype(str)
    frame = frame[
        frame["date"].between(start, end, inclusive="both")
    ].copy()
    if frame.duplicated(["date", "stock_id"]).any():
        raise SystemExit("BLOCKED: duplicate tradability keys")
    return frame


def _load_events(cfg: dict) -> tuple[pd.DataFrame, dict[str, object]]:
    path = SOURCE_ROOT / "adj" / "dividend_events.parquet"
    raw = pd.read_parquet(path)
    events = valid_adjustment_events(
        raw,
        ratio_min=float(cfg["adjustment_ratio_min"]),
        ratio_max=float(cfg["adjustment_ratio_max"]),
    )
    meta = {
        "source_rows": int(len(raw)),
        "valid_grouped_event_rows": int(len(events)),
        "columns": [str(x) for x in raw.columns],
        "first_event_date": (
            None
            if events.empty
            else events["date"].min().date().isoformat()
        ),
        "last_event_date": (
            None
            if events.empty
            else events["date"].max().date().isoformat()
        ),
        "has_known_at_column": any(
            str(c).lower() in {"known_at", "known_date", "publish_time", "published_at"}
            for c in raw.columns
        ),
        "event_date_semantics": (
            "effective/adjustment date used by build_adj.py: historical rows with "
            "price_date < event_date receive after_price/before_price"
        ),
    }
    return events, meta


def _year_stats_template(year: int) -> dict[str, object]:
    return {
        "year": year,
        "prefilter_union_rows": 0,
        "prefilter_unique_stocks": set(),
        "comparable_price_rows": 0,
        "comparable_unique_stocks": set(),
        "missing_raw_rows": 0,
        "missing_adjusted_rows": 0,
        "future_factor_affected_rows": 0,
        "future_factor_affected_stocks": set(),
        "reconstruction_price_mismatch_rows": 0,
        "reconstruction_price_mismatch_stocks": set(),
        "volume_mismatch_rows": 0,
        "amount_mismatch_rows": 0,
        "ma120_ready_rows": 0,
        "ma120_value_diff_gt_tol_rows": 0,
        "ma120_value_diff_stocks": set(),
        "ma120_gate_flip_model_rows": 0,
        "ma120_gate_flip_model_stocks": set(),
        "ma120_gate_flip_actual_rows": 0,
        "ma120_gate_flip_actual_stocks": set(),
        "ma120_near_threshold_rows": 0,
        "n60_ready_rows": 0,
        "n60_signal_flip_model_rows": 0,
        "n60_signal_flip_model_stocks": set(),
        "n60_signal_flip_actual_rows": 0,
        "n60_signal_flip_actual_stocks": set(),
        "n60_near_threshold_rows": 0,
        "universe_comparable_rows": 0,
        "universe_base_added_under_raw": 0,
        "universe_base_removed_under_raw": 0,
        "universe_base_diff_stocks": set(),
        "universe_final_added_under_raw": 0,
        "universe_final_removed_under_raw": 0,
        "universe_final_diff_stocks": set(),
        "universe_rank_ripple_rows": 0,
    }


def _inc_set(stats: dict, key: str, stock: str, mask: np.ndarray) -> None:
    if bool(np.any(mask)):
        stats[key].add(stock)


def _add_cases(
    cases: list[dict[str, object]],
    per_reason: dict[str, int],
    *,
    reason: str,
    limit: int,
    frame: pd.DataFrame,
    mask: np.ndarray | pd.Series,
    columns: list[str],
) -> None:
    remaining = limit - per_reason.get(reason, 0)
    if remaining <= 0:
        return
    take = frame.loc[np.asarray(mask, dtype=bool), columns].head(remaining)
    for row in take.to_dict("records"):
        row = {"reason": reason, **row}
        cases.append(row)
    per_reason[reason] = per_reason.get(reason, 0) + len(take)


def _numeric_not_equal(a: pd.Series, b: pd.Series, atol: float) -> pd.Series:
    x = pd.to_numeric(a, errors="coerce")
    y = pd.to_numeric(b, errors="coerce")
    comparable = x.notna() & y.notna()
    out = pd.Series(False, index=a.index)
    out.loc[comparable] = ~np.isclose(
        x.loc[comparable].to_numpy(float),
        y.loc[comparable].to_numpy(float),
        rtol=0.0,
        atol=float(atol),
    )
    return out


def _feature_audit(
    *,
    comparable: pd.DataFrame,
    events: pd.DataFrame,
    cfg: dict,
    yearly: dict[int, dict[str, object]],
    cases: list[dict[str, object]],
    case_counts: dict[str, int],
) -> None:
    audit_start = pd.Timestamp(cfg["audit_start"])
    audit_end = pd.Timestamp(cfg["audit_end"])
    ma_window = int(cfg["ma_window"])
    breakout = int(cfg["breakout_lookback"])
    round_decimals = int(cfg["source_price_round_decimals"])
    tol = cfg["tolerances"]
    ma_atol = float(tol["ma_ratio_abs"])
    price_atol = float(tol["reconstruction_price_abs"])
    near_ma = float(tol["near_ma_threshold_abs"])
    near_break = float(tol["near_breakout_margin_abs"])
    case_limit = int(cfg["case_limit_per_reason"])

    event_groups = {
        sid: g[["date", "ratio"]].copy()
        for sid, g in events.groupby("stock_id", sort=False)
    }

    for stock, g0 in comparable.groupby("stock_id", sort=True):
        g = g0.sort_values("date", kind="stable").reset_index(drop=True)
        ev = event_groups.get(stock)
        if ev is None:
            ev_dates = np.array([], dtype="datetime64[ns]")
            ev_ratios = np.array([], dtype=float)
        else:
            ev_dates = ev["date"].to_numpy(dtype="datetime64[ns]")
            ev_ratios = ev["ratio"].to_numpy(float)

        ff = future_factor(g["date"], ev_dates, ev_ratios)
        raw_close = pd.to_numeric(g["raw_close"], errors="coerce")
        actual_close = pd.to_numeric(g["adj_close"], errors="coerce")
        modeled_close = np.round(
            raw_close.to_numpy(float) * ff,
            round_decimals,
        )

        full_metrics = metrics_for_close(
            pd.Series(modeled_close),
            ma_window=ma_window,
            breakout_lookback=breakout,
        )
        actual_metrics = metrics_for_close(
            actual_close.reset_index(drop=True),
            ma_window=ma_window,
            breakout_lookback=breakout,
        )
        target = g["date"].between(
            audit_start, audit_end, inclusive="both"
        ).to_numpy()
        asof_metrics = asof_metrics_from_raw_and_events(
            dates=g["date"],
            raw_close=raw_close,
            full_factor=ff,
            ma_window=ma_window,
            breakout_lookback=breakout,
            round_decimals=round_decimals,
            target_mask=target,
        )

        work = g.copy()
        work["future_factor_after_t"] = ff
        work["modeled_full_close"] = modeled_close
        work["modeled_asof_close_t"] = np.round(
            raw_close.to_numpy(float),
            round_decimals,
        )
        work["actual_close_to_ma120"] = actual_metrics["close_to_ma"].to_numpy()
        work["modeled_full_close_to_ma120"] = full_metrics["close_to_ma"].to_numpy()
        work["modeled_asof_close_to_ma120"] = asof_metrics["close_to_ma"].to_numpy()
        work["actual_ma120_pass"] = actual_metrics["ma_pass"].to_numpy(bool)
        work["modeled_full_ma120_pass"] = full_metrics["ma_pass"].to_numpy(bool)
        work["modeled_asof_ma120_pass"] = asof_metrics["ma_pass"].to_numpy(bool)
        work["actual_n60_signal"] = actual_metrics["breakout_signal"].to_numpy(bool)
        work["modeled_full_n60_signal"] = full_metrics["breakout_signal"].to_numpy(bool)
        work["modeled_asof_n60_signal"] = asof_metrics["breakout_signal"].to_numpy(bool)
        work["modeled_full_breakout_margin"] = full_metrics["breakout_margin"].to_numpy()
        work["modeled_asof_breakout_margin"] = asof_metrics["breakout_margin"].to_numpy()
        work["modeled_asof_previous_margin"] = asof_metrics["previous_margin"].to_numpy()
        work["reconstruction_abs_diff"] = (
            actual_close - pd.Series(modeled_close)
        ).abs().to_numpy()

        w = work.loc[target].reset_index(drop=True)
        if w.empty:
            continue

        years = w["date"].dt.year.to_numpy(int)
        model_ma_ready = (
            pd.to_numeric(w["modeled_full_close_to_ma120"], errors="coerce").notna()
            & pd.to_numeric(w["modeled_asof_close_to_ma120"], errors="coerce").notna()
        )
        actual_ma_ready = (
            pd.to_numeric(w["actual_close_to_ma120"], errors="coerce").notna()
            & pd.to_numeric(w["modeled_asof_close_to_ma120"], errors="coerce").notna()
        )
        ma_model_diff = (
            pd.to_numeric(w["modeled_full_close_to_ma120"], errors="coerce")
            - pd.to_numeric(w["modeled_asof_close_to_ma120"], errors="coerce")
        ).abs().gt(ma_atol) & model_ma_ready
        ma_model_flip = (
            w["modeled_full_ma120_pass"].astype(bool)
            != w["modeled_asof_ma120_pass"].astype(bool)
        ) & model_ma_ready
        ma_actual_flip = (
            w["actual_ma120_pass"].astype(bool)
            != w["modeled_asof_ma120_pass"].astype(bool)
        ) & actual_ma_ready
        ma_near = (
            pd.to_numeric(w["modeled_full_close_to_ma120"], errors="coerce").abs().le(near_ma)
            | pd.to_numeric(w["modeled_asof_close_to_ma120"], errors="coerce").abs().le(near_ma)
        ) & model_ma_ready

        n60_ready = (
            pd.to_numeric(w["modeled_full_breakout_margin"], errors="coerce").notna()
            & pd.to_numeric(w["modeled_asof_breakout_margin"], errors="coerce").notna()
            & pd.to_numeric(w["modeled_asof_previous_margin"], errors="coerce").notna()
        )
        n60_model_flip = (
            w["modeled_full_n60_signal"].astype(bool)
            != w["modeled_asof_n60_signal"].astype(bool)
        ) & n60_ready
        actual_n60_ready = (
            pd.to_numeric(
                actual_metrics.loc[target, "breakout_margin"].reset_index(drop=True),
                errors="coerce",
            ).notna()
            & pd.to_numeric(w["modeled_asof_breakout_margin"], errors="coerce").notna()
        )
        n60_actual_flip = (
            w["actual_n60_signal"].astype(bool)
            != w["modeled_asof_n60_signal"].astype(bool)
        ) & actual_n60_ready
        n60_near = (
            pd.to_numeric(w["modeled_full_breakout_margin"], errors="coerce").abs().le(near_break)
            | pd.to_numeric(w["modeled_asof_breakout_margin"], errors="coerce").abs().le(near_break)
            | pd.to_numeric(w["modeled_asof_previous_margin"], errors="coerce").abs().le(near_break)
        ) & n60_ready

        reconstruction_bad = (
            pd.to_numeric(w["reconstruction_abs_diff"], errors="coerce")
            .gt(price_atol)
        )
        factor_affected = ~np.isclose(
            pd.to_numeric(w["future_factor_after_t"], errors="coerce").to_numpy(float),
            1.0,
            rtol=1e-13,
            atol=1e-15,
        )

        volume_bad = _numeric_not_equal(
            w["adj_Trading_Volume"],
            w["raw_Trading_Volume"],
            atol=0.0,
        )
        amount_bad = _numeric_not_equal(
            w["adj_Trading_money"],
            w["raw_Trading_money"],
            atol=0.0,
        )

        for year in sorted(set(years.tolist())):
            m = years == year
            s = yearly[year]
            s["comparable_price_rows"] += int(m.sum())
            s["comparable_unique_stocks"].add(stock)
            s["future_factor_affected_rows"] += int((factor_affected & m).sum())
            _inc_set(s, "future_factor_affected_stocks", stock, factor_affected & m)
            s["reconstruction_price_mismatch_rows"] += int((reconstruction_bad.to_numpy() & m).sum())
            _inc_set(s, "reconstruction_price_mismatch_stocks", stock, reconstruction_bad.to_numpy() & m)
            s["volume_mismatch_rows"] += int((volume_bad.to_numpy() & m).sum())
            s["amount_mismatch_rows"] += int((amount_bad.to_numpy() & m).sum())
            s["ma120_ready_rows"] += int((model_ma_ready.to_numpy() & m).sum())
            s["ma120_value_diff_gt_tol_rows"] += int((ma_model_diff.to_numpy() & m).sum())
            _inc_set(s, "ma120_value_diff_stocks", stock, ma_model_diff.to_numpy() & m)
            s["ma120_gate_flip_model_rows"] += int((ma_model_flip.to_numpy() & m).sum())
            _inc_set(s, "ma120_gate_flip_model_stocks", stock, ma_model_flip.to_numpy() & m)
            s["ma120_gate_flip_actual_rows"] += int((ma_actual_flip.to_numpy() & m).sum())
            _inc_set(s, "ma120_gate_flip_actual_stocks", stock, ma_actual_flip.to_numpy() & m)
            s["ma120_near_threshold_rows"] += int((ma_near.to_numpy() & m).sum())
            s["n60_ready_rows"] += int((n60_ready.to_numpy() & m).sum())
            s["n60_signal_flip_model_rows"] += int((n60_model_flip.to_numpy() & m).sum())
            _inc_set(s, "n60_signal_flip_model_stocks", stock, n60_model_flip.to_numpy() & m)
            s["n60_signal_flip_actual_rows"] += int((n60_actual_flip.to_numpy() & m).sum())
            _inc_set(s, "n60_signal_flip_actual_stocks", stock, n60_actual_flip.to_numpy() & m)
            s["n60_near_threshold_rows"] += int((n60_near.to_numpy() & m).sum())

        case_cols = [
            "date", "stock_id", "raw_close", "adj_close",
            "future_factor_after_t", "modeled_full_close",
            "reconstruction_abs_diff", "actual_close_to_ma120",
            "modeled_full_close_to_ma120", "modeled_asof_close_to_ma120",
            "actual_ma120_pass", "modeled_full_ma120_pass",
            "modeled_asof_ma120_pass", "actual_n60_signal",
            "modeled_full_n60_signal", "modeled_asof_n60_signal",
            "modeled_full_breakout_margin", "modeled_asof_breakout_margin",
            "modeled_asof_previous_margin",
        ]
        _add_cases(cases, case_counts, reason="RECONSTRUCTION_MISMATCH",
                   limit=case_limit, frame=w, mask=reconstruction_bad, columns=case_cols)
        _add_cases(cases, case_counts, reason="MA120_VALUE_DIFF_GT_TOL",
                   limit=case_limit, frame=w, mask=ma_model_diff, columns=case_cols)
        _add_cases(cases, case_counts, reason="MA120_GATE_FLIP_MODELED",
                   limit=case_limit, frame=w, mask=ma_model_flip, columns=case_cols)
        _add_cases(cases, case_counts, reason="MA120_GATE_FLIP_ACTUAL_VS_ASOF",
                   limit=case_limit, frame=w, mask=ma_actual_flip, columns=case_cols)
        _add_cases(cases, case_counts, reason="N60_SIGNAL_FLIP_MODELED",
                   limit=case_limit, frame=w, mask=n60_model_flip, columns=case_cols)
        _add_cases(cases, case_counts, reason="N60_SIGNAL_FLIP_ACTUAL_VS_ASOF",
                   limit=case_limit, frame=w, mask=n60_actual_flip, columns=case_cols)


def _universe_audit(
    *,
    domain: pd.DataFrame,
    tradability: pd.DataFrame,
    cfg: dict,
    yearly: dict[int, dict[str, object]],
    cases: list[dict[str, object]],
    case_counts: dict[str, int],
) -> dict[str, int]:
    start = pd.Timestamp(cfg["audit_start"])
    end = pd.Timestamp(cfg["audit_end"])
    x = domain[
        domain["date"].between(start, end, inclusive="both")
        & domain["raw_close"].notna()
        & domain["adj_close"].notna()
    ].copy()
    trad = tradability[
        tradability["date"].between(start, end, inclusive="both")
    ].copy()
    x = x.merge(
        trad,
        on=["date", "stock_id"],
        how="left",
        validate="one_to_one",
    )
    x["observed_trade"] = x["observed_trade"].fillna(False).astype(bool)
    x["valid_ohlc"] = x["valid_ohlc"].fillna(False).astype(bool)
    x["Trading_money"] = pd.to_numeric(
        x["adj_Trading_money"], errors="coerce"
    )

    expected_sha = str(cfg["p2_060_exclusion_sha256"])
    if _sha256(EXCLUSIONS_PATH) != expected_sha:
        raise SystemExit("BLOCKED: P2-060 exclusion SHA drift")
    excluded = set(pd.read_csv(
        EXCLUSIONS_PATH, dtype={"ticker": str}
    )["ticker"].astype(str))

    universe_cfg = load_universe_config(cfg["universe_config"])
    context = UniverseContext(
        p2_060_excluded_tickers=frozenset(excluded),
        p2_060_exclusion_sha256=expected_sha,
        theme_root=None,
    )

    base = x[[
        "date", "stock_id", "Trading_money",
        "observed_trade", "valid_ohlc",
    ]].copy()
    adj_panel = base.copy()
    adj_panel["close"] = pd.to_numeric(x["adj_close"], errors="coerce")
    raw_panel = base.copy()
    raw_panel["close"] = pd.to_numeric(x["raw_close"], errors="coerce")

    compiler = UniverseCompiler()
    adj_mask = compiler.compile(universe_cfg, adj_panel, context).frame.rename(
        columns={
            "base_pass": "adj_base_pass",
            "counts": "adj_counts",
        }
    )
    raw_mask = compiler.compile(universe_cfg, raw_panel, context).frame.rename(
        columns={
            "base_pass": "raw_base_pass",
            "counts": "raw_counts",
        }
    )
    compared = (
        x[["date", "stock_id", "raw_close", "adj_close", "Trading_money"]]
        .merge(
            adj_mask[["date", "stock_id", "adj_base_pass", "adj_counts"]],
            on=["date", "stock_id"],
            how="left",
            validate="one_to_one",
        )
        .merge(
            raw_mask[["date", "stock_id", "raw_base_pass", "raw_counts"]],
            on=["date", "stock_id"],
            how="left",
            validate="one_to_one",
        )
    )
    base_add = ~compared["adj_base_pass"] & compared["raw_base_pass"]
    base_remove = compared["adj_base_pass"] & ~compared["raw_base_pass"]
    final_add = ~compared["adj_counts"] & compared["raw_counts"]
    final_remove = compared["adj_counts"] & ~compared["raw_counts"]
    ripple = (compared["adj_base_pass"] == compared["raw_base_pass"]) & (
        compared["adj_counts"] != compared["raw_counts"]
    )

    case_limit = int(cfg["case_limit_per_reason"])
    for year, g in compared.groupby(compared["date"].dt.year, sort=True):
        year = int(year)
        s = yearly[year]
        idx = g.index
        s["universe_comparable_rows"] = int(len(g))
        s["universe_base_added_under_raw"] = int(base_add.loc[idx].sum())
        s["universe_base_removed_under_raw"] = int(base_remove.loc[idx].sum())
        s["universe_base_diff_stocks"].update(
            g.loc[
                base_add.loc[idx].to_numpy() | base_remove.loc[idx].to_numpy(),
                "stock_id",
            ].astype(str)
        )
        s["universe_final_added_under_raw"] = int(final_add.loc[idx].sum())
        s["universe_final_removed_under_raw"] = int(final_remove.loc[idx].sum())
        s["universe_final_diff_stocks"].update(
            g.loc[
                final_add.loc[idx].to_numpy() | final_remove.loc[idx].to_numpy(),
                "stock_id",
            ].astype(str)
        )
        s["universe_rank_ripple_rows"] = int(ripple.loc[idx].sum())

    compared["near_10_twd"] = (
        (pd.to_numeric(compared["raw_close"], errors="coerce") - 10).abs()
        .le(float(cfg["tolerances"]["near_close_threshold_twd"]))
        | (pd.to_numeric(compared["adj_close"], errors="coerce") - 10).abs()
        .le(float(cfg["tolerances"]["near_close_threshold_twd"]))
    )
    cols = [
        "date", "stock_id", "raw_close", "adj_close",
        "Trading_money", "adj_base_pass", "raw_base_pass",
        "adj_counts", "raw_counts", "near_10_twd",
    ]
    _add_cases(cases, case_counts, reason="CLOSE_THRESHOLD_ADDED_UNDER_RAW",
               limit=case_limit, frame=compared, mask=base_add, columns=cols)
    _add_cases(cases, case_counts, reason="CLOSE_THRESHOLD_REMOVED_UNDER_RAW",
               limit=case_limit, frame=compared, mask=base_remove, columns=cols)
    _add_cases(cases, case_counts, reason="ALL_LIQUID_ADDED_UNDER_RAW",
               limit=case_limit, frame=compared, mask=final_add, columns=cols)
    _add_cases(cases, case_counts, reason="ALL_LIQUID_REMOVED_UNDER_RAW",
               limit=case_limit, frame=compared, mask=final_remove, columns=cols)
    _add_cases(cases, case_counts, reason="ALL_LIQUID_RANK_RIPPLE",
               limit=case_limit, frame=compared, mask=ripple, columns=cols)

    return {
        "base_diff_rows": int((base_add | base_remove).sum()),
        "final_diff_rows": int((final_add | final_remove).sum()),
        "final_diff_stocks": int(
            compared.loc[final_add | final_remove, "stock_id"].nunique()
        ),
        "rank_ripple_rows": int(ripple.sum()),
    }


def _finalize_yearly(yearly: dict[int, dict[str, object]]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for year in sorted(yearly):
        row: dict[str, object] = {}
        for key, value in yearly[year].items():
            if isinstance(value, set):
                row[key.replace("_stocks", "_unique_stocks")] = len(value)
            else:
                row[key] = value
        rows.append(row)
    return pd.DataFrame(rows)


def _report(
    *,
    cfg: dict,
    yearly: pd.DataFrame,
    classification: pd.DataFrame,
    event_meta: dict[str, object],
    universe_summary: dict[str, int],
    manifest: dict[str, object],
) -> str:
    total = yearly.select_dtypes(include="number").sum(numeric_only=True)
    ma_flips = int(total.get("ma120_gate_flip_model_rows", 0))
    n60_flips = int(total.get("n60_signal_flip_model_rows", 0))
    ma_value_diffs = int(total.get("ma120_value_diff_gt_tol_rows", 0))
    final_diff = int(total.get("universe_final_added_under_raw", 0)) + int(
        total.get("universe_final_removed_under_raw", 0)
    )
    recon = int(total.get("reconstruction_price_mismatch_rows", 0))

    lines = [
        "# 公司行動回溯調整實際影響稽核",
        "",
        "狀態：**AUDIT COMPLETE / AWAITING REVIEW**。本項只比較資料、特徵與候選資格；沒有策略效果、報酬、勝率或期望值。",
        "",
        "## 稽核邊界",
        "",
        f"- source revision：`{cfg['source_revision']}`",
        f"- E1：{cfg['audit_start']}～{cfg['audit_end']}；暖機自 {cfg['load_start']}。",
        "- 固定股票日集合從 source RAW/adjusted 合併後、套 universe 前開始；正式母體沒有被修改。",
        "- 本稽核把 dividend_events.date 視為**事件生效／調整日**，只回答「晚於 T 發生的事件因子」會不會改變 T 的資料／公式。",
        "- dividend_events 沒有可用的歷史 known_at/publish timestamp；所以「晚於 T 才知道」是另一個 PIT 問題，本報告不把 effective date 冒充 known date。",
        "",
        "## 來源算法證據",
        "",
        "- `build_adj.py`：對每個股票日，factor = 該日之後所有有效事件的 `after_price/before_price` 連乘；OHLC × factor 後 round(4)。",
        "- 合法 ratio 範圍 0.5～1.2，正倍率；同日多事件連乘。",
        "- `daily_update_adj.py`：新事件會回寫所有舊年度 OHLC；**Trading_Volume 與 Trading_money 不乘 adjustment factor**。",
        f"- event source rows={event_meta['source_rows']:,}；有效同日聚合事件={event_meta['valid_grouped_event_rows']:,}；event range={event_meta['first_event_date']}～{event_meta['last_event_date']}。",
        f"- event table 是否含 known-time 欄：**{event_meta['has_known_at_column']}**。",
        "",
        "## 事前固定容差",
        "",
        f"- MA ratio value absolute tolerance：{cfg['tolerances']['ma_ratio_abs']}",
        f"- RAW→full-adjusted reconstruction price tolerance：TWD {cfg['tolerances']['reconstruction_price_abs']}",
        f"- MA gate / N_SESSION_HIGH 布林翻轉：**不套容差，直接比較**。",
        f"- near-MA band：±{cfg['tolerances']['near_ma_threshold_abs']}；near-breakout margin：±{cfg['tolerances']['near_breakout_margin_abs']}；close=10 診斷帶：±TWD {cfg['tolerances']['near_close_threshold_twd']}。",
        "",
        "## 核心結果",
        "",
        f"- modeled future-factor removal：MA120 value diff > tolerance = **{ma_value_diffs:,}**；MA120 `>=0` flips = **{ma_flips:,}**；N_SESSION_HIGH60 flips = **{n60_flips:,}**。",
        f"- current adjusted close vs RAW×documented-full-factor reconstruction mismatch rows = **{recon:,}**。這些列不能只用『共同倍率抵消』解釋，另受 rounding／資料修訂／未涵蓋事件影響。",
        f"- RAW-close 對照造成 all_liquid final membership 差異 = **{final_diff:,}** rows；distinct stocks={universe_summary['final_diff_stocks']:,}；其中 turnover-rank ripple={universe_summary['rank_ripple_rows']:,} rows。",
        "",
        "### E1 逐年",
        "",
        "| 年 | 可比價格列 | 股票 | future-factor 影響列 | recon mismatch | MA value diff | MA gate flip | N60 flip | RAW門檻新增 | RAW門檻移除 | final新增 | final移除 | rank ripple |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in yearly.itertuples(index=False):
        lines.append(
            f"| {int(r.year)} | {int(r.comparable_price_rows):,} | "
            f"{int(r.comparable_unique_stocks):,} | {int(r.future_factor_affected_rows):,} | "
            f"{int(r.reconstruction_price_mismatch_rows):,} | "
            f"{int(r.ma120_value_diff_gt_tol_rows):,} | {int(r.ma120_gate_flip_model_rows):,} | "
            f"{int(r.n60_signal_flip_model_rows):,} | {int(r.universe_base_added_under_raw):,} | "
            f"{int(r.universe_base_removed_under_raw):,} | {int(r.universe_final_added_under_raw):,} | "
            f"{int(r.universe_final_removed_under_raw):,} | {int(r.universe_rank_ripple_rows):,} |"
        )

    lines += [
        "",
        "## 解讀：特徵值與母體分開",
        "",
        "- `close_to_ma120` 與 N_SESSION_HIGH60 的『future-effective event factor』是固定-key、共同正倍率問題；數學上 ratio／ordering 可抵消，但本報告仍用 frozen source E1 實際資料與 round(4) 流程驗證，布林比較不使用 tolerance。",
        "- 即使上述固定-key公式不變，`all_liquid.base.min_close_twd=10` 讀的是 research panel 的 **adjusted close**。RAW close 診斷對照若改變 base_pass，就會連帶改變同日 turnover top-25% 排名，因此 final universe 可有直接門檻差異與 rank ripple。",
        "- RAW close >=10 只是一個診斷對照，**本次沒有把正式母體改成 RAW**。",
        "- 目前 v1 stock feature parquet 是先套 all_liquid 才持久化；所以只要 final universe 有差異，既有 persisted row set 就不能因某個 ratio 特徵本身不變而直接宣告乾淨。",
        "",
        "## 特徵影響分類",
        "",
        "完整逐 dictionary row 分類見 classification CSV。分類只針對『documented future-effective common positive OHLC factor』：",
        "",
        "- `PROVEN_INVARIANT_FIXED_KEYS_UNIFORM_POSITIVE_FACTOR`：比值、排序、return-based 等公式在固定股票日集合下對共同正倍率不變。",
        "- `PROVEN_NUMERICALLY_AFFECTED_BY_SCALE`：例如 MACD histogram 原值會按倍率縮放；即使 zero-cross sign 可能不變，raw value 與跨股排名不能稱不變。",
        "- `VALUE_INDEPENDENT_OF_OHLC_FACTOR`：volume/amount/market-value/industry 等原值不由此 OHLC factor 直接改寫。",
        "- `INDIRECTLY_AFFECTED_BY_ELIGIBLE_SET`：同日橫截面／產業成分依賴母體，母體一變就需另評估。",
        "- 『值不變』只解除這一種 future-effective factor 的疑慮；**不等於 known-time、source revision、universe membership 或其他 PIT 條件通過**。",
        "",
        "## VCP Round 1 依賴追蹤",
        "",
        "- `configs/research/vcp_round1_three_segment_v1.yaml` 明確使用 `configs/examples/universes/all_liquid.yaml`。",
        "- `source_vcp_round1.py` 從 `source_config_sweep._research_panel()` 取得 adjusted research panel，再走相同 universe compiler 路徑。",
        (
            "- 因本次觀察到 final universe 差異，VCP Round 1 標記：**待影響評估**。既有結果保留、不中止、不重跑，也不直接宣告績效失效。"
            if final_diff
            else "- 本次未觀察到 final universe 差異；VCP Round 1 仍共享此母體路徑，其他 PIT 限制維持。"
        ),
        "",
        "## 最小修正方案（未執行）",
        "",
        "1. **保留**：feature 公式程式、dictionary、market_context、固定-key下已證明不變的數學定義，以及既有 v1 artifact 作為可追溯歷史產物。",
        "2. **另建版本，不覆蓋 v1**：只修正 stock research universe／row membership 的因果價格門檻來源，再由同一 layer1 pipeline 重建受母體影響的 stock artifact 與 cross-sectional ranks；不需要因 MA ratio 本身就把整套公式推倒重寫。",
        "3. 若 reconstruction mismatch 非零，先釐清這些列是 sequential rounding、raw/adjusted source revision、還是 dividend_events 未涵蓋的 corporate action；未釐清前，相關公式只能標『對指定 factor 不變』，不能擴張為『整體 PIT VERIFIED』。",
        "4. historical known-time evidence（EOD/RAW/TRI/industry）仍按第 5 項 integration 契約處理；本稽核沒有補齊發布時間。",
        "",
        "## QA 產物",
        "",
        f"- yearly：`{cfg['outputs']['yearly']}`",
        f"- cases：`{cfg['outputs']['cases']}`（每個 reason 最多 {cfg['case_limit_per_reason']} 筆，無後續報酬）",
        f"- classification：`{cfg['outputs']['classification']}`",
        f"- manifest：`{cfg['outputs']['manifest']}`",
        "",
        "本項沒有修改正式母體、沒有重建正式 feature artifact、沒有修改既有 VCP 結果，並且沒有查 E2/E3 策略效果。",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    source_revision = os.environ.get("SOURCE_REVISION", "").strip()
    if source_revision != str(cfg["source_revision"]):
        raise SystemExit(
            f"BLOCKED: source revision mismatch {source_revision} != {cfg['source_revision']}"
        )

    load_start = pd.Timestamp(cfg["load_start"])
    audit_start = pd.Timestamp(cfg["audit_start"])
    audit_end = pd.Timestamp(cfg["audit_end"])
    years = range(load_start.year, audit_end.year + 1)

    adjusted = _read_years("adj", years).rename(
        columns={
            "open": "adj_open", "max": "adj_max", "min": "adj_min",
            "close": "adj_close", "Trading_Volume": "adj_Trading_Volume",
            "Trading_money": "adj_Trading_money",
        }
    )
    raw = _read_years("raw", years).rename(
        columns={
            "open": "raw_open", "max": "raw_max", "min": "raw_min",
            "close": "raw_close", "Trading_Volume": "raw_Trading_Volume",
            "Trading_money": "raw_Trading_money",
        }
    )

    merged = adjusted.merge(
        raw,
        on=["date", "stock_id"],
        how="outer",
        validate="one_to_one",
        indicator=True,
    )
    merged = merged[
        merged["date"].between(load_start, audit_end, inclusive="both")
        & merged["stock_id"].str.fullmatch(str(cfg["ticker_pattern"]), na=False)
    ].sort_values(["stock_id", "date"], kind="stable").reset_index(drop=True)

    yearly = {
        y: _year_stats_template(y)
        for y in range(audit_start.year, audit_end.year + 1)
    }
    e1 = merged[
        merged["date"].between(audit_start, audit_end, inclusive="both")
    ]
    for year, g in e1.groupby(e1["date"].dt.year, sort=True):
        year = int(year)
        yearly[year]["prefilter_union_rows"] = int(len(g))
        yearly[year]["prefilter_unique_stocks"].update(
            g["stock_id"].astype(str)
        )
        yearly[year]["missing_raw_rows"] = int(
            g["raw_close"].isna().sum()
        )
        yearly[year]["missing_adjusted_rows"] = int(
            g["adj_close"].isna().sum()
        )

    comparable = merged[
        merged["raw_close"].notna() & merged["adj_close"].notna()
    ].copy()

    events, event_meta = _load_events(cfg)
    cases: list[dict[str, object]] = []
    case_counts: dict[str, int] = {}
    _feature_audit(
        comparable=comparable,
        events=events,
        cfg=cfg,
        yearly=yearly,
        cases=cases,
        case_counts=case_counts,
    )

    tradability = _load_tradability(audit_start, audit_end)
    universe_summary = _universe_audit(
        domain=merged,
        tradability=tradability,
        cfg=cfg,
        yearly=yearly,
        cases=cases,
        case_counts=case_counts,
    )

    yearly_frame = _finalize_yearly(yearly)
    dictionary = pd.read_csv(DICTIONARY_PATH)
    classification = classify_feature_rows(dictionary)

    total_ma_flips = int(yearly_frame["ma120_gate_flip_model_rows"].sum())
    total_n60_flips = int(yearly_frame["n60_signal_flip_model_rows"].sum())
    ma_row = classification["column"].eq("close_to_ma120")
    classification.loc[ma_row, "empirical_result"] = (
        f"E1 modeled future-factor removal: gate_flips={total_ma_flips}; "
        f"value_diff_gt_tol={int(yearly_frame['ma120_value_diff_gt_tol_rows'].sum())}"
    )
    n60_row = classification["column"].eq("N_SESSION_HIGH_60")
    classification.loc[n60_row, "empirical_result"] = (
        f"E1 modeled future-factor removal: signal_flips={total_n60_flips}"
    )
    classification["empirical_result"] = classification[
        "empirical_result"
    ].fillna("NOT_RECOMPUTED_THIS_AUDIT")

    out = cfg["outputs"]
    Path(out["yearly"]).parent.mkdir(parents=True, exist_ok=True)
    yearly_frame.to_csv(out["yearly"], index=False)
    pd.DataFrame(cases).sort_values(
        ["reason", "date", "stock_id"], kind="stable"
    ).to_csv(out["cases"], index=False)
    classification.to_csv(out["classification"], index=False)

    manifest = {
        "audit_name": cfg["name"],
        "epoch": "E1",
        "period": [cfg["audit_start"], cfg["audit_end"]],
        "source_revision": cfg["source_revision"],
        "code_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "config_path": str(CONFIG_PATH),
        "config_sha256": _sha256(CONFIG_PATH),
        "source_algorithm": {
            "factor": "product(after_price/before_price for event_date > price_date)",
            "ratio_range": [
                cfg["adjustment_ratio_min"],
                cfg["adjustment_ratio_max"],
            ],
            "price_round_decimals": cfg["source_price_round_decimals"],
            "adjusted_fields": ["open", "max", "min", "close"],
            "not_factor_adjusted": ["Trading_Volume", "Trading_money"],
        },
        "event_metadata": event_meta,
        "tolerances": cfg["tolerances"],
        "prefilter_source": "outer union of RAW and adjusted source keys before universe",
        "modeled_asof_semantics": (
            "remove factors whose effective event_date is after T; this is not "
            "a claim about historical announcement/known time"
        ),
        "ma120_gate_flips_modeled": total_ma_flips,
        "n60_signal_flips_modeled": total_n60_flips,
        "reconstruction_price_mismatch_rows": int(
            yearly_frame["reconstruction_price_mismatch_rows"].sum()
        ),
        "universe_base_diff_rows": universe_summary["base_diff_rows"],
        "universe_final_diff_rows": universe_summary["final_diff_rows"],
        "universe_final_diff_stocks": universe_summary["final_diff_stocks"],
        "universe_rank_ripple_rows": universe_summary["rank_ripple_rows"],
        "vcp_round1_uses_same_all_liquid_path": True,
        "vcp_round1_status": (
            "待影響評估"
            if universe_summary["final_diff_rows"] > 0
            else "共享母體路徑；本次未觀察 final universe 差異"
        ),
        "formal_universe_modified": False,
        "formal_feature_artifact_rebuilt": False,
        "strategy_effect_metrics_computed": False,
        "e2_e3_effects_queried": False,
        "outputs": out,
    }
    Path(out["manifest"]).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    Path(out["report"]).write_text(
        _report(
            cfg=cfg,
            yearly=yearly_frame,
            classification=classification,
            event_meta=event_meta,
            universe_summary=universe_summary,
            manifest=manifest,
        ),
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
