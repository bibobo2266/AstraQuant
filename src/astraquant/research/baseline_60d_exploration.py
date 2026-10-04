from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Iterable
import hashlib
import json
import math

import numpy as np
import pandas as pd
import yaml

from astraquant.data.market_coordinates import SignalPriceSemantics
from astraquant.data.source_adapter import SourceDataAdapter
from astraquant.execution.assumptions import FixedBpsSlippage, SideAwareBpsFeeModel
from astraquant.execution.fills import ExecutionFillFactory
from astraquant.execution.market_data import ExecutionMarketData
from astraquant.execution.service import CanonicalExecutionService, SignalDeclaration
from astraquant.portfolio.engine import PortfolioEngine
from astraquant.portfolio.performance_reporting import TradeReport, build_trade_report, portfolio_fills
from astraquant.portfolio.policy import (
    CapacitySelectionRule,
    PortfolioIntentPolicy,
    PortfolioPolicyConfig,
)
from astraquant.portfolio.strategy_simulator import CanonicalStrategySimulator, StrategySimulationConfig
from astraquant.research.baseline_60d_simulation import (
    BaselineSimulationContext,
    BaselineSimulationMode,
)
from astraquant.research.config_engine import PreparedResearchRun, ResearchConfigEngine
from astraquant.research.feature_panel_integration import (
    EligibilityEvidenceScope,
    FeaturePanelIntegrator,
)
from astraquant.research.feature_panel_integration import (
    load_feature_panel_integration_config,
    sha256_file,
)
from astraquant.research.prepared_run_evidence import build_prepared_run_eligibility_evidence
from astraquant.research.signal_engine import SignalContext
from astraquant.research.universe_engine import UniverseContext


class BaselineExplorationError(RuntimeError):
    pass


class RowEligibilityStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    EXCLUDED = "EXCLUDED"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"


class InputScope(str, Enum):
    SYNTHETIC_FIXTURE = "SYNTHETIC_FIXTURE"
    SOURCE_EVIDENCE = "SOURCE_EVIDENCE"


FROZEN_METHOD = {
    "schema_version": "1",
    "name": "baseline_60d_breakout_v1_exploration",
    "strategy_version": "baseline_60d_breakout_v1",
    "run_config": "configs/research/baseline_60d_breakout_v1/run.yaml",
    "epoch": "E1",
    "period": {"start": "2016-01-04", "end": "2021-12-31"},
    "entry": {
        "trigger": "N_SESSION_HIGH",
        "lookback": 60,
        "first_cross_strict": True,
        "close_to_ma120_min": 0.0,
        "prior20_amount_twd_min": 20_000_000,
        "execution": "NEXT_CANONICAL_RAW_OPEN",
    },
    "exit": {
        "atr_period": 14,
        "atr_smoothing": "SMA",
        "atr_multiplier": 3.0,
        "atr_trigger": "CLOSE_LE_THRESHOLD",
        "low_window": 20,
        "low_exclude_current": True,
        "low_trigger": "CLOSE_STRICT_LT",
        "execution": "NEXT_LEGAL_CANONICAL_RAW_OPEN",
    },
    "costs": {
        "buy_fee_bps": 14.25,
        "sell_fee_bps_including_tax": 44.25,
        "adverse_slippage_bps_each_side": 10.0,
        "settlement_lag_sessions": 2,
    },
    "method_contract": {
        "one_open_trade_per_ticker": True,
        "cross_stock_capital_competition": False,
        "force_close_at_period_end": False,
        "mfe_mae_role": "DIAGNOSTIC_ONLY",
        "profit_concentration_remove_top": [1, 3, 5],
    },
    "unfrozen_for_real_e1": [
        "candidate_cohort_opening_cash_twd",
        "candidate_cohort_position_fraction",
        "capital_constrained_opening_cash_twd",
        "capital_constrained_position_fraction",
        "capital_constrained_max_positions",
        "capital_constrained_capacity_selection_rule",
    ],
    "formal_research_status": "BLOCKED",
}


@dataclass(frozen=True)
class EligibilityManifest:
    schema_version: str
    scope: InputScope
    source_revision: str
    epoch: str
    period_start: str
    period_end: str
    row_count: int
    table_sha256: str


@dataclass(frozen=True)
class EligibilityTable:
    frame: pd.DataFrame
    manifest: EligibilityManifest
    counts_by_status: dict[str, int]
    counts_by_reason: dict[str, int]


@dataclass(frozen=True)
class SourceFileEvidence:
    path: str
    sha256: str


@dataclass(frozen=True)
class SourceManifest:
    schema_version: str
    scope: InputScope
    source_revision: str
    period_start: str
    period_end: str
    files: tuple[SourceFileEvidence, ...]


@dataclass(frozen=True)
class SyntheticPolicySettings:
    opening_cash_twd: float
    position_fraction: float
    max_positions: int
    capacity_selection_rule: CapacitySelectionRule


@dataclass(frozen=True)
class ExplorationRunArtifacts:
    report: dict[str, object]
    candidate_trades: pd.DataFrame
    capital_trades: pd.DataFrame
    open_positions: pd.DataFrame
    eligibility_rows: pd.DataFrame
    candidate_funnel: pd.DataFrame
    mfe_mae: pd.DataFrame


def _canonical_yaml(path: Path) -> dict[str, object]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise BaselineExplorationError(f"config must be mapping: {path}")
    return value


def load_frozen_method_config(path: str | Path) -> dict[str, object]:
    path = Path(path)
    value = _canonical_yaml(path)
    if value != FROZEN_METHOD:
        raise BaselineExplorationError(
            "baseline exploration method config differs from frozen contract"
        )
    return value


