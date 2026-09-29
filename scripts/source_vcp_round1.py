#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

# These source helpers use this range only for loading/data-quality inventory.
# VCP effects below are hard-gated to E1 and never consume post-E1 observations.
os.environ.setdefault("SIGNAL_START", "2016-01-04")
os.environ.setdefault("SIGNAL_END", "2026-06-30")

from astraquant.data.market_coordinates import SignalPriceSemantics
from astraquant.data.source_adapter import SourceDataAdapter
from astraquant.execution.assumptions import FixedBpsSlippage, SideAwareBpsFeeModel
from astraquant.execution.fills import ExecutionFillFactory
from astraquant.execution.market_data import ExecutionMarketData
from astraquant.execution.service import SignalDeclaration
from astraquant.portfolio.policy import PortfolioPolicyConfig
from astraquant.research.config_io import (
    load_exit_config,
    load_parameter_sweep_config,
    load_signal_config,
)
from astraquant.research.contact_registry import ContactRecord, append_contact_record
from astraquant.research.epoch_governance import resolve_historical_effect_period
from astraquant.research.exit_engine import ExitCompiler
from astraquant.research.parameter_sweep import ResearchParameterSweepRunner
from astraquant.research.signal_engine import SignalContext
from astraquant.research.technical_components import vcp_three_segment_details
from astraquant.research.universe_engine import UniverseContext
from astraquant.research.vcp_round1 import (
    VCPRound1ExecutionSettings,
    VCPRound1TradeRunner,
    build_adjusted_exit_features,
    build_common_session_panel,
    compile_round1_exit_settings,
)
from astraquant.research.vcp_round1_reporting import (
    NULL_CALIBRATION_TEXT,
    make_charts,
    normalized_frame_hash,
    overlap_table,
    summary_row,
    write_report,
)

from source_config_sweep import (
    EXPECTED_ELIGIBLE_TICKERS,
    EXPECTED_EXCLUSIONS_SHA256,
    _load_exclusions,
    _research_panel,
)
from source_eligible_universe_ca_coverage import eligible_turnover_universe
from source_strategy_integration_smoke import build_supported_ca


ROOT = Path(".").resolve()
SOURCE_ROOT = Path(
    os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")
).resolve()
SOURCE_REVISION = os.environ.get("SOURCE_REVISION", "source-checkout").strip()
SWEEP_PATH = Path(
    os.environ.get(
        "SWEEP_PATH",
        "configs/research/vcp_round1_three_segment_v1.yaml",
    )
)
OUT_DIR = Path(os.environ.get("OUT_DIR", "out"))
REPORT_PATH = Path(
    os.environ.get(
        "REPORT_PATH",
        "docs/VCP_ROUND1_THREE_SEGMENT_V1.md",
    )
)
CONTACT_REGISTRY_PATH = Path(
    os.environ.get("CONTACT_REGISTRY_PATH", "docs/CONTACT_REGISTRY.md")
)

PERIOD = resolve_historical_effect_period("E1")
assert PERIOD.end is not None
E1_START = pd.Timestamp(PERIOD.start)
E1_END = pd.Timestamp(PERIOD.end)

SUMMARY_PATH = OUT_DIR / "vcp_sweep_round1.csv"
TRADES_PATH = OUT_DIR / "vcp_sweep_round1_trades.csv"
OPEN_PATH = OUT_DIR / "vcp_sweep_round1_open_positions.csv"
OVERLAP_PATH = OUT_DIR / "vcp_sweep_overlap.csv"
PILOT_PATH = OUT_DIR / "vcp_sweep_round1_pilot.csv"
DIAG_PATH = OUT_DIR / "vcp_sweep_round1_signal_diagnostics.csv"
MANIFEST_PATH = OUT_DIR / "vcp_sweep_round1_manifest.json"

