from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from astraquant.portfolio.models import (
    Fill,
    PositionSecurityConversion,
    PositionShareMutation,
)


@dataclass(frozen=True)
class ReconstructedOpenLot:
    ticker: str
    quantity: float
    unit_cost: float
    opened_at: datetime
    source_fill_id: str


@dataclass(frozen=True)
class ReconstructedClosedLot:
    entry_ticker: str
    exit_ticker: str
    quantity: float
    entry_price_with_fees: float
    exit_price: float
    entry_at: datetime
    exit_at: datetime
    source_fill_id: str
    exit_fill_id: str
    allocated_exit_fees: float
    realized_pnl: float

    @property
    def return_on_cost(self) -> float:
        cost = self.entry_price_with_fees * self.quantity
        return self.realized_pnl / cost if cost > 0 else float("nan")


@dataclass(frozen=True)
class TradeReconstructionResult:
    closed_lots: tuple[ReconstructedClosedLot, ...]
    open_lots: tuple[ReconstructedOpenLot, ...]


@dataclass
class _Lot:
    ticker: str
    quantity: float
    unit_cost: float
    opened_at: datetime
    source_fill_id: str
    entry_ticker: str
    sequence: int


def reconstruct_fifo_trades(
    *,
    fills: Iterable[Fill],
    share_mutations: Iterable[PositionShareMutation] = (),
    security_conversions: Iterable[PositionSecurityConversion] = (),
    tolerance: float = 1e-9,
) -> TradeReconstructionResult:
    """Reconstruct FIFO lots from canonical fills plus exogenous share events.

    Share mutations rescale open-lot quantity and per-share cost without changing
    total cost basis. Successor-security conversions move the original FIFO lots
    to the successor ticker, preserving their original acquisition timestamp and
    cost basis. This mirrors canonical portfolio accounting instead of treating
    fills as the only source of position-state changes.
    """

    events: list[tuple[datetime, int, str, object]] = []
    for mutation in share_mutations:
        events.append((mutation.effective_at, 0, mutation.event_id, mutation))
    for conversion in security_conversions:
        events.append((conversion.effective_at, 1, conversion.event_id, conversion))
    for fill in fills:
        events.append((fill.filled_at, 2, fill.fill_id, fill))
    events.sort(key=lambda x: (x[0], x[1], x[2]))

    queues: dict[str, list[_Lot]] = {}
    closed: list[ReconstructedClosedLot] = []
    sequence = 0

    for _, _, _, event in events:
        if isinstance(event, PositionShareMutation):
            queue = queues.get(str(event.ticker), [])
            for lot in queue:
                lot.quantity *= float(event.share_multiplier)
                lot.unit_cost /= float(event.share_multiplier)
            continue

        if isinstance(event, PositionSecurityConversion):
            source_ticker = str(event.from_ticker)
            target_ticker = str(event.to_ticker)
            moved = queues.pop(source_ticker, [])
            for lot in moved:
                lot.ticker = target_ticker
                lot.quantity *= float(event.quantity_multiplier)
                lot.unit_cost /= float(event.quantity_multiplier)
            if moved:
                target = queues.setdefault(target_ticker, [])
                target.extend(moved)
                target.sort(key=lambda lot: (lot.opened_at, lot.sequence))
            continue

        fill = event
        ticker = str(fill.ticker)
        side = fill.side.lower()
        if fill.quantity <= 0 or fill.price <= 0:
            raise ValueError(f"nonpositive fill economics: {fill.fill_id}")

        if side == "buy":
            unit_cost = (
                float(fill.price)
                + float(fill.fees) / float(fill.quantity)
            )
            queues.setdefault(ticker, []).append(
                _Lot(
                    ticker=ticker,
                    quantity=float(fill.quantity),
                    unit_cost=unit_cost,
                    opened_at=fill.filled_at,
                    source_fill_id=fill.fill_id,
                    entry_ticker=ticker,
                    sequence=sequence,
                )
            )
            sequence += 1
            continue

        if side != "sell":
            raise ValueError(f"unsupported fill side: {fill.side}")

        queue = queues.setdefault(ticker, [])
        remaining = float(fill.quantity)
        if sum(lot.quantity for lot in queue) + tolerance < remaining:
            raise ValueError(
                f"FIFO reconstruction cannot match sell {fill.fill_id}: "
                f"ticker={ticker} sell={remaining} open={sum(lot.quantity for lot in queue)}"
            )

        fee_per_share = float(fill.fees) / float(fill.quantity)
        while remaining > tolerance:
            lot = queue[0]
            matched = min(lot.quantity, remaining)
            exit_fees = fee_per_share * matched
            realized = (
                (float(fill.price) - lot.unit_cost) * matched
                - exit_fees
            )
            closed.append(
                ReconstructedClosedLot(
                    entry_ticker=lot.entry_ticker,
                    exit_ticker=ticker,
                    quantity=matched,
                    entry_price_with_fees=lot.unit_cost,
                    exit_price=float(fill.price),
                    entry_at=lot.opened_at,
                    exit_at=fill.filled_at,
                    source_fill_id=lot.source_fill_id,
                    exit_fill_id=fill.fill_id,
                    allocated_exit_fees=exit_fees,
                    realized_pnl=realized,
                )
            )
            lot.quantity -= matched
            remaining -= matched
            if lot.quantity <= tolerance:
                queue.pop(0)

    open_lots = tuple(
        ReconstructedOpenLot(
            ticker=ticker,
            quantity=lot.quantity,
            unit_cost=lot.unit_cost,
            opened_at=lot.opened_at,
            source_fill_id=lot.source_fill_id,
        )
        for ticker in sorted(queues)
        for lot in queues[ticker]
        if lot.quantity > tolerance
    )
    return TradeReconstructionResult(
        closed_lots=tuple(closed),
        open_lots=open_lots,
    )