def _parse_scope(value: object) -> InputScope:
    if isinstance(value, InputScope):
        return value
    if not isinstance(value, str) or not value.strip():
        raise BaselineExplorationError("input scope must be a recognized string")
    try:
        return InputScope(value.strip().upper())
    except ValueError as exc:
        raise BaselineExplorationError(f"unknown input scope: {value!r}") from exc


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise BaselineExplorationError(f"JSON root must be object: {path}")
    return value


def load_eligibility_table(
    *,
    table_path: str | Path,
    manifest_path: str | Path,
) -> EligibilityTable:
    table_path = Path(table_path).resolve()
    manifest_path = Path(manifest_path).resolve()
    manifest_raw = _read_json(manifest_path)
    expected_keys = {
        "schema_version",
        "scope",
        "source_revision",
        "epoch",
        "period_start",
        "period_end",
        "row_count",
        "table_sha256",
    }
    if set(manifest_raw) != expected_keys:
        raise BaselineExplorationError(
            "eligibility manifest keys do not match schema v1"
        )
    manifest = EligibilityManifest(
        schema_version=str(manifest_raw["schema_version"]),
        scope=_parse_scope(manifest_raw["scope"]),
        source_revision=str(manifest_raw["source_revision"]),
        epoch=str(manifest_raw["epoch"]),
        period_start=str(manifest_raw["period_start"]),
        period_end=str(manifest_raw["period_end"]),
        row_count=int(manifest_raw["row_count"]),
        table_sha256=str(manifest_raw["table_sha256"]),
    )
    if manifest.schema_version != "1":
        raise BaselineExplorationError("unsupported eligibility manifest schema")
    if not table_path.exists():
        raise BaselineExplorationError(f"eligibility table missing: {table_path}")
    if sha256_file(table_path) != manifest.table_sha256:
        raise BaselineExplorationError("eligibility table checksum mismatch")

    frame = pd.read_csv(table_path, dtype={"stock_id": str})
    required = {
        "date",
        "stock_id",
        "eligibility_status",
        "reason_code",
        "reason_detail",
    }
    missing = required - set(frame.columns)
    if missing:
        raise BaselineExplorationError(
            f"eligibility table missing columns: {sorted(missing)}"
        )
    frame = frame[list(required)].copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    frame["stock_id"] = frame["stock_id"].astype(str)
    if frame[["date", "stock_id"]].isna().any(axis=1).any():
        raise BaselineExplorationError("eligibility table has null logical keys")
    if frame.duplicated(["date", "stock_id"]).any():
        raise BaselineExplorationError("eligibility table has duplicate logical keys")
    if len(frame) != manifest.row_count:
        raise BaselineExplorationError(
            "eligibility row_count does not match manifest"
        )
    if manifest.row_count <= 0:
        raise BaselineExplorationError("eligibility table must not be empty")

    normalized_status: list[str] = []
    for raw in frame["eligibility_status"]:
        if not isinstance(raw, str) or not raw.strip():
            raise BaselineExplorationError("eligibility_status must be non-empty")
        try:
            normalized_status.append(RowEligibilityStatus(raw.strip().upper()).value)
        except ValueError as exc:
            raise BaselineExplorationError(
                f"unknown eligibility_status: {raw!r}"
            ) from exc
    frame["eligibility_status"] = normalized_status
    frame["reason_code"] = frame["reason_code"].astype("string")
    frame["reason_detail"] = frame["reason_detail"].astype("string")
    if frame["reason_code"].isna().any() or frame["reason_code"].str.strip().eq("").any():
        raise BaselineExplorationError("reason_code must be explicit for every row")

    start = pd.Timestamp(manifest.period_start)
    end = pd.Timestamp(manifest.period_end)
    if start > end:
        raise BaselineExplorationError("eligibility manifest period is reversed")
    if frame["date"].lt(start).any() or frame["date"].gt(end).any():
        raise BaselineExplorationError(
            "eligibility rows exceed manifest period"
        )

    counts_by_status = {
        str(k): int(v)
        for k, v in frame["eligibility_status"].value_counts(dropna=False).items()
    }
    counts_by_reason = {
        str(k): int(v)
        for k, v in frame["reason_code"].value_counts(dropna=False).items()
    }
    return EligibilityTable(
        frame=frame.sort_values(["date", "stock_id"], kind="stable").reset_index(drop=True),
        manifest=manifest,
        counts_by_status=counts_by_status,
        counts_by_reason=counts_by_reason,
    )


def load_source_manifest(
    *,
    source_root: str | Path,
    manifest_path: str | Path,
) -> SourceManifest:
    source_root = Path(source_root).resolve()
    raw = _read_json(Path(manifest_path))
    required = {
        "schema_version",
        "scope",
        "source_revision",
        "period_start",
        "period_end",
        "files",
    }
    if set(raw) != required:
        raise BaselineExplorationError("source manifest keys do not match schema v1")
    files_raw = raw["files"]
    if not isinstance(files_raw, list) or not files_raw:
        raise BaselineExplorationError("source manifest files must be non-empty")
    files: list[SourceFileEvidence] = []
    for item in files_raw:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise BaselineExplorationError("invalid source manifest file entry")
        rel = str(item["path"])
        path = (source_root / rel).resolve()
        try:
            path.relative_to(source_root)
        except ValueError as exc:
            raise BaselineExplorationError("source manifest path escapes root") from exc
        if not path.exists():
            raise BaselineExplorationError(f"source file missing: {rel}")
        expected = str(item["sha256"])
        if sha256_file(path) != expected:
            raise BaselineExplorationError(
                f"source file checksum mismatch: {rel}"
            )
        files.append(SourceFileEvidence(path=rel, sha256=expected))
    if str(raw["schema_version"]) != "1":
        raise BaselineExplorationError("unsupported source manifest schema")
    period_start = pd.Timestamp(str(raw["period_start"]))
    period_end = pd.Timestamp(str(raw["period_end"]))
    if period_start > period_end:
        raise BaselineExplorationError("source manifest period is reversed")
    return SourceManifest(
        schema_version=str(raw["schema_version"]),
        scope=_parse_scope(raw["scope"]),
        source_revision=str(raw["source_revision"]),
        period_start=str(raw["period_start"]),
        period_end=str(raw["period_end"]),
        files=tuple(files),
    )


