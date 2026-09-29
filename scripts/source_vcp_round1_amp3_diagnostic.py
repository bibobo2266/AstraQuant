#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from astraquant.research.contact_registry import ContactRecord, append_contact_record
from astraquant.research.parameter_sweep import ResearchParameterSweepRunner
from astraquant.research.signal_engine import SignalContext
from astraquant.research.technical_components import vcp_three_segment_details
from astraquant.research.universe_engine import UniverseContext
from astraquant.research.vcp_round1 import build_common_session_panel

from source_config_sweep import (
    EXPECTED_EXCLUSIONS_SHA256,
    _load_exclusions,
    _research_panel,
)


ROOT = Path(".").resolve()
SOURCE_REVISION = os.environ.get("SOURCE_REVISION", "").strip()
ROUND1_SWEEP = Path("configs/research/vcp_round1_three_segment_v1.yaml")
ROUND1_SUMMARY = Path("out/vcp_sweep_round1.csv")
ROUND1_TRADES = Path("out/vcp_sweep_round1_trades.csv")
ROUND1_OPEN = Path("out/vcp_sweep_round1_open_positions.csv")
ROUND1_MANIFEST = Path("out/vcp_sweep_round1_manifest.json")
OUTPUT = Path("out/vcp_round1_amp3_diagnostic.csv")
CONTACT_REGISTRY = Path("docs/CONTACT_REGISTRY.md")
E1_START = pd.Timestamp("2016-01-04")
E1_END = pd.Timestamp("2021-12-31")


