from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from astraquant.portfolio.engine import PortfolioEngine
from astraquant.portfolio.models import Fill
from astraquant.portfolio.trade_reconstruction import (
    TradeReconstructionResult,
    reconstruct_fifo_trades,
)


@dataclass(frozen=True)
class ClosedTrade:
    source_fill_id: str
    entry_ticker: str
    entry_at: object
    exit_at: object
    realized_pnl: float
    entry_cost: float
    return_on_cost: float
    holding_days: float
    exit_components: tuple[str, ...] = ()


@dataclass(frozen=True)
class TradeStatistics:
    n: int
    win_rate: float
    average_win: float
    average_loss: float
    payoff_ratio: float
    expectancy: float
    average_holding_days: float


@dataclass(frozen=True)
class TradeReport:
    reconstruction: TradeReconstructionResult
    closed_trades: tuple[ClosedTrade, ...]
    statistics: TradeStatistics


def portfolio_fills(portfolio: PortfolioEngine) -> tuple[Fill, ...]:
    fills: dict[str, Fill] = {}
    for order in portfolio.orders.orders.values():
        for fill in order.fills:
            fills[fill.fill_id] = fill
    return tuple(sorted(fills.values(), key=lambda x: (x.filled_at, x.fill_id)))


def reconstruct_portfolio_trades(portfolio: PortfolioEngine) -> TradeReconstructionResult:
    ca = portfolio.corporate_actions
    entitlements = {
        **ca.cash_entitlement_receivables,
        **ca.completed_cash_entitlements,
    }
    return reconstruct_fifo_trades(
        fills=portfolio_fills(portfolio),
        share_mutations=ca.share_mutations.values(),
        security_conversions=ca.security_conversions.values(),
        composite_conversions=ca.composite_conversions.values(),
        position_extinguishments=ca.position_extinguishments.values(),
        cash_entitlements=entitlements.values(),
    )


def aggregate_closed_trades(
    reconstruction: TradeReconstructionResult,
) -> tuple[ClosedTrade, ...]:
    open_sources = {lot.source_fill_id for lot in reconstruction.open_lots}
    grouped: dict[str, list] = {}
    for lot in reconstruction.closed_lots:
        grouped.setdefault(lot.source_fill_id, []).append(lot)

    trades: list[ClosedTrade] = []
    for source_fill_id, lots in sorted(grouped.items()):
        if source_fill_id in open_sources:
            continue
        entry_cost = sum(float(x.entry_price_with_fees) * float(x.quantity) for x in lots)
        realized = sum(float(x.realized_pnl) for x in lots)
        entry_at = min(x.entry_at for x in lots)
        exit_at = max(x.exit_at for x in lots)
        trades.append(
            ClosedTrade(
                source_fill_id=source_fill_id,
                entry_ticker=str(lots[0].entry_ticker),
                entry_at=entry_at,
                exit_at=exit_at,
                realized_pnl=realized,
                entry_cost=entry_cost,
                return_on_cost=(realized / entry_cost if entry_cost > 0 else float("nan")),
                holding_days=float((exit_at.date() - entry_at.date()).days),
                exit_components=tuple(
                    sorted(
                        {
                            str(x.exit_component)
                            for x in lots
                            if x.exit_component is not None
                        }
                    )
                ),
            )
        )
    return tuple(trades)


def summarize_closed_trades(trades: Iterable[ClosedTrade]) -> TradeStatistics:
    rows = tuple(trades)
    returns = np.asarray([x.return_on_cost for x in rows], dtype=float)
    returns = returns[np.isfinite(returns)]
    wins = returns[returns > 0]
    losses = returns[returns < 0]
    avg_win = float(wins.mean()) if len(wins) else float("nan")
    avg_loss = float(losses.mean()) if len(losses) else float("nan")
    payoff = (
        avg_win / abs(avg_loss)
        if len(wins) and len(losses) and avg_loss != 0
        else float("nan")
    )
    holding = np.asarray([x.holding_days for x in rows], dtype=float)
    return TradeStatistics(
        n=int(len(returns)),
        win_rate=float((returns > 0).mean()) if len(returns) else float("nan"),
        average_win=avg_win,
        average_loss=avg_loss,
        payoff_ratio=payoff,
        expectancy=float(returns.mean()) if len(returns) else float("nan"),
        average_holding_days=float(holding.mean()) if len(holding) else float("nan"),
    )


def build_trade_report(portfolio: PortfolioEngine) -> TradeReport:
    reconstruction = reconstruct_portfolio_trades(portfolio)
    trades = aggregate_closed_trades(reconstruction)
    return TradeReport(
        reconstruction=reconstruction,
        closed_trades=trades,
        statistics=summarize_closed_trades(trades),
    )
