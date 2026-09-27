from __future__ import annotations

from .models import Fill, Position, PositionShareMutation


class PortfolioLedger:
    """Position state changes only through fills."""

    def __init__(self) -> None:
        self.positions: dict[str, Position] = {}
        self.applied_share_mutation_ids: set[str] = set()

    def apply_fill(self, fill: Fill) -> Position:
        pos = self.positions.setdefault(fill.ticker, Position(ticker=fill.ticker))
        side = fill.side.lower()

        if side == "buy":
            new_qty = pos.quantity + fill.quantity
            acquisition_cost = (fill.price * fill.quantity) + fill.fees
            pos.avg_cost = (
                (pos.avg_cost * pos.quantity) + acquisition_cost
            ) / new_qty
            pos.quantity = new_qty

        elif side == "sell":
            if fill.quantity > pos.quantity:
                raise ValueError("Cannot sell more than current position")
            pos.realized_pnl += (
                (fill.price - pos.avg_cost) * fill.quantity
            ) - fill.fees
            pos.quantity -= fill.quantity
            if pos.quantity == 0:
                pos.avg_cost = 0.0

        else:
            raise ValueError(f"Unsupported side: {fill.side}")

        pos.fills.append(fill)
        return pos


    def apply_share_mutation(self, mutation: PositionShareMutation) -> Position:
        """Apply an explicit exogenous corporate-action share mutation.

        Signals, recommendations, and decisions still cannot mutate holdings.
        This path exists only for economic corporate actions with an explicit
        share multiplier.
        """

        if mutation.event_id in self.applied_share_mutation_ids:
            raise ValueError(f"duplicate share mutation event id: {mutation.event_id}")

        pos = self.positions.setdefault(
            mutation.ticker,
            Position(ticker=mutation.ticker),
        )
        if pos.quantity < 0:
            raise ValueError("negative positions are unsupported")

        if pos.quantity > 0:
            old_total_cost = pos.avg_cost * pos.quantity
            pos.quantity *= mutation.share_multiplier
            pos.avg_cost = old_total_cost / pos.quantity

        self.applied_share_mutation_ids.add(mutation.event_id)
        return pos