def _entry_keys(path: Path) -> set[tuple[str, str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return set()
    frame = pd.read_csv(
        path,
        usecols=["config_id", "stock_id", "signal_date"],
        dtype={"config_id": str, "stock_id": str, "signal_date": str},
    )
    return {
        (
            str(row.config_id),
            str(row.stock_id),
            pd.Timestamp(row.signal_date).date().isoformat(),
        )
        for row in frame.itertuples(index=False)
    }


def main() -> None:
    for path in (
        ROUND1_SWEEP,
        ROUND1_SUMMARY,
        ROUND1_TRADES,
        ROUND1_OPEN,
        ROUND1_MANIFEST,
    ):
        if not path.exists():
            raise SystemExit(f"BLOCKED: missing frozen round1 artifact: {path}")

    manifest = json.loads(ROUND1_MANIFEST.read_text(encoding="utf-8"))
    frozen_source_revision = str(manifest["source_revision"]).strip()
    if not SOURCE_REVISION:
        raise SystemExit("BLOCKED: SOURCE_REVISION is required")
    if SOURCE_REVISION != frozen_source_revision:
        raise SystemExit(
            "BLOCKED: diagnostic source revision differs from frozen round1 "
            f"manifest: current={SOURCE_REVISION} frozen={frozen_source_revision}"
        )

    summary = pd.read_csv(
        ROUND1_SUMMARY,
        dtype={"config_id": str},
    )
    if len(summary) != 108 or summary["config_id"].nunique() != 108:
        raise SystemExit("BLOCKED: frozen round1 summary is not 108 configs")
    expected_signal_count = {
        str(row.config_id): int(row.signal_count)
        for row in summary.itertuples(index=False)
    }

    entered_closed = _entry_keys(ROUND1_TRADES)
    entered_open = _entry_keys(ROUND1_OPEN)
    entered = entered_closed | entered_open

    excluded = _load_exclusions()
    panel, _, _ = _research_panel()
    dates = pd.to_datetime(panel["date"], errors="coerce").dt.normalize()
    numeric_scope = set(
        panel.loc[
            dates.le(E1_END)
            & panel["stock_id"].astype(str).str.fullmatch(
                r"[1-9]\d{3}",
                na=False,
            ),
            "stock_id",
        ].astype(str)
    )
    research_ticker_scope = numeric_scope - set(excluded)
    common_panel = build_common_session_panel(
        panel,
        ticker_scope=research_ticker_scope,
        end=E1_END,
    )

    sweep_runner = ResearchParameterSweepRunner()
    stream = sweep_runner.stream_sweep(
        sweep_config_path=ROUND1_SWEEP,
        root=ROOT,
        panel=common_panel,
        universe_context=UniverseContext(
            p2_060_excluded_tickers=frozenset(excluded),
            p2_060_exclusion_sha256=EXPECTED_EXCLUSIONS_SHA256,
            theme_root=None,
        ),
        signal_context=SignalContext(source_revision=SOURCE_REVISION),
        base_policy=__import__(
            "astraquant.portfolio.policy",
            fromlist=["PortfolioPolicyConfig"],
        ).PortfolioPolicyConfig(
            position_fraction=1.0,
            max_positions=1,
            stop_fraction=None,
            reentry_gap_sessions=0,
            max_hold_sessions=None,
            lot_size=1,
            random_seed=0,
        ),
    )
    if stream.declared_combinations != 108 or stream.skipped_by_constraints != 0:
        raise SystemExit("BLOCKED: round1 grid drifted from 108 unskipped configs")

    rows: list[pd.DataFrame] = []
    candidate_keys: set[tuple[str, str, str]] = set()

    for index, item in enumerate(stream.runs, start=1):
        config_id = f"VCP-R1-{index:03d}"
        details = vcp_three_segment_details(
            panel=common_panel,
            spec=item.prepared.signal_config.trigger,
            cache=sweep_runner.engine.feature_cache,
            context=SignalContext(source_revision=SOURCE_REVISION),
        ).reset_index(drop=True)
        signal = item.prepared.signal_frame.reset_index(drop=True)
        if len(details) != len(signal) or len(signal) != len(common_panel):
            raise RuntimeError(
                f"round1 diagnostic alignment failure for {config_id}"
            )
        selected = (
            signal["counts_as_candidate"].fillna(False).astype(bool)
            & signal["signal_date"].between(
                E1_START,
                E1_END,
                inclusive="both",
            )
        )
        frame = pd.DataFrame(
            {
                "config_id": config_id,
                "base_len": int(item.parameters["trigger.base_len"]),
                "last_contraction": float(
                    item.parameters["trigger.last_contraction"]
                ),
                "dry_up": float(item.parameters["trigger.dry_up"]),
                "breakout_vol": float(
                    item.parameters["trigger.breakout_vol"]
                ),
                "stock_id": signal.loc[
                    selected, "stock_id"
                ].astype(str).to_numpy(),
                "signal_date": pd.to_datetime(
                    signal.loc[selected, "signal_date"]
                ).dt.date.astype(str).to_numpy(),
                "amplitude_1": details.loc[
                    selected, "amplitude_1"
                ].to_numpy(),
                "amplitude_2": details.loc[
                    selected, "amplitude_2"
                ].to_numpy(),
                "amplitude_3": details.loc[
                    selected, "amplitude_3"
                ].to_numpy(),
            }
        )
        expected = expected_signal_count[config_id]
        if len(frame) != expected:
            raise RuntimeError(
                f"round1 candidate count mismatch {config_id}: "
                f"diagnostic={len(frame)} frozen_summary={expected}"
            )
        frame["amplitude3_eq_0"] = frame["amplitude_3"].eq(0.0)
        frame["amplitude3_lt_0_01"] = frame["amplitude_3"].lt(0.01)
        entry_flags = []
        for row in frame.itertuples(index=False):
            key = (row.config_id, str(row.stock_id), str(row.signal_date))
            candidate_keys.add(key)
            entry_flags.append(key in entered)
        frame["entered_trade"] = entry_flags
        rows.append(frame)

    diagnostic = pd.concat(rows, ignore_index=True)
    if len(diagnostic) != int(summary["signal_count"].sum()):
        raise RuntimeError(
            "round1 diagnostic total candidate count does not equal frozen summary"
        )
    missing_entries = entered - candidate_keys
    if missing_entries:
        sample = sorted(missing_entries)[:10]
        raise RuntimeError(
            "frozen round1 entry keys are not a subset of reconstructed "
            f"candidate keys; sample={sample}"
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    diagnostic.to_csv(OUTPUT, index=False)

    append_contact_record(
        CONTACT_REGISTRY,
        ContactRecord(
            result_id="VCP_ROUND1_AMP3_DIAGNOSTIC",
            covered_period="2016-01-04 ~ 2021-12-31",
            contact_date=datetime.now(ZoneInfo("Asia/Taipei")).date(),
            context=(
                "round1 post-hoc amplitude_3 diagnostic only; "
                "no round1 config/result mutation; "
                f"source_revision={SOURCE_REVISION}; "
                "candidate counts checked against frozen 108-config summary"
            ),
        ),
    )

    entered_diag = diagnostic[diagnostic["entered_trade"].astype(bool)]
    by_base = (
        diagnostic.groupby("base_len", as_index=False)
        .agg(
            candidate_count=("config_id", "size"),
            amplitude3_eq_0=("amplitude3_eq_0", "sum"),
            amplitude3_lt_0_01=("amplitude3_lt_0_01", "sum"),
        )
        .to_dict("records")
    )
    top_tickers = (
        diagnostic.loc[
            diagnostic["amplitude3_lt_0_01"].astype(bool),
            "stock_id",
        ]
        .value_counts()
        .head(10)
        .to_dict()
    )
    result = {
        "candidate_count": int(len(diagnostic)),
        "candidate_amplitude3_eq_0": int(
            diagnostic["amplitude3_eq_0"].sum()
        ),
        "candidate_amplitude3_lt_0_01": int(
            diagnostic["amplitude3_lt_0_01"].sum()
        ),
        "entered_count": int(len(entered_diag)),
        "entered_amplitude3_eq_0": int(
            entered_diag["amplitude3_eq_0"].sum()
        ),
        "entered_amplitude3_lt_0_01": int(
            entered_diag["amplitude3_lt_0_01"].sum()
        ),
        "by_base_len": by_base,
        "top_tickers_lt_0_01": top_tickers,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
