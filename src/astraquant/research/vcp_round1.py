from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from collections import deque
import math
from typing import Iterable

import numpy as np
import pandas as pd

from astraquant.data.market_coordinates import PriceUse
from astraquant.execution.fills import ExecutionFillFactory, NotExecutableError
from astraquant.execution.market_data import ExecutionAvailability, ExecutionMarketData
from astraquant.execution.service import CanonicalExecutionService, SignalDeclaration
from astraquant.portfolio.calendar import TradingCalendar
from astraquant.portfolio.corporate_actions import CashEntitlementBasis, CorporateActionType
from astraquant.portfolio.engine import PortfolioEngine, SettlementInstruction
from astraquant.portfolio.historical_runner import HistoricalCorporateActionInstruction
from astraquant.portfolio.models import OrderIntent
from astraquant.research.exit_engine import CompiledExitPlan


@dataclass(frozen=True)
class VCPRound1ExitSettings:
    atr_period: int
    atr_multiplier: float
    ma_window: int


@dataclass(frozen=True)
class VCPRound1ExecutionSettings:
    chase_multiple: float
    normalized_initial_notional: float
    settlement_lag_sessions: int
    adjustment_method: str

    def __post_init__(self) -> None:
        if self.chase_multiple <= 1:
            raise ValueError("chase_multiple must exceed 1")
        if self.normalized_initial_notional <= 0:
            raise ValueError("normalized_initial_notional must be positive")
        if self.settlement_lag_sessions < 0:
            raise ValueError("settlement_lag_sessions must be non-negative")
        if not self.adjustment_method.strip():
            raise ValueError("adjustment_method is required")


@dataclass(frozen=True)
class ConfigTradeSimulation:
    trades: pd.DataFrame
    open_positions: pd.DataFrame
    signal_count: int
    entry_count: int
    ignored_while_holding: int
    chase_reject_count: int
    other_unfilled_count: int
    unfilled_reason_counts: dict[str, int]
    unverified_terminal_trade_count: int


def compile_round1_exit_settings(plan: CompiledExitPlan) -> VCPRound1ExitSettings:
    if plan.stop_fraction is not None or plan.max_hold_sessions is not None:
        raise ValueError("VCP round1 forbids legacy fixed-stop and max-hold exits")
    by_type = {rule.type: rule for rule in plan.close_exit_rules}
    if set(by_type) != {"ATR_TRAILING", "MA_BREAK"}:
        raise ValueError(
            "VCP round1 requires exactly ATR_TRAILING and MA_BREAK close rules"
        )
    atr = by_type["ATR_TRAILING"].params
    ma = by_type["MA_BREAK"].params
    return VCPRound1ExitSettings(
        atr_period=int(atr["period"]),
        atr_multiplier=float(atr["multiplier"]),
        ma_window=int(ma["window"]),
    )


def build_common_session_panel(
    panel: pd.DataFrame,
    *,
    ticker_scope: Iterable[str],
    end: pd.Timestamp,
) -> pd.DataFrame:
    """Expand research rows to a common-session grid without filling values."""
    required = {
        "date",
        "stock_id",
        "open",
        "max",
        "min",
        "close",
        "Trading_money",
        "Trading_Volume",
        "observed_trade",
        "valid_ohlc",
    }
    missing = required - set(panel.columns)
    if missing:
        raise ValueError(f"common-session panel missing columns: {sorted(missing)}")

    x = panel.copy()
    x["date"] = pd.to_datetime(x["date"], errors="coerce").dt.normalize()
    x["stock_id"] = x["stock_id"].astype(str)
    x = x[x["date"].le(pd.Timestamp(end).normalize())].copy()
    tickers = sorted({str(v) for v in ticker_scope})
    x = x[x["stock_id"].isin(tickers)].copy()
    if x.duplicated(["date", "stock_id"]).any():
        raise ValueError("research panel has duplicate logical keys")

    sessions = pd.DatetimeIndex(x["date"].dropna().unique()).sort_values()
    grid = pd.MultiIndex.from_product(
        [tickers, sessions], names=["stock_id", "date"]
    )
    out = x.set_index(["stock_id", "date"]).reindex(grid).reset_index()
    out["observed_trade"] = out["observed_trade"].fillna(False).astype(bool)
    out["valid_ohlc"] = out["valid_ohlc"].fillna(False).astype(bool)
    return out.sort_values(["stock_id", "date"], kind="stable").reset_index(drop=True)