def qualify_candidates(
    candidates: pd.DataFrame,
    eligibility: EligibilityTable,
) -> pd.DataFrame:
    rows = candidates.copy()
    if rows.empty:
        for column in ("eligibility_status", "reason_code", "reason_detail"):
            rows[column] = pd.Series(dtype="object")
        return rows
    rows["signal_date"] = pd.to_datetime(
        rows["signal_date"], errors="coerce"
    ).dt.normalize()
    rows["stock_id"] = rows["stock_id"].astype(str)
    lookup = eligibility.frame.rename(columns={"date": "signal_date"})
    merged = rows.merge(
        lookup,
        on=["signal_date", "stock_id"],
        how="left",
        validate="many_to_one",
        indicator=True,
    )
    missing = merged["_merge"].eq("left_only")
    merged.loc[missing, "eligibility_status"] = RowEligibilityStatus.UNKNOWN.value
    merged.loc[missing, "reason_code"] = "MISSING_ELIGIBILITY_ROW"
    merged.loc[missing, "reason_detail"] = (
        "candidate has no row-level eligibility evidence"
    )
    return merged.drop(columns=["_merge"])


def _policy_from_fixture(raw: dict[str, object]) -> tuple[SyntheticPolicySettings, PortfolioPolicyConfig]:
    required = {
        "opening_cash_twd",
        "position_fraction",
        "max_positions",
        "capacity_selection_rule",
    }
    if set(raw) != required:
        raise BaselineExplorationError("synthetic policy keys do not match schema")
    settings = SyntheticPolicySettings(
        opening_cash_twd=float(raw["opening_cash_twd"]),
        position_fraction=float(raw["position_fraction"]),
        max_positions=int(raw["max_positions"]),
        capacity_selection_rule=CapacitySelectionRule(
            str(raw["capacity_selection_rule"]).upper()
        ),
    )
    if settings.opening_cash_twd <= 0:
        raise BaselineExplorationError("opening_cash_twd must be positive")
    policy = PortfolioPolicyConfig(
        position_fraction=settings.position_fraction,
        max_positions=settings.max_positions,
        stop_fraction=None,
        reentry_gap_sessions=0,
        max_hold_sessions=None,
        lot_size=1000,
        random_seed=0,
        capacity_selection_rule=settings.capacity_selection_rule,
    )
    return settings, policy


def _subset_prepared(
    *,
    prepared: PreparedResearchRun,
    candidates: pd.DataFrame,
    hydrated_panel: pd.DataFrame,
    execution_sessions: Iterable[date],
) -> PreparedResearchRun:
    evidence = prepared.eligibility_evidence
    if evidence is None:
        raise BaselineExplorationError("prepared run is missing eligibility evidence")
    rebound = build_prepared_run_eligibility_evidence(
        feature_evidence=evidence.feature_evidence,
        hydrated_panel=hydrated_panel,
        run_config=prepared.run_config,
        universe_config=prepared.universe_config,
        signal_config=prepared.signal_config,
        exit_config=prepared.exit_config,
        exit_plan=prepared.exit_plan,
        portfolio_policy=prepared.portfolio_policy,
        universe_mask=prepared.universe_mask,
        signal_frame=prepared.signal_frame,
        candidates=candidates,
        signal_source_revision=prepared.signal_source_revision,
        signal_availability_policy=prepared.signal_availability_policy,
        execution_sessions=execution_sessions,
    )
    return replace(
        prepared,
        candidates=candidates.reset_index(drop=True),
        eligibility_evidence=rebound,
    )


def _build_simulator(
    *,
    source_root: Path,
    prepared: PreparedResearchRun,
    opening_cash_twd: float,
    costs: dict[str, object],
) -> tuple[CanonicalStrategySimulator, PortfolioEngine]:
    portfolio = PortfolioEngine(opening_cash=float(opening_cash_twd))
    execution = CanonicalExecutionService(
        market_data=ExecutionMarketData(SourceDataAdapter(source_root)),
        fill_factory=ExecutionFillFactory(
            fee_model=SideAwareBpsFeeModel(
                buy_bps=float(costs["buy_fee_bps"]),
                sell_bps=float(costs["sell_fee_bps_including_tax"]),
            ),
            slippage_model=FixedBpsSlippage(
                bps=float(costs["adverse_slippage_bps_each_side"])
            ),
        ),
        portfolio=portfolio,
    )
    simulator = CanonicalStrategySimulator(
        execution=execution,
        portfolio=portfolio,
        policy=PortfolioIntentPolicy(prepared.portfolio_policy),
        signal=SignalDeclaration(
            source=f"CONFIG:{prepared.signal_config.name}",
            price_semantics=SignalPriceSemantics.SCALE_SENSITIVE,
        ),
        config=StrategySimulationConfig(
            settlement_lag_sessions=int(costs["settlement_lag_sessions"])
        ),
    )
    return simulator, portfolio


def _holding_sessions(
    *,
    entry_at,
    exit_at,
    sessions: tuple[date, ...],
) -> int:
    index = {day: i for i, day in enumerate(sessions)}
    entry_day = pd.Timestamp(entry_at).date()
    exit_day = pd.Timestamp(exit_at).date()
    if entry_day not in index or exit_day not in index:
        raise BaselineExplorationError(
            "trade timestamps fall outside execution sessions"
        )
    return int(index[exit_day] - index[entry_day])


