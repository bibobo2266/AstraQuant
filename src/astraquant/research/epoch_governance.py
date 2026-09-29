from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from pathlib import Path
from typing import Iterable

import pandas as pd

E1_START = date(2016, 1, 4)
E1_END = date(2021, 12, 31)
E2_START = date(2022, 1, 1)
E2_END = date(2026, 6, 30)
E3_START = date(2026, 7, 1)
E2_LABEL_TW = "E2：已接觸歷史驗證期，非獨立樣本外"
PUBLIC_DISCLOSURE_TW = (
    "已完成歷史回測與跨時期穩定性分析；部分歷史驗證資料曾參與"
    "研究判讀，因此不宣稱為獨立樣本外驗證。凍結版本後，另行"
    "累積前瞻結果。"
)
LEGACY_BREAKOUT_REGRESSION_EXEMPTION_ID = "EX-001"
LEGACY_BREAKOUT_EXPECTED_NAV = Decimal("51696620.30")


class Epoch(str, Enum):
    E1 = "E1"
    E2 = "E2"
    E3 = "E3"
    E4 = "E4"


class QueryKind(str, Enum):
    EFFECT = "EFFECT"
    ACCESS_RECORD = "ACCESS_RECORD"
    DATA_PROCESSING_RANGE = "DATA_PROCESSING_RANGE"
    DATA_QUALITY = "DATA_QUALITY"


class EpochGovernanceError(ValueError):
    pass


class E3EffectQueryBlocked(EpochGovernanceError):
    pass


class E2ExplicitFlagRequired(EpochGovernanceError):
    pass


class E4RegistrationError(EpochGovernanceError):
    pass


@dataclass(frozen=True)
class StrategyVersionRecord:
    strategy_version: str
    frozen_at: datetime | None
    validation_start_date: date | None
    entry_rules: str
    exit_rules: str
    parameters: str
    universe_rules: str
    market_context_rules: str
    cost_assumptions: str
    capital_rules: str
    validation_length: str | None = None
    validation_criteria: str | None = None

    def __post_init__(self) -> None:
        required = {
            "strategy_version": self.strategy_version,
            "entry_rules": self.entry_rules,
            "exit_rules": self.exit_rules,
            "parameters": self.parameters,
            "universe_rules": self.universe_rules,
            "market_context_rules": self.market_context_rules,
            "cost_assumptions": self.cost_assumptions,
            "capital_rules": self.capital_rules,
        }
        missing = [name for name, value in required.items() if not str(value).strip()]
        if missing:
            raise ValueError(f"strategy version record missing fields: {missing}")
        if (self.frozen_at is None) != (self.validation_start_date is None):
            raise ValueError(
                "frozen_at and validation_start_date must both be set or both be blank"
            )
        if self.frozen_at is not None and self.validation_start_date is not None:
            if self.validation_start_date < self.frozen_at.date():
                raise ValueError("validation_start_date cannot precede frozen_at date")

    @property
    def is_frozen(self) -> bool:
        return self.frozen_at is not None

    def require_e4_preregistration(self) -> None:
        if not self.is_frozen or self.validation_start_date is None:
            raise E4RegistrationError(
                f"strategy version {self.strategy_version} is not frozen for E4"
            )
        if not (self.validation_length or "").strip():
            raise E4RegistrationError("E4 validation_length must be preregistered")
        if not (self.validation_criteria or "").strip():
            raise E4RegistrationError("E4 validation_criteria must be preregistered")


@dataclass(frozen=True)
class EffectPeriod:
    epoch: Epoch
    start: date
    end: date | None
    label: str


@dataclass(frozen=True)
class WindowPurgeResult:
    included: pd.DataFrame
    cross_boundary_count: int
    unavailable_endpoint_count: int


def _parse_date(value: str) -> date | None:
    value = value.strip()
    return date.fromisoformat(value) if value else None


def _parse_datetime(value: str) -> datetime | None:
    value = value.strip()
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def load_strategy_version_registry(path: str | Path) -> dict[str, StrategyVersionRecord]:
    records: dict[str, StrategyVersionRecord] = {}
    with Path(path).open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            record = StrategyVersionRecord(
                strategy_version=row["strategy_version"].strip(),
                frozen_at=_parse_datetime(row.get("frozen_at", "")),
                validation_start_date=_parse_date(row.get("validation_start_date", "")),
                entry_rules=row["entry_rules"].strip(),
                exit_rules=row["exit_rules"].strip(),
                parameters=row["parameters"].strip(),
                universe_rules=row["universe_rules"].strip(),
                market_context_rules=row["market_context_rules"].strip(),
                cost_assumptions=row["cost_assumptions"].strip(),
                capital_rules=row["capital_rules"].strip(),
                validation_length=(row.get("validation_length") or "").strip() or None,
                validation_criteria=(row.get("validation_criteria") or "").strip() or None,
            )
            if record.strategy_version in records:
                raise ValueError(f"duplicate strategy_version: {record.strategy_version}")
            records[record.strategy_version] = record
    return records


def epoch_for_date(record: StrategyVersionRecord, value: date) -> Epoch:
    if E1_START <= value <= E1_END:
        return Epoch.E1
    if E2_START <= value <= E2_END:
        return Epoch.E2
    if value >= E3_START:
        if record.validation_start_date is not None and value >= record.validation_start_date:
            return Epoch.E4
        return Epoch.E3
    raise EpochGovernanceError(f"date precedes governed history: {value.isoformat()}")