def build_adjusted_exit_features(
    panel: pd.DataFrame,
    *,
    atr_period: int,
    ma_window: int,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """Build exact Wilder ATR and D-SMA on valid adjusted research bars.

    ATR seed is the simple mean of the first atr_period valid TR values.
    Missing bars do not get filled. The next valid TR uses the previous valid
    close, which keeps suspension gaps explicit without inventing prices.
    """
    if atr_period <= 0 or ma_window <= 0:
        raise ValueError("exit feature windows must be positive")
    required = {"date", "stock_id", "max", "min", "close"}
    missing = required - set(panel.columns)
    if missing:
        raise ValueError(f"exit feature panel missing columns: {sorted(missing)}")

    x = panel[list(required)].copy()
    x["date"] = pd.to_datetime(x["date"], errors="coerce").dt.normalize()
    x["stock_id"] = x["stock_id"].astype(str)
    x = x[x["date"].le(pd.Timestamp(end).normalize())].copy()
    x = x.sort_values(["stock_id", "date"], kind="stable").reset_index(drop=True)

    rows: list[pd.DataFrame] = []
    for ticker, group in x.groupby("stock_id", sort=False):
        g = group.copy()
        high = pd.to_numeric(g["max"], errors="coerce").to_numpy(float)
        low = pd.to_numeric(g["min"], errors="coerce").to_numpy(float)
        close = pd.to_numeric(g["close"], errors="coerce").to_numpy(float)
        atr_out = np.full(len(g), np.nan, dtype=float)
        ma_out = np.full(len(g), np.nan, dtype=float)

        prev_valid_close: float | None = None
        seed_tr: list[float] = []
        atr_state: float | None = None
        close_window: deque[float] = deque(maxlen=ma_window)

        for i in range(len(g)):
            h, l, c = high[i], low[i], close[i]
            valid = (
                np.isfinite(h)
                and np.isfinite(l)
                and np.isfinite(c)
                and h > 0
                and l > 0
                and c > 0
                and h >= max(l, c)
                and l <= min(h, c)
            )
            if not valid:
                continue

            if prev_valid_close is None:
                tr = h - l
            else:
                tr = max(
                    h - l,
                    abs(h - prev_valid_close),
                    abs(l - prev_valid_close),
                )

            if atr_state is None:
                seed_tr.append(float(tr))
                if len(seed_tr) == atr_period:
                    atr_state = float(np.mean(seed_tr))
            else:
                atr_state = ((atr_period - 1) * atr_state + float(tr)) / atr_period

            if atr_state is not None:
                atr_out[i] = atr_state

            close_window.append(float(c))
            if len(close_window) == ma_window:
                ma_out[i] = float(np.mean(close_window))
            prev_valid_close = float(c)

        g["adjusted_high"] = high
        g["adjusted_close"] = close
        g["atr"] = atr_out
        g["d_ma"] = ma_out
        rows.append(
            g[
                [
                    "date",
                    "stock_id",
                    "adjusted_high",
                    "adjusted_close",
                    "atr",
                    "d_ma",
                ]
            ]
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "date",
                "stock_id",
                "adjusted_high",
                "adjusted_close",
                "atr",
                "d_ma",
            ]
        )
    return pd.concat(rows, ignore_index=True)


def update_atr_trail(
    previous_trail: float | None,
    *,
    high_watermark: float,
    atr: float,
    multiplier: float,
) -> float:
    candidate = float(high_watermark) - float(multiplier) * float(atr)
    if previous_trail is None:
        return candidate
    return max(float(previous_trail), candidate)


def close_exit_reason(
    *,
    close: float,
    atr_trail: float | None,
    d_ma: float | None,
) -> str | None:
    atr_hit = (
        atr_trail is not None
        and math.isfinite(float(atr_trail))
        and float(close) < float(atr_trail)
    )
    ma_hit = (
        d_ma is not None
        and math.isfinite(float(d_ma))
        and float(close) < float(d_ma)
    )
    if atr_hit and ma_hit:
        return "BOTH"
    if atr_hit:
        return "ATR"
    if ma_hit:
        return "D21"
    return None