AXES = {
    "trigger.base_len": [25, 35, 50, 65],
    "trigger.last_contraction": [0.08, 0.12, 0.15],
    "trigger.dry_up": [0.50, 0.65, 0.80],
    "trigger.breakout_vol": [1.5, 2.0, 2.5],
}
AXIS_COLUMNS = {
    "trigger.base_len": "base_len",
    "trigger.last_contraction": "last_contraction",
    "trigger.dry_up": "dry_up",
    "trigger.breakout_vol": "breakout_vol",
}
PILOT_CONFIG_COUNT = 2
CONSISTENCY_SAMPLE_COUNT = 3


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _code_revision() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        text=True,
    ).strip()


def _validate_sweep_contract(sweep) -> dict[str, object]:
    if sweep.name != "vcp_round1_three_segment_v1":
        raise SystemExit("BLOCKED: unexpected sweep name")
    if sweep.combination_count != 108 or sweep.max_combinations != 108:
        raise SystemExit(
            "BLOCKED: VCP round1 must declare exactly 108 cells"
        )
    actual_axes = {
        axis.target: list(axis.values)
        for axis in sweep.axes
    }
    if actual_axes != AXES:
        raise SystemExit(
            "BLOCKED: VCP round1 axes changed from owner-frozen grid"
        )
    if sweep.constraints:
        raise SystemExit(
            "BLOCKED: VCP round1 must not skip cells by constraints"
        )

    fixed = dict(sweep.fixed_settings)
    expected = {
        "epoch": "E1",
        "entry_timing": "NEXT_COMMON_OPEN",
        "entry_chase_multiple": 1.05,
        "normalized_initial_notional": 1.0,
        "reentry_cooldown_sessions": 0,
        "one_open_trade_per_config_ticker": True,
        "cross_stock_capital_competition": False,
        "buy_fee_bps": 14.25,
        "sell_fee_bps_including_tax": 44.25,
        "adverse_slippage_bps_each_side": 10.0,
        "settlement_lag_sessions": 2,
        "low_n_closed_trades": 100,
        "high_score_fraction": 0.25,
        "overlap_top_trades": 20,
        "overlap_warning_threshold": 0.60,
        "remove_top_profit_counts": [1, 3, 5],
        "adjustment_method": (
            "ADJUSTED_RESEARCH_INDICATORS_RAW_EXECUTION_CA_ACCOUNTING"
        ),
        "pilot_config_count": PILOT_CONFIG_COUNT,
        "batch_consistency_sample_count": CONSISTENCY_SAMPLE_COUNT,
    }
    for key, value in expected.items():
        if fixed.get(key) != value:
            raise SystemExit(
                f"BLOCKED: fixed setting changed: {key} "
                f"expected={value!r} got={fixed.get(key)!r}"
            )
    return fixed


