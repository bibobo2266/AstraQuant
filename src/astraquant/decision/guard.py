from __future__ import annotations

from datetime import datetime

from astraquant.portfolio.models import OrderIntent

from .review import HumanDecision, ReviewHistory


class HumanApprovalRequired(RuntimeError):
    pass


def create_order_intent_after_approval(
    *,
    packet_id: str,
    review_history: ReviewHistory,
    intent_id: str,
    ticker: str,
    side: str,
    quantity: float,
    created_at: datetime,
    rationale: str,
) -> OrderIntent:
    latest = review_history.latest_for_packet(packet_id)
    if latest is None or latest.decision is not HumanDecision.APPROVED:
        raise HumanApprovalRequired(
            f"packet {packet_id} does not have current explicit human approval"
        )

    if quantity <= 0:
        raise ValueError("quantity must be positive")

    return OrderIntent(
        intent_id=intent_id,
        ticker=ticker,
        side=side,
        quantity=quantity,
        created_at=created_at,
        rationale=rationale,
    )