def _trade_frame(
    *,
    trade_report: TradeReport,
    simulation,
    portfolio: PortfolioEngine,
    sessions: tuple[date, ...],
    run_label: str,
) -> pd.DataFrame:
    fills = {fill.fill_id: fill for fill in portfolio_fills(portfolio)}
    terminal_sources = {
        lot.source_fill_id
        for lot in trade_report.reconstruction.closed_lots
        if lot.exit_kind != "MARKET_FILL"
    }
    pending_by_ticker: dict[str, list] = {}
    state = simulation.baseline_exit_state
    if state is not None:
        for item in state.completed_exit_intents:
            pending_by_ticker.setdefault(str(item.ticker), []).append(item)
        for items in pending_by_ticker.values():
            items.sort(key=lambda x: (x.trigger_date, x.intent_id))

    rows: list[dict[str, object]] = []
    ticker_offsets: dict[str, int] = {}
    for trade in sorted(
        trade_report.closed_trades,
        key=lambda x: (x.exit_at, x.entry_ticker, x.source_fill_id),
    ):
        entry_fill = fills.get(trade.source_fill_id)
        if entry_fill is None:
            raise BaselineExplorationError(
                f"missing entry fill for closed trade: {trade.source_fill_id}"
            )
        if trade.source_fill_id in terminal_sources:
            exit_reason = "TERMINAL"
        else:
            ticker = str(trade.entry_ticker)
            offset = ticker_offsets.get(ticker, 0)
            intents = pending_by_ticker.get(ticker, [])
            exit_reason = (
                intents[offset].reason.value
                if offset < len(intents)
                else "UNKNOWN_STRATEGY_EXIT"
            )
            ticker_offsets[ticker] = offset + 1
        rows.append(
            {
                "run_label": run_label,
                "source_fill_id": trade.source_fill_id,
                "stock_id": str(trade.entry_ticker),
                "entry_at": pd.Timestamp(trade.entry_at).isoformat(),
                "exit_at": pd.Timestamp(trade.exit_at).isoformat(),
                "entry_fill_price": float(entry_fill.price),
                "entry_fees": float(entry_fill.fees),
                "realized_pnl": float(trade.realized_pnl),
                "entry_cost": float(trade.entry_cost),
                "net_return": float(trade.return_on_cost),
                "holding_days": float(trade.holding_days),
                "holding_sessions": _holding_sessions(
                    entry_at=trade.entry_at,
                    exit_at=trade.exit_at,
                    sessions=sessions,
                ),
                "exit_reason": exit_reason,
            }
        )
    return pd.DataFrame(rows)


def _open_frame(
    *,
    trade_report: TradeReport,
    sessions: tuple[date, ...],
    period_end: date,
    run_label: str,
) -> pd.DataFrame:
    index = {day: i for i, day in enumerate(sessions)}
    rows: list[dict[str, object]] = []
    for lot in trade_report.reconstruction.open_lots:
        opened = pd.Timestamp(lot.opened_at).date()
        rows.append(
            {
                "run_label": run_label,
                "source_fill_id": lot.source_fill_id,
                "stock_id": str(lot.ticker),
                "entry_at": pd.Timestamp(lot.opened_at).isoformat(),
                "quantity": float(lot.quantity),
                "unit_cost": float(lot.unit_cost),
                "held_days_at_period_end": int((period_end - opened).days),
                "held_sessions_at_period_end": (
                    int(index[period_end] - index[opened])
                    if opened in index and period_end in index
                    else None
                ),
            }
        )
    return pd.DataFrame(rows)


def _metrics(trades: pd.DataFrame, open_positions: pd.DataFrame) -> dict[str, object]:
    if trades.empty:
        returns = np.asarray([], dtype=float)
    else:
        returns = pd.to_numeric(trades["net_return"], errors="raise").to_numpy(dtype=float)
    wins = returns[returns > 0]
    losses = returns[returns < 0]
    avg_win = float(wins.mean()) if len(wins) else math.nan
    avg_loss_abs = float(abs(losses.mean())) if len(losses) else math.nan
    payoff = (
        float(avg_win / avg_loss_abs)
        if len(wins) and len(losses) and avg_loss_abs > 0
        else math.nan
    )
    result: dict[str, object] = {
        "n_closed": int(len(returns)),
        "n_open": int(len(open_positions)),
        "win_rate": float((returns > 0).mean()) if len(returns) else math.nan,
        "average_win": avg_win,
        "average_loss_abs": avg_loss_abs,
        "payoff_ratio": payoff,
        "average_net_return_per_trade": (
            float(returns.mean()) if len(returns) else math.nan
        ),
        "average_holding_days": (
            float(pd.to_numeric(trades["holding_days"]).mean())
            if not trades.empty
            else math.nan
        ),
        "average_holding_sessions": (
            float(pd.to_numeric(trades["holding_sessions"]).mean())
            if not trades.empty
            else math.nan
        ),
    }
    positive_total = float(wins.sum()) if len(wins) else 0.0
    ordered = np.sort(returns)[::-1] if len(returns) else returns
    for n in (1, 3, 5):
        top_positive = np.sort(wins)[::-1][:n] if len(wins) else wins
        result[f"top{n}_positive_return_share"] = (
            float(top_positive.sum() / positive_total)
            if positive_total > 0
            else math.nan
        )
        remaining = ordered[n:]
        result[f"expectancy_ex_top{n}"] = (
            float(remaining.mean()) if len(remaining) else math.nan
        )
        result[f"n_closed_ex_top{n}"] = int(len(remaining))
    return result