def resolve_historical_effect_period(
    requested_epoch: str | Epoch | None = None,
) -> EffectPeriod:
    epoch = Epoch(requested_epoch or Epoch.E1)
    if epoch is Epoch.E1:
        return EffectPeriod(epoch, E1_START, E1_END, "E1：歷史開發期")
    if epoch is Epoch.E2:
        return EffectPeriod(epoch, E2_START, E2_END, E2_LABEL_TW)
    if epoch is Epoch.E3:
        raise E3EffectQueryBlocked("E3 策略效果查詢禁止")
    raise E4RegistrationError("E4 效果查詢必須指定已登記且已凍結的 strategy_version")


def resolve_effect_period(
    record: StrategyVersionRecord,
    requested_epoch: str | Epoch | None = None,
) -> EffectPeriod:
    epoch = Epoch(requested_epoch or Epoch.E1)
    if epoch is Epoch.E1:
        return EffectPeriod(epoch, E1_START, E1_END, "E1：歷史開發期")
    if epoch is Epoch.E2:
        return EffectPeriod(epoch, E2_START, E2_END, E2_LABEL_TW)
    if epoch is Epoch.E3:
        raise E3EffectQueryBlocked("E3 策略效果查詢禁止")
    record.require_e4_preregistration()
    assert record.validation_start_date is not None
    return EffectPeriod(epoch, record.validation_start_date, None, "E4：前瞻驗證期")


def authorize_query(
    record: StrategyVersionRecord,
    *,
    start: date,
    end: date,
    kind: QueryKind,
    allow_e2: bool = False,
) -> tuple[Epoch, ...]:
    if end < start:
        raise ValueError("query end cannot precede start")
    if kind is not QueryKind.EFFECT:
        return tuple(
            sorted(
                {epoch_for_date(record, start), epoch_for_date(record, end)},
                key=lambda x: x.value,
            )
        )
    e3_end = record.validation_start_date if record.validation_start_date is not None else None
    e3_overlaps = end >= E3_START and (e3_end is None or start < e3_end)
    if e3_overlaps:
        raise E3EffectQueryBlocked("E3 策略效果查詢禁止")
    e2_overlaps = start <= E2_END and end >= E2_START
    if e2_overlaps and not allow_e2:
        raise E2ExplicitFlagRequired(E2_LABEL_TW)
    e4_overlaps = (
        record.validation_start_date is not None
        and end >= record.validation_start_date
    )
    if e4_overlaps:
        record.require_e4_preregistration()
    checkpoints = {start, end}
    if start <= E1_END <= end:
        checkpoints.add(E1_END)
    if start <= E2_START <= end:
        checkpoints.add(E2_START)
    if start <= E2_END <= end:
        checkpoints.add(E2_END)
    if record.validation_start_date and start <= record.validation_start_date <= end:
        checkpoints.add(record.validation_start_date)
    return tuple(
        sorted({epoch_for_date(record, d) for d in checkpoints}, key=lambda x: x.value)
    )


def purge_path_windows(
    candidates: pd.DataFrame,
    *,
    trading_sessions: Iterable[date | pd.Timestamp],
    period_start: date,
    period_end: date,
    window_sessions: int,
    signal_date_col: str = "date",
) -> WindowPurgeResult:
    if window_sessions not in {5, 10, 20}:
        raise ValueError("path diagnostic window must be one of 5/10/20 sessions")
    if signal_date_col not in candidates.columns:
        raise ValueError(f"missing signal date column: {signal_date_col}")
    sessions = pd.DatetimeIndex(pd.to_datetime(list(trading_sessions))).normalize()
    if sessions.has_duplicates:
        raise ValueError("trading_sessions contains duplicates")
    sessions = sessions.sort_values()
    positions = {ts: i for i, ts in enumerate(sessions)}
    x = candidates.copy()
    signal_dates = pd.to_datetime(x[signal_date_col], errors="coerce").dt.normalize()
    if signal_dates.isna().any():
        raise ValueError("candidate signal dates contain null/invalid values")
    in_period = signal_dates.between(
        pd.Timestamp(period_start), pd.Timestamp(period_end), inclusive="both"
    )
    endpoint_dates = []
    cross = 0
    unavailable = 0
    keep = []
    for dt, eligible in zip(signal_dates, in_period):
        if not eligible:
            endpoint_dates.append(pd.NaT)
            keep.append(False)
            continue
        pos = positions.get(dt)
        if pos is None or pos + window_sessions >= len(sessions):
            endpoint_dates.append(pd.NaT)
            unavailable += 1
            keep.append(False)
            continue
        endpoint = sessions[pos + window_sessions]
        endpoint_dates.append(endpoint)
        if endpoint > pd.Timestamp(period_end):
            cross += 1
            keep.append(False)
        else:
            keep.append(True)
    x["window_end_date"] = endpoint_dates
    return WindowPurgeResult(
        included=x.loc[keep].copy(),
        cross_boundary_count=cross,
        unavailable_endpoint_count=unavailable,
    )


def legacy_breakout_nav_regression_matches(actual_final_nav: float | Decimal) -> bool:
    actual = Decimal(str(actual_final_nav)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return actual == LEGACY_BREAKOUT_EXPECTED_NAV


def assert_legacy_breakout_nav_regression(actual_final_nav: float | Decimal) -> None:
    actual = Decimal(str(actual_final_nav)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    difference = (actual - LEGACY_BREAKOUT_EXPECTED_NAV).copy_abs()
    if actual != LEGACY_BREAKOUT_EXPECTED_NAV:
        raise EpochGovernanceError(f"回歸失敗；差異金額：{difference:.2f}")
