from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LogicalOp(str, Enum):
    AND = "AND"
    OR = "OR"


class GroupingMode(str, Enum):
    OFFICIAL = "OFFICIAL"
    THEME = "THEME"
    CORRELATION = "CORRELATION"


class PoolType(str, Enum):
    ALL = "ALL"
    STABLE = "STABLE"
    INDUSTRY_THEME = "INDUSTRY_THEME"
    FUNDAMENTAL_FLOOR = "FUNDAMENTAL_FLOOR"
    EARNINGS_STREAK = "EARNINGS_STREAK"


class TriggerType(str, Enum):
    N_SESSION_HIGH = "N_SESSION_HIGH"
    GAP_UP = "GAP_UP"
    VOLUME_SPIKE = "VOLUME_SPIKE"
    MA_GOLDEN_CROSS = "MA_GOLDEN_CROSS"
    MACD_CROSS_ABOVE_ZERO = "MACD_CROSS_ABOVE_ZERO"
    KD_LOW_ZONE_GOLDEN_CROSS = "KD_LOW_ZONE_GOLDEN_CROSS"
    RSI_CROSS = "RSI_CROSS"
    BOLLINGER_UPPER_BREAK = "BOLLINGER_UPPER_BREAK"
    ICHIMOKU = "ICHIMOKU"
    PULLBACK_RECLAIM = "PULLBACK_RECLAIM"
    CONSECUTIVE_UP_DAYS = "CONSECUTIVE_UP_DAYS"


class ExitType(str, Enum):
    FIXED_STOP_TARGET = "FIXED_STOP_TARGET"
    MA_BREAK = "MA_BREAK"
    EMA_BREAK = "EMA_BREAK"
    ICHIMOKU_BREAK = "ICHIMOKU_BREAK"
    BOLLINGER_MIDLINE_BREAK = "BOLLINGER_MIDLINE_BREAK"
    ATR_TRAILING = "ATR_TRAILING"
    PERCENT_TRAILING = "PERCENT_TRAILING"
    DONCHIAN_BREAK = "DONCHIAN_BREAK"
    TIME_EXIT = "TIME_EXIT"


class BaseUniverseConfig(FrozenModel):
    ticker_pattern: str = r"^[1-9]\d{3}$"
    min_close_twd: float = 10.0
    require_observed_trade: bool = True
    require_valid_ohlc: bool = True
    p2_060_exclusion_sha256: str = (
        "379d58f6a8aa06b1e020d56911930f4bc01861d3eeca109613d9e5b1e490d134"
    )


class AllPoolConfig(FrozenModel):
    type: Literal["ALL"] = "ALL"
    turnover_top_fraction: float = Field(default=0.25, gt=0, le=1)


class StablePoolConfig(FrozenModel):
    type: Literal["STABLE"] = "STABLE"
    index_down_threshold: float = Field(default=-0.01, lt=0)
    downside_rs_multiplier: float = Field(default=0.70, gt=0)
    downside_rs_lookback: int = Field(default=250, ge=2)
    rv60_bottom_fraction: float = Field(default=0.40, gt=0, le=1)
    max_drawdown_multiplier: float = Field(default=1.20, gt=0)
    max_drawdown_lookback: int = Field(default=250, ge=2)
    large_holder_min_fraction: float = Field(default=0.60, ge=0, le=1)
    large_holder_max_change_pp: float = Field(default=5.0, ge=0)
    holder_lookback: int = Field(default=250, ge=2)
    consecutive_dividend_years: int = Field(default=5, ge=0)
    turnover_ratio_bottom_fraction: float = Field(default=0.50, gt=0, le=1)


class OfficialGroupingConfig(FrozenModel):
    mode: Literal["OFFICIAL"] = "OFFICIAL"
    groups: tuple[
        Literal[
            "電子上游",
            "電子下游",
            "工業運輸營建",
            "內需消費",
            "原物料",
            "生技醫療",
            "其他",
            "金融",
        ],
        ...,
    ]
    leakage_note_required: bool = True


class ThemeGroupingConfig(FrozenModel):
    mode: Literal["THEME"] = "THEME"
    themes: tuple[str, ...]
    combine: LogicalOp = LogicalOp.OR
    dated_membership_required: bool = True