def _candidate_frame(
    *,
    common_panel: pd.DataFrame,
    prepared,
    cache,
    signal_context: SignalContext,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    expected_keys = common_panel[["date", "stock_id"]].rename(
        columns={"date": "signal_date"}
    ).reset_index(drop=True)
    got_keys = prepared.signal_frame[
        ["signal_date", "stock_id"]
    ].reset_index(drop=True)
    if not expected_keys.equals(got_keys):
        raise RuntimeError(
            "prepared signal frame/common panel key order mismatch"
        )

    details = vcp_three_segment_details(
        panel=common_panel,
        spec=prepared.signal_config.trigger,
        cache=cache,
        context=signal_context,
    ).reset_index(drop=True)
    signal = prepared.signal_frame.reset_index(drop=True)
    selected = (
        signal["counts_as_candidate"].fillna(False).astype(bool)
        & signal["signal_date"].between(
            E1_START,
            E1_END,
            inclusive="both",
        )
    )
    rows = pd.DataFrame(
        {
            "signal_date": signal.loc[
                selected, "signal_date"
            ].to_numpy(),
            "stock_id": signal.loc[
                selected, "stock_id"
            ].astype(str).to_numpy(),
            "pivot_adjusted": details.loc[
                selected, "pivot_adjusted"
            ].to_numpy(),
            "adjusted_signal_close": pd.to_numeric(
                common_panel.loc[selected, "close"],
                errors="coerce",
            ).to_numpy(),
        }
    )
    if rows[
        ["pivot_adjusted", "adjusted_signal_close"]
    ].isna().any(axis=1).any():
        raise RuntimeError(
            "selected VCP signal is missing pivot/adjusted close"
        )

    in_universe = (
        signal["universe_counts"].fillna(False).astype(bool)
        & signal["signal_date"].between(
            E1_START,
            E1_END,
            inclusive="both",
        )
    )
    reasons = (
        details.loc[in_universe, "diagnostic_reason"]
        .value_counts(dropna=False)
        .rename_axis("reason")
        .reset_index(name="count")
    )
    reasons["stage"] = "SIGNAL_EVALUATION"
    return rows, reasons


def _record_contact(result_id: str, context: str) -> None:
    append_contact_record(
        CONTACT_REGISTRY_PATH,
        ContactRecord(
            result_id=result_id,
            covered_period=f"{E1_START.date()} ~ {E1_END.date()}",
            contact_date=datetime.now(
                ZoneInfo("Asia/Taipei")
            ).date(),
            context=context,
        ),
    )


def _output_columns() -> tuple[list[str], list[str]]:
    trade_cols = [
        "config_id",
        "trade_id",
        "stock_id",
        "signal_date",
        "entry_date",
        "entry_price",
        "exit_date",
        "exit_price",
        "exit_reason",
        "entry_investment",
        "buy_fee",
        "sell_fee_and_tax",
        "buy_slippage_cost",
        "sell_slippage_cost",
        "total_cost",
        "ca_entitlement",
        "net_return",
        "holding_days",
        "holding_sessions",
        "blocked_exit_attempts",
        "terminal_unverified",
        "adjustment_method",
        "base_len",
        "last_contraction",
        "dry_up",
        "breakout_vol",
    ]
    open_cols = [
        "config_id",
        "trade_id",
        "stock_id",
        "signal_date",
        "entry_date",
        "entry_price",
        "held_days_at_period_end",
        "held_sessions_at_period_end",
        "pending_exit_state",
        "current_tickers",
        "ca_entitlement",
        "terminal_unverified",
        "blocked_exit_attempts",
        "adjustment_method",
        "base_len",
        "last_contraction",
        "dry_up",
        "breakout_vol",
    ]
    return trade_cols, open_cols


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sweep = load_parameter_sweep_config(SWEEP_PATH)
    fixed = _validate_sweep_contract(sweep)

    signal_path = Path(sweep.signal)
    exit_path = Path(sweep.exit)
    signal_config = load_signal_config(signal_path)
    signal_params = dict(signal_config.trigger.params)
    expected_signal_fixed = {
        "contraction_ratio": 0.75,
        "dry_up_window": 5,
        "breakout_volume_lookback": 50,
        "liquidity_lookback": 20,
        "min_prior_avg_amount_twd": 20_000_000,
        "entry_chase_multiple": 1.05,
    }
    for key, value in expected_signal_fixed.items():
        if signal_params.get(key) != value:
            raise SystemExit(
                f"BLOCKED: signal fixed setting changed: {key} "
                f"expected={value!r} got={signal_params.get(key)!r}"
            )
    config_hashes = {
        SWEEP_PATH.as_posix(): _sha256(SWEEP_PATH),
        signal_path.as_posix(): _sha256(signal_path),
        exit_path.as_posix(): _sha256(exit_path),
    }
    code_revision = _code_revision()

    excluded = _load_exclusions()
    panel, adjusted, tradability = _research_panel()

    # This is a data-quality/inventory gate, not an E2 effect query.
    eligible = eligible_turnover_universe(
        adjusted,
        tradability,
    )
    eligible_count = int(
        eligible["stock_id"].astype(str).nunique()
    )
    if eligible_count != EXPECTED_ELIGIBLE_TICKERS:
        raise SystemExit(
            "BLOCKED: frozen eligibility-union count changed: "
            f"expected={EXPECTED_ELIGIBLE_TICKERS} "
            f"got={eligible_count}"
        )

    e1_observed = pd.to_datetime(
        panel["date"], errors="coerce"
    ).le(E1_END)
    numeric_scope = set(
        panel.loc[
            e1_observed
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

    sessions = [
        pd.Timestamp(x)
        for x in common_panel["date"]
        .dropna()
        .drop_duplicates()
        .sort_values()
        .tolist()
        if E1_START <= pd.Timestamp(x) <= E1_END
    ]
    if not sessions:
        raise SystemExit(
            "BLOCKED: no E1 common trading sessions"
        )
    if max(sessions) > E1_END:
        raise SystemExit(
            "BLOCKED: E1 simulator calendar crossed boundary"
        )

    ca_scope = set(research_ticker_scope)
    (
        ca_instructions,
        unsupported_ca,
        unsupported_summary,
    ) = build_supported_ca(
        candidate_tickers=ca_scope,
        sessions=set(sessions),
    )
    if unsupported_ca:
        raise SystemExit(
            "BLOCKED: unsupported CA rows remain on research scope: "
            + json.dumps(
                unsupported_summary,
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    terminal_unverified_count = len(
        {
            str(item.event.ticker)
            for item in ca_instructions
            if item.component
            == "UNVERIFIED_TERMINAL_CASHOUT"
        }
    )

    exit_plan = ExitCompiler().compile(
        load_exit_config(exit_path)
    )
    exit_settings = compile_round1_exit_settings(
        exit_plan
    )
    if (
        exit_settings.atr_period != 21
        or not math.isclose(exit_settings.atr_multiplier, 2.5)
        or exit_settings.ma_window != 21
    ):
        raise SystemExit("BLOCKED: fixed VCP round1 exit settings changed")
    adjusted_exit_features = (
        build_adjusted_exit_features(
            common_panel,
            atr_period=exit_settings.atr_period,
            ma_window=exit_settings.ma_window,
            end=E1_END,
        )
    )

    market_data = ExecutionMarketData(
        SourceDataAdapter(SOURCE_ROOT),
        ticker_scope=ca_scope,
    )
    fill_factory = ExecutionFillFactory(
        fee_model=SideAwareBpsFeeModel(
            buy_bps=float(fixed["buy_fee_bps"]),
            sell_bps=float(
                fixed["sell_fee_bps_including_tax"]
            ),
        ),
        slippage_model=FixedBpsSlippage(
            bps=float(
                fixed["adverse_slippage_bps_each_side"]
            )
        ),
    )
    trade_runner = VCPRound1TradeRunner(
        market_data=market_data,
        fill_factory=fill_factory,
        signal=SignalDeclaration(
            source="CONFIG:vcp_round1_three_segment_v1",
            price_semantics=(
                SignalPriceSemantics.SCALE_SENSITIVE
            ),
        ),
        sessions=sessions,
        adjusted_exit_features=adjusted_exit_features,
        corporate_actions=ca_instructions,
        exit_settings=exit_settings,
        execution_settings=VCPRound1ExecutionSettings(
            chase_multiple=float(
                fixed["entry_chase_multiple"]
            ),
            normalized_initial_notional=float(
                fixed["normalized_initial_notional"]
            ),
            settlement_lag_sessions=int(
                fixed["settlement_lag_sessions"]
            ),
            adjustment_method=str(
                fixed["adjustment_method"]
            ),
        ),
    )

    signal_context = SignalContext(
        source_revision=SOURCE_REVISION
    )
    sweep_runner = ResearchParameterSweepRunner()
    stream = sweep_runner.stream_sweep(
        sweep_config_path=SWEEP_PATH,
        root=ROOT,
        panel=common_panel,
        universe_context=UniverseContext(
            p2_060_excluded_tickers=frozenset(
                excluded
            ),
            p2_060_exclusion_sha256=(
                EXPECTED_EXCLUSIONS_SHA256
            ),
            theme_root=None,
        ),
        signal_context=signal_context,
        base_policy=PortfolioPolicyConfig(
            position_fraction=1.0,
            max_positions=1,
            stop_fraction=None,
            reentry_gap_sessions=0,
            max_hold_sessions=None,
            lot_size=1,
            random_seed=0,
        ),
    )
    if (
        stream.declared_combinations != 108
        or stream.skipped_by_constraints != 0
    ):
        raise SystemExit(
            "BLOCKED: full sweep grid is not "
            "exactly 108 unskipped cells"
        )

    prepared_runs = []
    reason_frames: list[pd.DataFrame] = []
    for index, item in enumerate(
        stream.runs,
        start=1,
    ):
        config_id = f"VCP-R1-{index:03d}"
        candidates, reasons = _candidate_frame(
            common_panel=common_panel,
            prepared=item.prepared,
            cache=sweep_runner.engine.feature_cache,
            signal_context=signal_context,
        )
        reasons.insert(0, "config_id", config_id)
        reason_frames.append(reasons)
        prepared_runs.append(
            (
                config_id,
                dict(item.parameters),
                candidates,
            )
        )
    if len(prepared_runs) != 108:
        raise SystemExit(
            "BLOCKED: prepared grid is not 108"
        )

    pilot_started = time.perf_counter()
    pilot_rows = []
    pilot_simulations = {}
    for config_id, params, candidates in (
        prepared_runs[:PILOT_CONFIG_COUNT]
    ):
        simulation = trade_runner.simulate_config(
            config_id=config_id,
            candidates=candidates,
        )
        pilot_simulations[config_id] = simulation
        pilot_rows.append(
            summary_row(
                config_id=config_id,
                params=params,
                simulation=simulation,
                low_n_threshold=int(
                    fixed["low_n_closed_trades"]
                ),
            )
        )
    pilot_seconds = (
        time.perf_counter() - pilot_started
    )
    pd.DataFrame(pilot_rows).to_csv(
        PILOT_PATH,
        index=False,
    )
    _record_contact(
        "VCP_ROUND1_THREE_SEGMENT_V1_PILOT",
        (
            "E1 two-config pilot effect contact; "
            f"source_revision={SOURCE_REVISION}; "
            f"config_hash={config_hashes[SWEEP_PATH.as_posix()]}; "
            f"code_commit={code_revision}; "
            "definitions frozen before pilot"
        ),
    )

    full_started = time.perf_counter()
    summary_rows: list[dict[str, object]] = []
    trade_frames: list[pd.DataFrame] = []
    open_frames: list[pd.DataFrame] = []
    simulation_hashes = {}
    unfilled_reason_rows = []

    for config_id, params, candidates in prepared_runs:
        simulation = (
            pilot_simulations[config_id]
            if config_id in pilot_simulations
            else trade_runner.simulate_config(
                config_id=config_id,
                candidates=candidates,
            )
        )
        summary_rows.append(
            summary_row(
                config_id=config_id,
                params=params,
                simulation=simulation,
                low_n_threshold=int(
                    fixed["low_n_closed_trades"]
                ),
            )
        )
        if not simulation.trades.empty:
            frame = simulation.trades.copy()
            for key, column in AXIS_COLUMNS.items():
                frame[column] = params[key]
            trade_frames.append(frame)
        if not simulation.open_positions.empty:
            frame = simulation.open_positions.copy()
            for key, column in AXIS_COLUMNS.items():
                frame[column] = params[key]
            open_frames.append(frame)

        simulation_hashes[config_id] = (
            normalized_frame_hash(
                simulation.trades
            ),
            normalized_frame_hash(
                simulation.open_positions
            ),
        )
        for reason, count in (
            simulation.unfilled_reason_counts.items()
        ):
            unfilled_reason_rows.append(
                {
                    "config_id": config_id,
                    "stage": "ENTRY_UNFILLED",
                    "reason": reason,
                    "count": int(count),
                }
            )
    full_seconds = (
        time.perf_counter() - full_started
    )

    results = pd.DataFrame(summary_rows)
    if (
        len(results) != 108
        or results["config_id"].nunique() != 108
    ):
        raise RuntimeError(
            "full summary did not retain all 108 cells"
        )

    trade_cols, open_cols = _output_columns()
    trades = (
        pd.concat(
            trade_frames,
            ignore_index=True,
        )
        if trade_frames
        else pd.DataFrame(columns=trade_cols)
    )
    opens = (
        pd.concat(
            open_frames,
            ignore_index=True,
        )
        if open_frames
        else pd.DataFrame(columns=open_cols)
    )
    trades = trades.reindex(columns=trade_cols)
    opens = opens.reindex(columns=open_cols)

    sample_indices = sorted(
        set(
            np.linspace(
                0,
                len(prepared_runs) - 1,
                num=CONSISTENCY_SAMPLE_COUNT,
                dtype=int,
            ).tolist()
        )
    )
    consistency = []
    for index in sample_indices:
        config_id, params, candidates = (
            prepared_runs[index]
        )
        rerun = trade_runner.simulate_config(
            config_id=config_id,
            candidates=candidates,
        )
        got = (
            normalized_frame_hash(rerun.trades),
            normalized_frame_hash(
                rerun.open_positions
            ),
        )
        match = got == simulation_hashes[config_id]
        consistency.append(
            {
                "config_id": config_id,
                "match": match,
            }
        )
        if not match:
            raise RuntimeError(
                "batch/per-config consistency failed "
                f"for {config_id}"
            )

    results.to_csv(SUMMARY_PATH, index=False)
    trades.to_csv(TRADES_PATH, index=False)
    opens.to_csv(OPEN_PATH, index=False)

    diagnostics = pd.concat(
        reason_frames,
        ignore_index=True,
    )
    if unfilled_reason_rows:
        diagnostics = pd.concat(
            [
                diagnostics,
                pd.DataFrame(
                    unfilled_reason_rows
                ),
            ],
            ignore_index=True,
            sort=False,
        )
    diagnostics.to_csv(
        DIAG_PATH,
        index=False,
    )

    overlap, high_score_count, warning_count = (
        overlap_table(
            results=results,
            trades=trades,
            high_score_fraction=float(
                fixed["high_score_fraction"]
            ),
            overlap_top_trades=int(
                fixed["overlap_top_trades"]
            ),
            overlap_warning_threshold=float(
                fixed["overlap_warning_threshold"]
            ),
        )
    )
    overlap.to_csv(
        OVERLAP_PATH,
        index=False,
    )

    axis_values = {
        "base_len": AXES["trigger.base_len"],
        "last_contraction": (
            AXES["trigger.last_contraction"]
        ),
        "dry_up": AXES["trigger.dry_up"],
        "breakout_vol": (
            AXES["trigger.breakout_vol"]
        ),
    }
    chart_paths = make_charts(
        results,
        out_dir=OUT_DIR,
        cost_text=(
            "buy fee 0.1425%; sell fee 0.1425% "
            "+ tax 0.3%; slippage 0.1% each side"
        ),
        axis_values=axis_values,
    )
    terminal_affected_count = int(
        results[
            "unverified_terminal_trade_count"
        ].sum()
    )

    manifest = {
        "strategy_version": (
            "vcp_round1_three_segment_v1"
        ),
        "epoch": "E1",
        "period": [
            str(E1_START.date()),
            str(E1_END.date()),
        ],
        "source_revision": SOURCE_REVISION,
        "code_commit": code_revision,
        "config_hashes": config_hashes,
        "p2_060_exclusion_sha": (
            EXPECTED_EXCLUSIONS_SHA256
        ),
        "eligibility_union_distinct_tickers": (
            eligible_count
        ),
        "p2_excluded_distinct_tickers": len(
            excluded
        ),
        "research_numeric_scope_after_p2": len(
            research_ticker_scope
        ),
        "declared_combinations": 108,
        "evaluated_combinations": len(results),
        "fixed_settings": fixed,
        "execution_assumptions_id": (
            sweep.execution_assumptions_id
        ),
        "pilot": {
            "config_ids": [
                item[0]
                for item in prepared_runs[
                    :PILOT_CONFIG_COUNT
                ]
            ],
            "runtime_seconds": pilot_seconds,
            "artifact": PILOT_PATH.as_posix(),
        },
        "full_runtime_seconds": full_seconds,
        "batch_consistency": consistency,
        "feature_cache": {
            "hits": (
                sweep_runner.engine
                .feature_cache.hits
            ),
            "misses": (
                sweep_runner.engine
                .feature_cache.misses
            ),
        },
        "terminal_unverified_tickers": (
            terminal_unverified_count
        ),
        "terminal_affected_trade_records": (
            terminal_affected_count
        ),
        "null_calibration": {
            "status": (
                "NOT_REUSABLE_UNDER_EXISTING_"
                "FROZEN_CONTRACT"
            ),
            "statement": NULL_CALIBRATION_TEXT,
        },
        "artifacts": [
            SUMMARY_PATH.as_posix(),
            TRADES_PATH.as_posix(),
            OPEN_PATH.as_posix(),
            OVERLAP_PATH.as_posix(),
            PILOT_PATH.as_posix(),
            DIAG_PATH.as_posix(),
            *chart_paths,
            REPORT_PATH.as_posix(),
        ],
    }
    MANIFEST_PATH.write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    liquidity_threshold = float(
        signal_params["min_prior_avg_amount_twd"]
    )
    write_report(
        report_path=REPORT_PATH,
        summary_path=SUMMARY_PATH,
        trades_path=TRADES_PATH,
        open_path=OPEN_PATH,
        overlap_path=OVERLAP_PATH,
        pilot_path=PILOT_PATH,
        diagnostics_path=DIAG_PATH,
        manifest_path=MANIFEST_PATH,
        results=results,
        source_revision=SOURCE_REVISION,
        code_revision=code_revision,
        config_hashes=config_hashes,
        p2_sha=EXPECTED_EXCLUSIONS_SHA256,
        eligible_count=eligible_count,
        p2_excluded_count=len(excluded),
        liquidity_threshold=liquidity_threshold,
        terminal_unverified_count=(
            terminal_unverified_count
        ),
        terminal_affected_count=(
            terminal_affected_count
        ),
        high_score_count=high_score_count,
        warning_count=warning_count,
        pilot_count=PILOT_CONFIG_COUNT,
        pilot_seconds=pilot_seconds,
        full_seconds=full_seconds,
        cache_hits=(
            sweep_runner.engine.feature_cache.hits
        ),
        cache_misses=(
            sweep_runner.engine.feature_cache.misses
        ),
        chart_paths=chart_paths,
        low_n_threshold=int(
            fixed["low_n_closed_trades"]
        ),
    )
    _record_contact(
        "VCP_ROUND1_THREE_SEGMENT_V1_FULL",
        (
            "E1 full-trade 108-cell effect report; "
            f"source_revision={SOURCE_REVISION}; "
            f"config_hash={config_hashes[SWEEP_PATH.as_posix()]}; "
            f"code_commit={code_revision}; "
            "costed independent-trade canonical execution"
        ),
    )


if __name__ == "__main__":
    main()
