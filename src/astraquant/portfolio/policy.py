from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from astraquant.execution.market_data import ExecutionAvailability, ExecutionPriceDecision
from astraquant.portfolio.corporate_actions import CorporateActionEvent


class ExitReason(str, Enum):
    STOP = "STOP"
    MAX_HOLD = "MAX_HOLD"


@dataclass(frozen=True)
class PortfolioPolicyConfig:
    position_fraction: float
    max_positions: int
    stop_fraction: float = 0.12
    reentry_gap_sessions: int = 20
    max_hold_sessions: int = 250
    lot_size: int = 1000
    random_seed: int = 0

    def __post_init__(self) -> None:
        if not 0 < self.position_fraction <= 1:
            raise ValueError("position_fraction must be in (0, 1]")
        if self.max_positions <= 0:
            raise ValueError("max_positions must be positive")
        if not 0 < self.stop_fraction < 1:
            raise ValueError("stop_fraction must be in (0, 1)")
        if self.reentry_gap_sessions < 0:
            raise ValueError("reentry_gap_sessions must be non-negative")
        if self.max_hold_sessions <= 0:
            raise ValueError("max_hold_sessions must be positive")
        if self.lot_size <= 0:
            raise ValueError("lot_size must be positive")


@dataclass(frozen=True)
class EntryCandidate:
    ticker: str
    sizing_decision: ExecutionPriceDecision


@dataclass(frozen=True)
class PlannedEntry:
    ticker: str
    quantity: float
    raw_sizing_price: float
    budget: float


@dataclass
class ManagedPosition:
    ticker: str
    quantity: float
    entry_session_index: int
    entry_price: float
    stop_price: float