class CorrelationGroupingConfig(FrozenModel):
    mode: Literal["CORRELATION"] = "CORRELATION"
    return_lookback: int = Field(default=120, ge=20)
    recompute_every_sessions: int = Field(default=20, ge=1)
    cluster_method: str = "hierarchical"
    cluster_selector: dict[str, Any]


GroupingConfig = OfficialGroupingConfig | ThemeGroupingConfig | CorrelationGroupingConfig


class IndustryThemePoolConfig(FrozenModel):
    type: Literal["INDUSTRY_THEME"] = "INDUSTRY_THEME"
    groups: tuple[GroupingConfig, ...]
    combine: LogicalOp = LogicalOp.AND


class FundamentalFloorConfig(FrozenModel):
    type: Literal["FUNDAMENTAL_FLOOR"] = "FUNDAMENTAL_FLOOR"
    max_consecutive_loss_quarters: int = Field(default=1, ge=0)
    lookback_quarters: int = Field(default=4, ge=1)
    max_debt_ratio: float = Field(default=0.70, gt=0)
    exempt_financials: bool = True
    max_consecutive_revenue_decline_months: int = Field(default=2, ge=0)
    roe_quarter_average_min: float = 0.0
    roe_lookback_quarters: int = Field(default=4, ge=1)


class EarningsStreakConfig(FrozenModel):
    type: Literal["EARNINGS_STREAK"] = "EARNINGS_STREAK"
    consecutive_positive_eps_yoy_quarters: Literal[2, 3, 4] = 2


UniversePoolConfig = (
    AllPoolConfig
    | StablePoolConfig
    | IndustryThemePoolConfig
    | FundamentalFloorConfig
    | EarningsStreakConfig
)


class UniverseConfig(FrozenModel):
    schema_version: Literal["1"] = "1"
    name: str
    base: BaseUniverseConfig = BaseUniverseConfig()
    pools: tuple[UniversePoolConfig, ...]
    combine: LogicalOp = LogicalOp.AND

    @model_validator(mode="after")
    def require_pool(self):
        if not self.pools:
            raise ValueError("at least one universe pool is required")
        return self


class ThemeMember(FrozenModel):
    ticker: str
    from_date: date = Field(alias="from")
    to: date | None = None
    source: str

    @model_validator(mode="after")
    def validate_dates_and_source(self):
        if self.to is not None and self.to < self.from_date:
            raise ValueError("theme member to must be on/after from")
        if not self.source.strip():
            raise ValueError("theme member source is required")
        return self


class ThemeFile(FrozenModel):
    schema_version: Literal["1"] = "1"
    theme: str
    members: tuple[ThemeMember, ...]
    notes: str = ""


class ComponentSpec(FrozenModel):
    type: str
    params: dict[str, Any] = Field(default_factory=dict)


class SignalConfig(FrozenModel):
    schema_version: Literal["1"] = "1"
    name: str
    trigger: ComponentSpec
    filters: tuple[ComponentSpec, ...] = ()
    filter_combine: LogicalOp = LogicalOp.AND
    ranking: tuple[ComponentSpec, ...] = ()


class ExitRuleConfig(FrozenModel):
    type: str
    params: dict[str, Any] = Field(default_factory=dict)


class ExitConfig(FrozenModel):
    schema_version: Literal["1"] = "1"
    name: str
    rules: tuple[ExitRuleConfig, ...]
    first_trigger_wins: bool = True

    @model_validator(mode="after")
    def require_rule(self):
        if not self.rules:
            raise ValueError("at least one exit rule is required")
        return self


class StrategyRunConfig(FrozenModel):
    schema_version: Literal["1"] = "1"
    run_name: str
    universe: str
    signal: str
    exit: str
    execution_assumptions_id: str
    report_trade_stats_first: Literal[True] = True


class AvailabilityContract(FrozenModel):
    financial_statements_use_available_date: Literal[True] = True
    quarterly_deadlines: dict[str, str] = Field(default_factory=lambda: {
        "Q1": "05-15",
        "Q2": "08-14",
        "Q3": "11-14",
        "Q4": "following-03-31",
    })
    monthly_revenue_available_day_next_month: Literal[10] = 10
    institutional_and_margin_usable: Literal["T+1"] = "T+1"
    universe_mask_must_preserve_rows: Literal[True] = True
