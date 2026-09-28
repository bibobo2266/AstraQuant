from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from astraquant.portfolio.models import (
    Fill,
    PositionCompositeConversion,
    PositionExtinguishment,
    PositionSecurityConversion,
    PositionShareMutation,
)
from astraquant.portfolio.corporate_actions import CorporateActionCashReceivable


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
    exit_fill_id: str | None
    allocated_exit_fees: float
    realized_pnl: float
    exit_event_id: str | None = None
    exit_kind: str = "MARKET_FILL"

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
    composite_conversions: Iterable[PositionCompositeConversion] = (),
    position_extinguishments: Iterable[PositionExtinguishment] = (),
    cash_entitlements: Iterable[CorporateActionCashReceivable] = (),
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
    for conversion in composite_conversions:
        events.append((conversion.effective_at, 1, conversion.event_id, conversion))
    entitlement_by_event = {x.event_id: x for x in cash_entitlements}
    for extinguishment in position_extinguishments:
        events.append((extinguishment.effective_at, 2, extinguishment.event_id, extinguishment))
    for fill in fills:
        events.append((fill.filled_at, 3, fill.fill_id, fill))
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

        if isinstance(event, PositionCompositeConversion):
            source_ticker = str(event.from_ticker)
            moved = queues.pop(source_ticker, [])
            if not moved:
                continue

            for lot in moved:
                original_quantity = float(lot.quantity)
                original_unit_cost = float(lot.unit_cost)

                if event.cash_per_source_share > 0:
                    cash_basis_per_share = original_unit_cost * event.cash_value_weight
                    realized = (
                        float(event.cash_per_source_share) - cash_basis_per_share
                    ) * original_quantity
                    closed.append(
                        ReconstructedClosedLot(
                            entry_ticker=lot.entry_ticker,
                            exit_ticker=source_ticker,
                            quantity=original_quantity,
                            entry_price_with_fees=cash_basis_per_share,
                            exit_price=float(event.cash_per_source_share),
                            entry_at=lot.opened_at,
                            exit_at=event.effective_at,
                            source_fill_id=lot.source_fill_id,
                            exit_fill_id=None,
                            allocated_exit_fees=0.0,
                            realized_pnl=realized,
                            exit_event_id=event.event_id,
                            exit_kind="COMPOSITE_CASH_CONSIDERATION",
                        )
                    )

                for leg in event.legs:
                    new_quantity = original_quantity * float(leg.quantity_multiplier)
                    new_unit_cost = (
                        original_unit_cost * float(leg.value_weight)
                        / float(leg.quantity_multiplier)
                    )
                    target = queues.setdefault(str(leg.to_ticker), [])
                    target.append(
                        _Lot(
                            ticker=str(leg.to_ticker),
                            quantity=new_quantity,
                            unit_cost=new_unit_cost,
                            opened_at=lot.opened_at,
                            source_fill_id=lot.source_fill_id,
                            entry_ticker=lot.entry_ticker,
                            sequence=lot.sequence,
                        )
                    )

            for leg in event.legs:
                queues[str(leg.to_ticker)].sort(
                    key=lambda lot: (lot.opened_at, lot.sequence)
                )
            continue

        if isinstance(event, PositionExtinguishment):
            ticker = str(event.ticker)
            queue = queues.setdefault(ticker, [])
            entitlement = entitlement_by_event.get(event.event_id)
            open_quantity = sum(lot.quantity for lot in queue)
            if open_quantity <= tolerance:
                continue
            if entitlement is None:
                raise ValueError(
                    f"cash extinguishment {event.event_id} has open FIFO lots but no cash entitlement"
                )
            if abs(float(entitlement.shares_entitled) - open_quantity) > tolerance:
                raise ValueError(
                    f"cash extinguishment {event.event_id} entitlement/open-lot mismatch: "
                    f"entitled={entitlement.shares_entitled} open={open_quantity}"
                )
            exit_price = float(entitlement.cash_per_share)
            while queue:
                lot = queue.pop(0)
                realized = (exit_price - lot.unit_cost) * lot.quantity
                closed.append(
                    ReconstructedClosedLot(
                        entry_ticker=lot.entry_ticker,
                        exit_ticker=ticker,
                        quantity=lot.quantity,
                        entry_price_with_fees=lot.unit_cost,
                        exit_price=exit_price,
                        entry_at=lot.opened_at,
                        exit_at=event.effective_at,
                        source_fill_id=lot.source_fill_id,
                        exit_fill_id=None,
                        allocated_exit_fees=0.0,
                        realized_pnl=realized,
                        exit_event_id=event.event_id,
                        exit_kind="CASH_EXTINGUISHMENT",
                    )
                )
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