def _mfe_mae_diagnostics(
    *,
    source_root: Path,
    trades: pd.DataFrame,
    sessions: tuple[date, ...],
) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(
            columns=[
                "run_label",
                "source_fill_id",
                "stock_id",
                "status",
                "mfe",
                "mae",
            ]
        )
    adapter = SourceDataAdapter(source_root)
    years = sorted({pd.Timestamp(day).year for day in sessions})
    parts = []
    for year in years:
        rel = f"raw/prices_raw_{year}.parquet"
        if adapter.exists(rel):
            part = adapter.read_parquet(
                rel,
                columns=["date", "stock_id", "max", "min"],
            )
            part["date"] = pd.to_datetime(part["date"], errors="coerce").dt.normalize()
            part["stock_id"] = part["stock_id"].astype(str)
            parts.append(part)
    raw = (
        pd.concat(parts, ignore_index=True)
        if parts
        else pd.DataFrame(columns=["date", "stock_id", "max", "min"])
    )
    out: list[dict[str, object]] = []
    for row in trades.to_dict("records"):
        entry = pd.Timestamp(row["entry_at"]).normalize()
        exit_ = pd.Timestamp(row["exit_at"]).normalize()
        path = raw[
            raw["stock_id"].eq(str(row["stock_id"]))
            & raw["date"].between(entry, exit_, inclusive="both")
        ].copy()
        high = pd.to_numeric(path["max"], errors="coerce")
        low = pd.to_numeric(path["min"], errors="coerce")
        ref = float(row["entry_fill_price"])
        valid = (
            len(path) > 0
            and high.notna().all()
            and low.notna().all()
            and ref > 0
        )
        out.append(
            {
                "run_label": row["run_label"],
                "source_fill_id": row["source_fill_id"],
                "stock_id": row["stock_id"],
                "status": "OK" if valid else "UNAVAILABLE_RAW_PATH",
                "mfe": float((high / ref - 1.0).max()) if valid else math.nan,
                "mae": float((low / ref - 1.0).min()) if valid else math.nan,
            }
        )
    return pd.DataFrame(out)


def _json_safe(value):
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (float, np.floating)) and not math.isfinite(float(value)):
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    return value


