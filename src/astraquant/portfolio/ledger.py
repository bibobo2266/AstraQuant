from __future__ import annotations

from .models import Fill, Position


class PortfolioLedger:
    """Position state changes only through fills."""

    def __init__(self) -> None:
        self.positions: dict[str, Position] = {}

    def apply_fill(self, fill: Fill) -> Position:
        pos = self.positions.setdefault(fill.ticker, Position(ticker=fill.ticker))
        side = fill.side.lower()

        if side == "buy":
            new_qty = pos.quantity + fill.quantity
            pos.avg_cost = (
                (pos.avg_cost * pos.quantity) + (fill.price * fill.quantity)
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