@dataclass
class PortfolioIntentPolicy:
    config: PortfolioPolicyConfig
    managed_positions: dict[str, ManagedPosition] = field(default_factory=dict)
    last_entry_index: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._rng = np.random.default_rng(self.config.random_seed)

    def eligible_for_reentry(self, ticker: str, session_index: int) -> bool:
        if ticker in self.managed_positions:
            return False
        last = self.last_entry_index.get(ticker)
        if last is None:
            return True
        return session_index - last > self.config.reentry_gap_sessions

    def available_slots(self) -> int:
        return max(0, self.config.max_positions - len(self.managed_positions))

    def plan_entries(
        self,
        *,
        candidates: list[EntryCandidate],
        session_index: int,
        current_nav: float,
        available_cash: float,
    ) -> tuple[list[PlannedEntry], dict[str, str]]:
        """Select and board-lot-size entry candidates.

        Selection is random only when candidates exceed available position slots,
        using the configured deterministic RNG seed.
        """

        if current_nav < 0:
            raise ValueError("current_nav must be non-negative")
        if available_cash < 0:
            raise ValueError("available_cash must be non-negative")

        skipped: dict[str, str] = {}
        eligible: list[EntryCandidate] = []
        for candidate in candidates:
            ticker = str(candidate.ticker)
            if not self.eligible_for_reentry(ticker, session_index):
                skipped[ticker] = "REENTRY_OR_ALREADY_HELD"
                continue
            decision = candidate.sizing_decision
            if (
                decision.availability is not ExecutionAvailability.EXECUTABLE
                or decision.price is None
                or decision.price <= 0
            ):
                skipped[ticker] = "NOT_EXECUTABLE_SIZING"
                continue
            eligible.append(candidate)

        slots = self.available_slots()
        if slots <= 0:
            for candidate in eligible:
                skipped[str(candidate.ticker)] = "NO_POSITION_SLOT"
            return [], skipped

        if len(eligible) > slots:
            chosen_idx = set(
                int(i)
                for i in self._rng.choice(
                    len(eligible),
                    size=slots,
                    replace=False,
                )
            )
            selected = [c for i, c in enumerate(eligible) if i in chosen_idx]
            for i, candidate in enumerate(eligible):
                if i not in chosen_idx:
                    skipped[str(candidate.ticker)] = "CAPACITY_RANDOM_SKIP"
        else:
            selected = eligible

        per_position_budget = current_nav * self.config.position_fraction
        remaining_cash = available_cash
        planned: list[PlannedEntry] = []

        for candidate in selected:
            price = float(candidate.sizing_decision.price)
            budget = min(per_position_budget, remaining_cash)
            lots = int(budget // (price * self.config.lot_size))
            if lots < 1:
                skipped[str(candidate.ticker)] = "BOARD_LOT_UNAFFORDABLE"
                continue

            quantity = float(lots * self.config.lot_size)
            notional = quantity * price
            planned.append(
                PlannedEntry(
                    ticker=str(candidate.ticker),
                    quantity=quantity,
                    raw_sizing_price=price,
                    budget=budget,
                )
            )
            remaining_cash -= notional

        return planned, skipped

    def register_entry(
        self,
        *,
        ticker: str,
        quantity: float,
        fill_price: float,
        session_index: int,
    ) -> ManagedPosition:
        ticker = str(ticker)
        if ticker in self.managed_positions:
            raise ValueError(f"position already managed: {ticker}")
        if quantity <= 0 or fill_price <= 0:
            raise ValueError("quantity and fill_price must be positive")

        state = ManagedPosition(
            ticker=ticker,
            quantity=quantity,
            entry_session_index=session_index,
            entry_price=fill_price,
            stop_price=fill_price * (1 - self.config.stop_fraction),
        )
        self.managed_positions[ticker] = state
        self.last_entry_index[ticker] = session_index
        return state

    def register_exit(self, ticker: str) -> ManagedPosition:
        ticker = str(ticker)
        return self.managed_positions.pop(ticker)

    def max_hold_due(self, ticker: str, session_index: int) -> bool:
        state = self.managed_positions[str(ticker)]
        return session_index - state.entry_session_index >= self.config.max_hold_sessions


    def apply_corporate_action(
        self,
        event: CorporateActionEvent,
    ) -> ManagedPosition | None:
        """Adjust managed stop state for an exogenous economic event.

        The portfolio ledger performs the actual share/cash accounting. This
        method keeps policy state on the same RAW economic coordinate.

        For an event with pre-event cash entitlement c and share multiplier m,
        an economically equivalent post-event stop S' satisfies:

            m * S' + c = S

        therefore S' = (S - c) / m.
        """

        state = self.managed_positions.get(str(event.ticker))
        if state is None:
            return None

        multiplier = event.share_multiplier if event.share_multiplier is not None else 1.0
        cash_component = event.cash_per_share if event.cash_per_share is not None else 0.0
        if multiplier <= 0:
            raise ValueError("share multiplier must be positive")

        if event.share_multiplier is not None:
            state.quantity *= multiplier
            state.entry_price /= multiplier

        state.stop_price = max(
            1e-12,
            (state.stop_price - cash_component) / multiplier,
        )
        return state


    def convert_security(
        self,
        *,
        from_ticker: str,
        to_ticker: str,
        quantity_multiplier: float,
    ) -> ManagedPosition | None:
        """Move managed policy state across an explicit successor-security conversion."""

        from_ticker = str(from_ticker)
        to_ticker = str(to_ticker)
        if quantity_multiplier <= 0:
            raise ValueError("quantity_multiplier must be positive")
        state = self.managed_positions.get(from_ticker)
        if state is None:
            return None
        if to_ticker in self.managed_positions:
            raise ValueError(
                f"cannot convert into already-managed successor: {to_ticker}"
            )

        state = self.managed_positions.pop(from_ticker)
        state.ticker = to_ticker
        state.quantity *= quantity_multiplier
        state.entry_price /= quantity_multiplier
        state.stop_price /= quantity_multiplier
        self.managed_positions[to_ticker] = state

        last = self.last_entry_index.get(from_ticker)
        if last is not None and to_ticker not in self.last_entry_index:
            self.last_entry_index[to_ticker] = last
        return state