def _write_outputs(artifacts: ExplorationRunArtifacts, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(
        json.dumps(
            _json_safe(artifacts.report),
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    artifacts.candidate_trades.to_csv(output_dir / "candidate_trades.csv", index=False)
    artifacts.capital_trades.to_csv(output_dir / "capital_constrained_trades.csv", index=False)
    artifacts.open_positions.to_csv(output_dir / "open_positions.csv", index=False)
    artifacts.eligibility_rows.to_csv(output_dir / "eligibility_audit.csv", index=False)
    artifacts.candidate_funnel.to_csv(output_dir / "candidate_funnel.csv", index=False)
    artifacts.mfe_mae.to_csv(output_dir / "mfe_mae_diagnostics.csv", index=False)


def run_synthetic_exploration(
    *,
    repo_root: str | Path,
    fixture_root: str | Path,
    output_dir: str | Path,
    method_config_path: str | Path = (
        "configs/research/baseline_60d_breakout_v1/exploration.yaml"
    ),
) -> ExplorationRunArtifacts:
    repo_root = Path(repo_root).resolve()
    fixture_root = Path(fixture_root).resolve()
    output_dir = Path(output_dir).resolve()
    method = load_frozen_method_config(repo_root / method_config_path)
    fixture = _canonical_yaml(fixture_root / "fixture.yaml")
    if _parse_scope(fixture.get("scope")) is not InputScope.SYNTHETIC_FIXTURE:
        raise BaselineExplorationError(
            "synthetic runner requires SYNTHETIC_FIXTURE fixture scope"
        )
    if fixture.get("mode") != "SYNTHETIC_FIXTURE":
        raise BaselineExplorationError(
            "fixture mode must be SYNTHETIC_FIXTURE"
        )

    sessions_raw = fixture.get("execution_sessions")
    if not isinstance(sessions_raw, list) or not sessions_raw:
        raise BaselineExplorationError("fixture execution_sessions must be non-empty")
    sessions = tuple(pd.Timestamp(value).date() for value in sessions_raw)

    source_root = fixture_root / "source"
    source_manifest = load_source_manifest(
        source_root=source_root,
        manifest_path=fixture_root / "source_manifest.json",
    )
    eligibility = load_eligibility_table(
        table_path=fixture_root / "eligibility.csv",
        manifest_path=fixture_root / "eligibility_manifest.json",
    )
    if source_manifest.scope is not InputScope.SYNTHETIC_FIXTURE:
        raise BaselineExplorationError("synthetic source manifest scope mismatch")
    if eligibility.manifest.scope is not InputScope.SYNTHETIC_FIXTURE:
        raise BaselineExplorationError("synthetic eligibility scope mismatch")
    if source_manifest.source_revision != eligibility.manifest.source_revision:
        raise BaselineExplorationError(
            "source revision mismatch between execution and eligibility evidence"
        )

    panel = pd.read_parquet(fixture_root / "panel.parquet")
    feature_integrator = FeaturePanelIntegrator(
        config=load_feature_panel_integration_config(
            fixture_root / "feature_integration.yaml"
        ),
        artifact_root=fixture_root / "feature_artifact",
        manifest_path=fixture_root / "feature_manifest.json",
        evidence_scope=EligibilityEvidenceScope.SYNTHETIC_FIXTURE,
        evidence_source="baseline_60d_exploration synthetic fixture",
    )
    joined = feature_integrator.hydrate(panel)
    if joined.evidence.source_revision != source_manifest.source_revision:
        raise BaselineExplorationError(
            "feature/source revision mismatch in synthetic fixture"
        )
    if joined.evidence.source_revision != eligibility.manifest.source_revision:
        raise BaselineExplorationError(
            "feature/eligibility revision mismatch in synthetic fixture"
        )

    candidate_settings, candidate_policy = _policy_from_fixture(
        dict(fixture["candidate_cohort_policy"])
    )
    capital_settings, capital_policy = _policy_from_fixture(
        dict(fixture["capital_constrained_policy"])
    )

    engine = ResearchConfigEngine()
    run_config_path = repo_root / str(method["run_config"])
    context = UniverseContext(
        p2_060_excluded_tickers=frozenset(),
        p2_060_exclusion_sha256=(
            "379d58f6a8aa06b1e020d56911930f4bc01861d3eeca109613d9e5b1e490d134"
        ),
    )
    signal_context = SignalContext(
        source_revision=source_manifest.source_revision
    )
    prepared_candidate = engine.prepare_hydrated(
        run_config_path=run_config_path,
        root=repo_root,
        feature_integrator=feature_integrator,
        feature_join_result=joined,
        universe_context=context,
        signal_context=signal_context,
        base_policy=candidate_policy,
        execution_sessions=sessions,
    )
    prepared_capital = engine.prepare_hydrated(
        run_config_path=run_config_path,
        root=repo_root,
        feature_integrator=feature_integrator,
        feature_join_result=joined,
        universe_context=context,
        signal_context=signal_context,
        base_policy=capital_policy,
        execution_sessions=sessions,
    )
    if prepared_candidate.run_config.strategy_version != method["strategy_version"]:
        raise BaselineExplorationError("prepared strategy version drift")
    if not prepared_candidate.candidates.equals(prepared_capital.candidates):
        raise BaselineExplorationError(
            "candidate set changed across execution policies"
        )

    qualified = qualify_candidates(prepared_candidate.candidates, eligibility)
    executable = qualified[
        qualified["eligibility_status"].eq(RowEligibilityStatus.ELIGIBLE.value)
    ].copy()
    candidate_columns = list(prepared_candidate.candidates.columns)
    executable_candidates = executable[candidate_columns].copy()

    baseline_context = BaselineSimulationContext(
        mode=BaselineSimulationMode.SYNTHETIC_FIXTURE
    )
    costs = dict(method["costs"])

    candidate_trade_parts: list[pd.DataFrame] = []
    candidate_open_parts: list[pd.DataFrame] = []
    candidate_fill_count = 0
    for ticker in sorted(executable_candidates["stock_id"].astype(str).unique()):
        subset = executable_candidates[
            executable_candidates["stock_id"].astype(str).eq(ticker)
        ].copy()
        prepared_one = _subset_prepared(
            prepared=prepared_candidate,
            candidates=subset,
            hydrated_panel=joined.frame,
            execution_sessions=sessions,
        )
        simulator, portfolio = _build_simulator(
            source_root=source_root,
            prepared=prepared_one,
            opening_cash_twd=candidate_settings.opening_cash_twd,
            costs=costs,
        )
        executed = engine.execute_prepared(
            prepared=prepared_one,
            simulator=simulator,
            sessions=sessions,
            baseline_context=baseline_context,
        )
        candidate_trade_parts.append(
            _trade_frame(
                trade_report=executed.trade_report,
                simulation=executed.simulation,
                portfolio=portfolio,
                sessions=sessions,
                run_label="CANDIDATE_COHORT",
            )
        )
        candidate_open_parts.append(
            _open_frame(
                trade_report=executed.trade_report,
                sessions=sessions,
                period_end=sessions[-1],
                run_label="CANDIDATE_COHORT",
            )
        )
        candidate_fill_count += len(portfolio_fills(portfolio))

    candidate_trades = (
        pd.concat(candidate_trade_parts, ignore_index=True)
        if candidate_trade_parts
        else pd.DataFrame()
    )
    candidate_open = (
        pd.concat(candidate_open_parts, ignore_index=True)
        if candidate_open_parts
        else pd.DataFrame()
    )

    prepared_capital_filtered = _subset_prepared(
        prepared=prepared_capital,
        candidates=executable_candidates,
        hydrated_panel=joined.frame,
        execution_sessions=sessions,
    )
    capital_simulator, capital_portfolio = _build_simulator(
        source_root=source_root,
        prepared=prepared_capital_filtered,
        opening_cash_twd=capital_settings.opening_cash_twd,
        costs=costs,
    )
    capital_executed = engine.execute_prepared(
        prepared=prepared_capital_filtered,
        simulator=capital_simulator,
        sessions=sessions,
        baseline_context=baseline_context,
    )
    capital_trades = _trade_frame(
        trade_report=capital_executed.trade_report,
        simulation=capital_executed.simulation,
        portfolio=capital_portfolio,
        sessions=sessions,
        run_label="CAPITAL_CONSTRAINED",
    )
    capital_open = _open_frame(
        trade_report=capital_executed.trade_report,
        sessions=sessions,
        period_end=sessions[-1],
        run_label="CAPITAL_CONSTRAINED",
    )
    open_positions = pd.concat(
        [candidate_open, capital_open],
        ignore_index=True,
    )

    funnel = qualified[
        [
            "signal_date",
            "stock_id",
            "eligibility_status",
            "reason_code",
            "reason_detail",
        ]
    ].copy()
    candidate_status_counts = {
        str(k): int(v)
        for k, v in funnel["eligibility_status"].value_counts(dropna=False).items()
    }
    candidate_reason_counts = {
        str(k): int(v)
        for k, v in funnel["reason_code"].value_counts(dropna=False).items()
    }

    diagnostics = _mfe_mae_diagnostics(
        source_root=source_root,
        trades=pd.concat(
            [candidate_trades, capital_trades],
            ignore_index=True,
        ),
        sessions=sessions,
    )

    report = {
        "schema_version": "1",
        "report_type": "baseline_60d_exploration_synthetic",
        "strategy_version": method["strategy_version"],
        "mode": "SYNTHETIC_FIXTURE",
        "formal_research_status": "BLOCKED",
        "method_config": str(method_config_path),
        "source_revision": source_manifest.source_revision,
        "execution_period": {
            "start": sessions[0].isoformat(),
            "end": sessions[-1].isoformat(),
            "session_count": len(sessions),
        },
        "costs": costs,
        "unfrozen_for_real_e1": list(method["unfrozen_for_real_e1"]),
        "population": {
            "row_denominator": int(len(eligibility.frame)),
            "unique_tickers": int(eligibility.frame["stock_id"].nunique()),
            "status_counts": eligibility.counts_by_status,
            "reason_counts": eligibility.counts_by_reason,
        },
        "candidate_funnel": {
            "signal_candidates": int(len(qualified)),
            "eligible_candidates": int(len(executable_candidates)),
            "status_counts": candidate_status_counts,
            "reason_counts": candidate_reason_counts,
        },
        "candidate_cohort": {
            "execution_basis": "PER_TICKER_INDEPENDENT_CANONICAL_SIMULATION",
            "fixture_policy": {
                **asdict(candidate_settings),
                "capacity_selection_rule": (
                    candidate_settings.capacity_selection_rule.value
                ),
            },
            "fill_count": int(candidate_fill_count),
            "metrics": _metrics(candidate_trades, candidate_open),
        },
        "capital_constrained": {
            "execution_basis": "SINGLE_CANONICAL_PORTFOLIO",
            "fixture_policy": {
                **asdict(capital_settings),
                "capacity_selection_rule": (
                    capital_settings.capacity_selection_rule.value
                ),
            },
            "entries_executed": int(capital_executed.simulation.total_entries),
            "entry_skips": int(capital_executed.simulation.total_entry_skips),
            "capacity_rejections": int(
                capital_executed.simulation.total_capacity_rejections
            ),
            "metrics": _metrics(capital_trades, capital_open),
        },
        "mfe_mae": {
            "role": "DIAGNOSTIC_ONLY",
            "row_count": int(len(diagnostics)),
            "status_counts": {
                str(k): int(v)
                for k, v in diagnostics["status"].value_counts(dropna=False).items()
            } if not diagnostics.empty else {},
        },
        "notes": [
            "synthetic fixture only; not a strategy-effect result",
            "candidate cohort and capital-constrained portfolio are reported separately",
            "eligibility denominator is retained; non-eligible rows are not zero-filled",
            "MFE/MAE are diagnostics and are not used for selection or headline claims",
            "FORMAL_RESEARCH remains unconditionally blocked",
        ],
    }
    artifacts = ExplorationRunArtifacts(
        report=report,
        candidate_trades=candidate_trades,
        capital_trades=capital_trades,
        open_positions=open_positions,
        eligibility_rows=eligibility.frame.copy(),
        candidate_funnel=funnel,
        mfe_mae=diagnostics,
    )
    _write_outputs(artifacts, output_dir)
    return artifacts


def build_synthetic_fixture(root: str | Path) -> Path:
    """Build a deterministic fixture; this never reads repository real data."""
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    (root / "source/raw").mkdir(parents=True, exist_ok=True)
    (root / "source/reference").mkdir(parents=True, exist_ok=True)
    (root / "feature_artifact").mkdir(parents=True, exist_ok=True)

    sessions = [x.date() for x in pd.bdate_range("2020-01-02", periods=64)]
    tickers = [
        "2330", "2454", "3008", "2317",
        "1101", "1216", "1301", "1303",
        "2002", "2207", "2303", "2357",
        "2881", "2882", "2891", "6505",
    ]
    signal_tickers = {"2330", "2454", "3008", "2317"}
    turnover = {
        ticker: float(80_000_000 - rank * 2_000_000)
        for rank, ticker in enumerate(tickers)
    }
    panel_rows: list[dict[str, object]] = []
    feature_rows: list[dict[str, object]] = []
    raw_rows: list[dict[str, object]] = []
    trad_rows: list[dict[str, object]] = []
    eligibility_rows: list[dict[str, object]] = []

    for ticker in tickers:
        for idx, day in enumerate(sessions):
            signal_close = 110.0 if ticker in signal_tickers and idx == 61 else 100.0
            panel_rows.append(
                {
                    "date": day,
                    "stock_id": ticker,
                    "close": signal_close,
                    "Trading_money": turnover[ticker],
                    "observed_trade": True,
                    "valid_ohlc": True,
                    "__decision_cutoff_at": pd.Timestamp(day) + pd.Timedelta(days=1, hours=8, minutes=45),
                }
            )
            feature_rows.append(
                {
                    "date": day,
                    "stock_id": ticker,
                    "close_to_ma120": 0.10,
                    "prior20_amount_twd": 30_000_000.0,
                    "available_at_date": day,
                    "source_available_at": pd.Timestamp(day) + pd.Timedelta(hours=18),
                    "bars_seen": 200 + idx,
                }
            )

            close = 100.0
            open_ = 100.0
            high = 101.0
            low = 99.0
            if ticker in signal_tickers and idx == 61:
                close, open_, high, low = 110.0, 100.0, 111.0, 99.0
            if ticker in {"2330", "2454"} and idx == 62:
                close, open_, high, low = 90.0, 100.0, 101.0, 89.0
            if ticker == "3008" and idx == 62:
                close, open_, high, low = 110.0, 100.0, 111.0, 99.0
            if ticker == "2330" and idx == 63:
                close, open_, high, low = 105.0, 105.0, 106.0, 104.0
            if ticker == "2454" and idx == 63:
                close, open_, high, low = 95.0, 95.0, 96.0, 94.0
            raw_rows.append(
                {
                    "date": day,
                    "stock_id": ticker,
                    "open": open_,
                    "max": high,
                    "min": low,
                    "close": close,
                }
            )
            trad_rows.append(
                {
                    "date": day,
                    "stock_id": ticker,
                    "observed_trade": True,
                    "valid_ohlc": True,
                    "buy_blocked": False,
                    "sell_blocked": False,
                    "reason": "OBSERVED",
                }
            )
            if ticker == "2317":
                status = RowEligibilityStatus.BLOCKED.value
                reason = "ECONOMIC_CONTENT_UNRESOLVED"
                detail = "synthetic unresolved economic-content fixture"
            else:
                status = RowEligibilityStatus.ELIGIBLE.value
                reason = "ELIGIBLE"
                detail = "synthetic eligible fixture"
            eligibility_rows.append(
                {
                    "date": day,
                    "stock_id": ticker,
                    "eligibility_status": status,
                    "reason_code": reason,
                    "reason_detail": detail,
                }
            )

    panel = pd.DataFrame(panel_rows)
    panel.to_parquet(root / "panel.parquet", index=False)
    feature = pd.DataFrame(feature_rows)
    feature_path = root / "feature_artifact/stock_features_2020.parquet"
    feature.to_parquet(feature_path, index=False)
    raw_path = root / "source/raw/prices_raw_2020.parquet"
    pd.DataFrame(raw_rows).to_parquet(raw_path, index=False)
    trad_path = root / "source/reference/tradability.parquet"
    pd.DataFrame(trad_rows).to_parquet(trad_path, index=False)
    eligibility_path = root / "eligibility.csv"
    pd.DataFrame(eligibility_rows).to_csv(eligibility_path, index=False)

    source_revision = "synthetic-baseline-exploration-v1"
    feature_manifest = {
        "artifact_name": "synthetic-baseline-exploration-features",
        "source_revision": source_revision,
        "formula_version": "baseline-60d-synthetic-features-v1",
        "epoch": "SYNTHETIC_E2E",
        "period": [str(sessions[0]), str(sessions[-1])],
        "stock_files": [
            {
                "path": "stock_features_2020.parquet",
                "rows": len(feature),
                "sha256": sha256_file(feature_path),
            }
        ],
    }
    (root / "feature_manifest.json").write_text(
        json.dumps(feature_manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    feature_config = {
        "schema_version": "1",
        "name": "baseline-60d-synthetic-exploration-features",
        "epoch": "SYNTHETIC_E2E",
        "artifact": {
            "manifest_path": str(root / "feature_manifest.json"),
            "artifact_name": feature_manifest["artifact_name"],
            "source_revision": source_revision,
            "formula_version": feature_manifest["formula_version"],
            "epoch": "SYNTHETIC_E2E",
        },
        "policy": {"strategy_required_status": "VERIFIED"},
        "availability_groups": {
            "synthetic_verified": {"status": "VERIFIED"}
        },
        "requested_features": [
            {
                "column": "close_to_ma120",
                "kind": "RAW",
                "required": True,
                "warmup_sessions": 120,
                "dependencies": ["synthetic_verified"],
                "expected_status": "VERIFIED",
            },
            {
                "column": "prior20_amount_twd",
                "kind": "RAW",
                "required": True,
                "warmup_sessions": 20,
                "dependencies": ["synthetic_verified"],
                "expected_status": "VERIFIED",
            },
        ],
    }
    (root / "feature_integration.yaml").write_text(
        yaml.safe_dump(feature_config, sort_keys=False),
        encoding="utf-8",
    )

    eligibility_manifest = {
        "schema_version": "1",
        "scope": "SYNTHETIC_FIXTURE",
        "source_revision": source_revision,
        "epoch": "SYNTHETIC_E2E",
        "period_start": str(sessions[0]),
        "period_end": str(sessions[-1]),
        "row_count": len(eligibility_rows),
        "table_sha256": sha256_file(eligibility_path),
    }
    (root / "eligibility_manifest.json").write_text(
        json.dumps(eligibility_manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    source_manifest = {
        "schema_version": "1",
        "scope": "SYNTHETIC_FIXTURE",
        "source_revision": source_revision,
        "period_start": str(sessions[0]),
        "period_end": str(sessions[-1]),
        "files": [
            {
                "path": "raw/prices_raw_2020.parquet",
                "sha256": sha256_file(raw_path),
            },
            {
                "path": "reference/tradability.parquet",
                "sha256": sha256_file(trad_path),
            },
        ],
    }
    (root / "source_manifest.json").write_text(
        json.dumps(source_manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    fixture = {
        "schema_version": "1",
        "scope": "SYNTHETIC_FIXTURE",
        "mode": "SYNTHETIC_FIXTURE",
        "execution_sessions": [day.isoformat() for day in sessions],
        "candidate_cohort_policy": {
            "opening_cash_twd": 10_000_000.0,
            "position_fraction": 0.5,
            "max_positions": 1,
            "capacity_selection_rule": "TICKER_ASC",
        },
        "capital_constrained_policy": {
            "opening_cash_twd": 10_000_000.0,
            "position_fraction": 0.3,
            "max_positions": 2,
            "capacity_selection_rule": "TICKER_ASC",
        },
        "note": (
            "fixture-only execution mechanics; these values are not frozen "
            "for real E1"
        ),
    }
    (root / "fixture.yaml").write_text(
        yaml.safe_dump(fixture, sort_keys=False),
        encoding="utf-8",
    )
    return root