class VCPRound1TradeRunner:
    """Independent equal-notional research using canonical execution/accounting."""

    def __init__(
        self,
        *,
        market_data: ExecutionMarketData,
        fill_factory: ExecutionFillFactory,
        signal: SignalDeclaration,
        sessions: Iterable[date | pd.Timestamp],
        adjusted_exit_features: pd.DataFrame,
        corporate_actions: Iterable[HistoricalCorporateActionInstruction],
        exit_settings: VCPRound1ExitSettings,
        execution_settings: VCPRound1ExecutionSettings,
    ) -> None:
        self.market_data = market_data
        self.fill_factory = fill_factory
        self.signal = signal
        self.calendar = TradingCalendar([pd.Timestamp(x).date() for x in sessions])
        self.sessions = self.calendar.sessions
        self.session_index = {day: i for i, day in enumerate(self.sessions)}
        self.exit_settings = exit_settings
        self.execution_settings = execution_settings

        ef = adjusted_exit_features.copy()
        ef["date"] = pd.to_datetime(ef["date"], errors="coerce").dt.normalize()
        ef["stock_id"] = ef["stock_id"].astype(str)
        self.exit_features = {
            (pd.Timestamp(row.date).date(), str(row.stock_id)): row
            for row in ef.itertuples(index=False)
        }

        self.open_ca: dict[date, list[HistoricalCorporateActionInstruction]] = {}
        self.close_ca: dict[date, list[HistoricalCorporateActionInstruction]] = {}
        for item in corporate_actions:
            day = self.calendar.map_effective_date(item.event.effective_at)
            target = self.close_ca if item.apply_at_close else self.open_ca
            target.setdefault(day, []).append(item)
        for mapping in (self.open_ca, self.close_ca):
            for day in mapping:
                mapping[day].sort(key=lambda x: x.event.event_id)

    def _settlement_due(self, session_index: int) -> datetime:
        target = session_index + self.execution_settings.settlement_lag_sessions
        if target < len(self.sessions):
            return datetime.combine(self.sessions[target], datetime.min.time())
        return datetime.combine(self.sessions[-1], datetime.min.time()) + timedelta(
            days=self.execution_settings.settlement_lag_sessions + 7
        )

    @staticmethod
    def _position_tickers(portfolio: PortfolioEngine) -> tuple[str, ...]:
        return tuple(
            sorted(
                ticker
                for ticker, position in portfolio.positions.positions.items()
                if position.quantity > 0
            )
        )

    @staticmethod
    def _ca_cash_total(portfolio: PortfolioEngine) -> float:
        ca = portfolio.corporate_actions
        items = [
            *ca.dividend_receivables.values(),
            *ca.completed_dividends.values(),
            *ca.cash_entitlement_receivables.values(),
            *ca.completed_cash_entitlements.values(),
        ]
        return float(sum(float(x.amount) for x in items))

    def _apply_ca(
        self,
        *,
        portfolio: PortfolioEngine,
        item: HistoricalCorporateActionInstruction,
        applied_at: datetime,
    ) -> dict[str, object]:
        event = item.event
        position = portfolio.positions.positions.get(str(event.ticker))
        opening_shares = 0.0 if position is None else float(position.quantity)
        economic_at = max(applied_at, item.applied_at)

        if event.cash_per_share is not None:
            if event.event_type is CorporateActionType.CASH_DIVIDEND:
                portfolio.corporate_actions.accrue_cash_dividend(
                    event=event,
                    shares_entitled=opening_shares,
                    accrued_at=economic_at,
                )
            else:
                if not item.component:
                    raise ValueError(f"cash component missing for {event.event_id}")
                if item.cash_share_basis_mode is CashEntitlementBasis.OPENING_POSITION:
                    shares_entitled = opening_shares
                else:
                    if item.cash_share_basis is None:
                        raise ValueError(
                            f"cash_share_basis missing for {event.event_id}"
                        )
                    shares_entitled = float(item.cash_share_basis)
                portfolio.corporate_actions.accrue_cash_entitlement(
                    event=event,
                    shares_entitled=shares_entitled,
                    accrued_at=economic_at,
                    component=item.component,
                )

        if event.share_multiplier is not None:
            portfolio.corporate_actions.apply_share_multiplier(
                event=event,
                positions=portfolio.positions,
                applied_at=economic_at,
            )

        transformed = False
        if item.successor_ticker is not None:
            if item.successor_multiplier is None:
                raise ValueError(
                    f"successor_multiplier missing for {event.event_id}"
                )
            portfolio.corporate_actions.convert_security(
                event=event,
                positions=portfolio.positions,
                to_ticker=str(item.successor_ticker),
                quantity_multiplier=float(item.successor_multiplier),
                applied_at=economic_at,
            )
            transformed = True

        if item.successor_legs:
            portfolio.corporate_actions.convert_security_composite(
                event=event,
                positions=portfolio.positions,
                legs=item.successor_legs,
                cash_value_weight=float(item.cash_value_weight),
                applied_at=economic_at,
            )
            transformed = True

        cash_exit_price = None
        if item.extinguish_position:
            portfolio.corporate_actions.extinguish_position(
                event=event,
                positions=portfolio.positions,
                applied_at=economic_at,
            )
            if event.cash_per_share is not None:
                cash_exit_price = float(event.cash_per_share)

        return {
            "transformed": transformed,
            "extinguished": item.extinguish_position,
            "component": item.component,
            "cash_exit_price": cash_exit_price,
            "unverified_terminal": item.component == "UNVERIFIED_TERMINAL_CASHOUT",
        }

    def _pivot_entry_raw(
        self,
        *,
        ticker: str,
        signal_day: date,
        entry_day: date,
        pivot_adjusted: float,
        adjusted_signal_close: float,
    ) -> tuple[float | None, str | None]:
        if (
            not math.isfinite(float(pivot_adjusted))
            or not math.isfinite(float(adjusted_signal_close))
            or float(pivot_adjusted) <= 0
            or float(adjusted_signal_close) <= 0
        ):
            return None, "PIVOT_ADJUSTED_INVALID"

        raw_signal = self.market_data.resolve(
            ticker=ticker,
            session_date=signal_day,
            side="sell",
            use=PriceUse.MARK,
            field="close",
        )
        if (
            raw_signal.availability is not ExecutionAvailability.EXECUTABLE
            or raw_signal.price is None
        ):
            return None, "PIVOT_RAW_SIGNAL_CLOSE_UNAVAILABLE"

        pivot_raw = (
            float(pivot_adjusted)
            * float(raw_signal.price)
            / float(adjusted_signal_close)
        )
        for item in self.open_ca.get(entry_day, ()):
            if str(item.event.ticker) != str(ticker):
                continue
            if (
                item.successor_ticker is not None
                or item.successor_legs
                or item.extinguish_position
            ):
                return None, "ENTRY_DAY_TERMINAL_EVENT"
            cash = float(item.event.cash_per_share or 0.0)
            multiplier = float(item.event.share_multiplier or 1.0)
            if multiplier <= 0:
                return None, "PIVOT_CA_MULTIPLIER_INVALID"
            pivot_raw = (pivot_raw - cash) / multiplier
            if not math.isfinite(pivot_raw) or pivot_raw <= 0:
                return None, "PIVOT_RAW_CONVERSION_INVALID"
        return float(pivot_raw), None

    def _make_execution(self, portfolio: PortfolioEngine) -> CanonicalExecutionService:
        return CanonicalExecutionService(
            market_data=self.market_data,
            fill_factory=self.fill_factory,
            portfolio=portfolio,
        )

    def _normalised_quantity(self, *, raw_open: float) -> float:
        unit_exec = self.fill_factory.slippage_model.execution_price(
            side="buy",
            quantity=1.0,
            reference_price=float(raw_open),
        )
        unit_fee = self.fill_factory.fee_model.fee(
            side="buy",
            quantity=1.0,
            price=unit_exec,
        )
        unit_cost = unit_exec + unit_fee
        q = self.execution_settings.normalized_initial_notional / unit_cost
        return math.nextafter(float(q), 0.0)

    def _trade_result(
        self,
        *,
        config_id: str,
        trade_id: str,
        ticker: str,
        signal_day: date,
        entry_day: date,
        exit_day: date,
        entry_fill,
        exit_fill,
        exit_reason: str,
        entry_raw_open: float,
        exit_raw_open: float | None,
        portfolio: PortfolioEngine,
        entry_investment: float,
        holding_sessions: int,
        terminal_unverified: bool,
        blocked_exit_attempts: int,
        exit_price_override: float | None = None,
    ) -> dict[str, object]:
        projected = float(portfolio.cash.projected_cash)
        pnl = projected - self.execution_settings.normalized_initial_notional
        net_return = pnl / float(entry_investment)
        buy_slippage = float(entry_fill.quantity) * (
            float(entry_fill.price) - float(entry_raw_open)
        )
        sell_slippage = 0.0
        if exit_fill is not None and exit_raw_open is not None:
            sell_slippage = float(exit_fill.quantity) * (
                float(exit_raw_open) - float(exit_fill.price)
            )
        explicit_cost = float(entry_fill.fees) + (
            0.0 if exit_fill is None else float(exit_fill.fees)
        )
        exit_price = (
            float(exit_fill.price)
            if exit_fill is not None
            else (
                None if exit_price_override is None else float(exit_price_override)
            )
        )
        return {
            "config_id": config_id,
            "trade_id": trade_id,
            "stock_id": ticker,
            "signal_date": signal_day.isoformat(),
            "entry_date": entry_day.isoformat(),
            "entry_price": float(entry_fill.price),
            "exit_date": exit_day.isoformat(),
            "exit_price": exit_price,
            "exit_reason": exit_reason,
            "entry_investment": float(entry_investment),
            "buy_fee": float(entry_fill.fees),
            "sell_fee_and_tax": (
                0.0 if exit_fill is None else float(exit_fill.fees)
            ),
            "buy_slippage_cost": buy_slippage,
            "sell_slippage_cost": sell_slippage,
            "total_cost": explicit_cost + buy_slippage + sell_slippage,
            "ca_entitlement": self._ca_cash_total(portfolio),
            "net_return": net_return,
            "holding_days": (exit_day - entry_day).days,
            "holding_sessions": holding_sessions,
            "blocked_exit_attempts": blocked_exit_attempts,
            "terminal_unverified": bool(terminal_unverified),
            "adjustment_method": self.execution_settings.adjustment_method,
        }

    def _simulate_entry(
        self,
        *,
        config_id: str,
        trade_sequence: int,
        candidate: dict[str, object],
    ) -> dict[str, object]:
        ticker = str(candidate["stock_id"])
        signal_day = pd.Timestamp(candidate["signal_date"]).date()
        signal_idx = self.session_index.get(signal_day)
        if signal_idx is None or signal_idx + 1 >= len(self.sessions):
            return {"status": "UNFILLED", "reason": "NO_NEXT_E1_SESSION"}
        entry_idx = signal_idx + 1
        entry_day = self.sessions[entry_idx]

        pivot_raw, pivot_error = self._pivot_entry_raw(
            ticker=ticker,
            signal_day=signal_day,
            entry_day=entry_day,
            pivot_adjusted=float(candidate["pivot_adjusted"]),
            adjusted_signal_close=float(candidate["adjusted_signal_close"]),
        )
        if pivot_error is not None or pivot_raw is None:
            return {"status": "UNFILLED", "reason": pivot_error}

        entry_decision = self.market_data.resolve(
            ticker=ticker,
            session_date=entry_day,
            side="buy",
            use=PriceUse.ENTRY,
            field="open",
        )
        if (
            entry_decision.availability is not ExecutionAvailability.EXECUTABLE
            or entry_decision.price is None
        ):
            return {
                "status": "UNFILLED",
                "reason": f"ENTRY_{entry_decision.reason}",
            }

        simulated_entry = self.fill_factory.slippage_model.execution_price(
            side="buy",
            quantity=1.0,
            reference_price=float(entry_decision.price),
        )
        chase_limit = float(pivot_raw) * self.execution_settings.chase_multiple
        if simulated_entry > chase_limit:
            return {
                "status": "CHASE_REJECT",
                "reason": "CHASE_LIMIT_EXCEEDED",
                "entry_day": entry_day,
                "pivot_entry_raw": pivot_raw,
                "simulated_entry_price": simulated_entry,
                "chase_limit": chase_limit,
            }

        portfolio = PortfolioEngine(
            opening_cash=self.execution_settings.normalized_initial_notional
        )
        execution = self._make_execution(portfolio)
        quantity = self._normalised_quantity(raw_open=float(entry_decision.price))
        trade_id = f"{config_id}:{ticker}:{signal_day.isoformat()}:{trade_sequence}"
        start = datetime.combine(entry_day, datetime.min.time())
        intent = OrderIntent(
            intent_id=f"entry:{trade_id}",
            ticker=ticker,
            side="buy",
            quantity=quantity,
            created_at=start,
            rationale="VCP round1 next-common-open entry",
        )
        try:
            executed = execution.execute(
                intent=intent,
                signal=self.signal,
                order_id=f"order:entry:{trade_id}",
                fill_id=f"fill:entry:{trade_id}",
                submitted_at=start,
                session_date=entry_day,
                use=PriceUse.ENTRY,
                field="open",
                settlement=SettlementInstruction(
                    settlement_id=f"settle:entry:{trade_id}",
                    due_at=self._settlement_due(entry_idx),
                ),
            )
        except NotExecutableError as exc:
            return {"status": "UNFILLED", "reason": f"ENTRY_EXECUTE:{exc}"}

        entry_fill = executed.fill
        entry_investment = (
            float(entry_fill.quantity) * float(entry_fill.price)
            + float(entry_fill.fees)
        )
        pending_exit: str | None = None
        atr_trail: float | None = None
        high_watermark: float | None = None
        transformed = False
        terminal_unverified = False
        blocked_exit_attempts = 0

        for day_idx in range(entry_idx, len(self.sessions)):
            day = self.sessions[day_idx]
            day_start = datetime.combine(day, datetime.min.time())

            if day_idx > entry_idx:
                for item in self.open_ca.get(day, ()):
                    if str(item.event.ticker) not in self._position_tickers(portfolio):
                        continue
                    ca_result = self._apply_ca(
                        portfolio=portfolio,
                        item=item,
                        applied_at=day_start,
                    )
                    transformed |= bool(ca_result["transformed"])
                    terminal_unverified |= bool(ca_result["unverified_terminal"])
                    if not self._position_tickers(portfolio):
                        return {
                            "status": "CLOSED",
                            "flat_at_open": True,
                            "entry_day": entry_day,
                            "exit_day": day,
                            "trade": self._trade_result(
                                config_id=config_id,
                                trade_id=trade_id,
                                ticker=ticker,
                                signal_day=signal_day,
                                entry_day=entry_day,
                                exit_day=day,
                                entry_fill=entry_fill,
                                exit_fill=None,
                                exit_reason=(
                                    "TERMINAL:"
                                    + str(ca_result["component"] or "EXTINGUISHMENT")
                                ),
                                entry_raw_open=float(entry_decision.price),
                                exit_raw_open=None,
                                portfolio=portfolio,
                                entry_investment=entry_investment,
                                holding_sessions=day_idx - entry_idx + 1,
                                terminal_unverified=terminal_unverified,
                                blocked_exit_attempts=blocked_exit_attempts,
                                exit_price_override=ca_result["cash_exit_price"],
                            ),
                        }

            if pending_exit is not None and not transformed:
                tickers = self._position_tickers(portfolio)
                if len(tickers) == 1:
                    current_ticker = tickers[0]
                    exit_decision = self.market_data.resolve(
                        ticker=current_ticker,
                        session_date=day,
                        side="sell",
                        use=PriceUse.EXIT,
                        field="open",
                    )
                    if (
                        exit_decision.availability is ExecutionAvailability.EXECUTABLE
                        and exit_decision.price is not None
                    ):
                        position = portfolio.positions.positions[current_ticker]
                        intent = OrderIntent(
                            intent_id=f"exit:{trade_id}:{day.isoformat()}",
                            ticker=current_ticker,
                            side="sell",
                            quantity=float(position.quantity),
                            created_at=day_start,
                            rationale=f"VCP round1 close-confirmed {pending_exit}",
                        )
                        try:
                            out = execution.execute(
                                intent=intent,
                                signal=self.signal,
                                order_id=f"order:exit:{trade_id}:{day.isoformat()}",
                                fill_id=f"fill:exit:{trade_id}:{day.isoformat()}",
                                submitted_at=day_start,
                                session_date=day,
                                use=PriceUse.EXIT,
                                field="open",
                                settlement=SettlementInstruction(
                                    settlement_id=(
                                        f"settle:exit:{trade_id}:{day.isoformat()}"
                                    ),
                                    due_at=self._settlement_due(day_idx),
                                ),
                            )
                        except NotExecutableError:
                            blocked_exit_attempts += 1
                        else:
                            return {
                                "status": "CLOSED",
                                "flat_at_open": True,
                                "entry_day": entry_day,
                                "exit_day": day,
                                "trade": self._trade_result(
                                    config_id=config_id,
                                    trade_id=trade_id,
                                    ticker=ticker,
                                    signal_day=signal_day,
                                    entry_day=entry_day,
                                    exit_day=day,
                                    entry_fill=entry_fill,
                                    exit_fill=out.fill,
                                    exit_reason=pending_exit,
                                    entry_raw_open=float(entry_decision.price),
                                    exit_raw_open=float(exit_decision.price),
                                    portfolio=portfolio,
                                    entry_investment=entry_investment,
                                    holding_sessions=day_idx - entry_idx + 1,
                                    terminal_unverified=terminal_unverified,
                                    blocked_exit_attempts=blocked_exit_attempts,
                                ),
                            }
                    else:
                        blocked_exit_attempts += 1

            if not transformed and pending_exit is None:
                feature = self.exit_features.get((day, ticker))
                if feature is not None:
                    adj_high = float(feature.adjusted_high)
                    adj_close = float(feature.adjusted_close)
                    if (
                        math.isfinite(adj_high)
                        and math.isfinite(adj_close)
                        and adj_high > 0
                        and adj_close > 0
                    ):
                        high_watermark = (
                            adj_high
                            if high_watermark is None
                            else max(high_watermark, adj_high)
                        )
                        atr = float(feature.atr)
                        if math.isfinite(atr) and high_watermark is not None:
                            atr_trail = update_atr_trail(
                                atr_trail,
                                high_watermark=high_watermark,
                                atr=atr,
                                multiplier=self.exit_settings.atr_multiplier,
                            )
                        d_ma = float(feature.d_ma)
                        pending_exit = close_exit_reason(
                            close=adj_close,
                            atr_trail=atr_trail,
                            d_ma=d_ma,
                        )

            for item in self.close_ca.get(day, ()):
                if str(item.event.ticker) not in self._position_tickers(portfolio):
                    continue
                ca_result = self._apply_ca(
                    portfolio=portfolio,
                    item=item,
                    applied_at=datetime.combine(day, datetime.max.time()),
                )
                transformed |= bool(ca_result["transformed"])
                terminal_unverified |= bool(ca_result["unverified_terminal"])
                if not self._position_tickers(portfolio):
                    return {
                        "status": "CLOSED",
                        "flat_at_open": False,
                        "entry_day": entry_day,
                        "exit_day": day,
                        "trade": self._trade_result(
                            config_id=config_id,
                            trade_id=trade_id,
                            ticker=ticker,
                            signal_day=signal_day,
                            entry_day=entry_day,
                            exit_day=day,
                            entry_fill=entry_fill,
                            exit_fill=None,
                            exit_reason=(
                                "TERMINAL:"
                                + str(ca_result["component"] or "EXTINGUISHMENT")
                            ),
                            entry_raw_open=float(entry_decision.price),
                            exit_raw_open=None,
                            portfolio=portfolio,
                            entry_investment=entry_investment,
                            holding_sessions=day_idx - entry_idx + 1,
                            terminal_unverified=terminal_unverified,
                            blocked_exit_attempts=blocked_exit_attempts,
                            exit_price_override=ca_result["cash_exit_price"],
                        ),
                    }

        current = self._position_tickers(portfolio)
        return {
            "status": "OPEN",
            "entry_day": entry_day,
            "exit_day": None,
            "open": {
                "config_id": config_id,
                "trade_id": trade_id,
                "stock_id": ticker,
                "signal_date": signal_day.isoformat(),
                "entry_date": entry_day.isoformat(),
                "entry_price": float(entry_fill.price),
                "held_days_at_period_end": (self.sessions[-1] - entry_day).days,
                "held_sessions_at_period_end": len(self.sessions) - entry_idx,
                "pending_exit_state": (
                    pending_exit
                    if pending_exit is not None
                    else (
                        "TERMINAL_SUCCESSOR_POSITION"
                        if transformed
                        else "NONE"
                    )
                ),
                "current_tickers": ";".join(current),
                "ca_entitlement": self._ca_cash_total(portfolio),
                "terminal_unverified": bool(terminal_unverified),
                "blocked_exit_attempts": blocked_exit_attempts,
                "adjustment_method": self.execution_settings.adjustment_method,
            },
        }

    def simulate_config(
        self,
        *,
        config_id: str,
        candidates: pd.DataFrame,
    ) -> ConfigTradeSimulation:
        required = {
            "signal_date",
            "stock_id",
            "pivot_adjusted",
            "adjusted_signal_close",
        }
        missing = required - set(candidates.columns)
        if missing:
            raise ValueError(f"VCP candidates missing columns: {sorted(missing)}")

        work = candidates.copy()
        work["signal_date"] = pd.to_datetime(
            work["signal_date"], errors="coerce"
        ).dt.normalize()
        work["stock_id"] = work["stock_id"].astype(str)
        if work[list(required)].isna().any(axis=1).any():
            raise ValueError("VCP candidates contain null required fields")
        if work.duplicated(["signal_date", "stock_id"]).any():
            raise ValueError("VCP candidates contain duplicate logical keys")
        work = work.sort_values(["stock_id", "signal_date"], kind="stable")

        trades: list[dict[str, object]] = []
        opens: list[dict[str, object]] = []
        entry_count = 0
        ignored = 0
        chase_reject = 0
        other_unfilled = 0
        unfilled_reasons: dict[str, int] = {}
        unverified_terminal = 0
        sequence = 0

        for ticker, group in work.groupby("stock_id", sort=False):
            records = group.to_dict("records")
            i = 0
            while i < len(records):
                candidate = records[i]
                sequence += 1
                result = self._simulate_entry(
                    config_id=config_id,
                    trade_sequence=sequence,
                    candidate=candidate,
                )
                status = str(result["status"])
                if status == "CHASE_REJECT":
                    chase_reject += 1
                    i += 1
                    continue
                if status == "UNFILLED":
                    other_unfilled += 1
                    reason = str(result.get("reason") or "UNSPECIFIED")
                    unfilled_reasons[reason] = unfilled_reasons.get(reason, 0) + 1
                    i += 1
                    continue

                entry_count += 1
                entry_day = result["entry_day"]
                if status == "CLOSED":
                    trade = result["trade"]
                    trades.append(trade)
                    unverified_terminal += int(bool(trade["terminal_unverified"]))
                    exit_day = result["exit_day"]
                    flat_at_open = bool(result["flat_at_open"])
                    j = i + 1
                    while j < len(records):
                        signal_day = pd.Timestamp(records[j]["signal_date"]).date()
                        held = (
                            entry_day <= signal_day < exit_day
                            if flat_at_open
                            else entry_day <= signal_day <= exit_day
                        )
                        if held:
                            ignored += 1
                            j += 1
                            continue
                        break
                    i = j
                    continue

                open_row = result["open"]
                opens.append(open_row)
                unverified_terminal += int(bool(open_row["terminal_unverified"]))
                for j in range(i + 1, len(records)):
                    signal_day = pd.Timestamp(records[j]["signal_date"]).date()
                    if signal_day >= entry_day:
                        ignored += 1
                break

        return ConfigTradeSimulation(
            trades=pd.DataFrame(trades),
            open_positions=pd.DataFrame(opens),
            signal_count=int(len(work)),
            entry_count=entry_count,
            ignored_while_holding=ignored,
            chase_reject_count=chase_reject,
            other_unfilled_count=other_unfilled,
            unfilled_reason_counts=dict(sorted(unfilled_reasons.items())),
            unverified_terminal_trade_count=unverified_terminal,
        )
