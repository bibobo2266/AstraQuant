from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from astraquant.portfolio.models import OrderIntent
from astraquant.risk.constraints import (
    RiskCheckResult,
    RiskConstraint,
    RiskContext,
    evaluate_constraints,
)

from .review import HumanDecision, ReviewHistory


class PreOrderBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class PreOrderDecision:
    approved: bool
    review_id: str | None
    risk_results: tuple[RiskCheckResult, ...]
    blockers: tuple[str, ...]


def evaluate_pre_order(
    *,
    packet_id: str,
    review_history: ReviewHistory,
    risk_constraints: list[RiskConstraint],
    risk_context: RiskContext,
) -> PreOrderDecision:
    latest = review_history.latest_for_packet(packet_id)

    blockers: list[str] = []
    review_id: str | None = None

    if latest is None:
        blockers.append("missing_human_review")
    else:
        review_id = latest.review_id
        if latest.decision is not HumanDecision.APPROVED:
            blockers.append(f"human_review_{latest.decision.value.lower()}")

    risk_results = evaluate_constraints(risk_constraints, risk_context)
    blockers.extend(
        f"risk:{result.name}"
        for result in risk_results
        if not result.passed
    )

    return PreOrderDecision(
        approved=not blockers,
        review_id=review_id,
        risk_results=risk_results,
        blockers=tuple(blockers),
    )


def create_order_intent(
    *,
    packet_id: str,
    review_history: ReviewHistory,
    risk_constraints: list[RiskConstraint],
    risk_context: RiskContext,
    intent_id: str,
    ticker: str,
    side: str,
    quantity: float,
    created_at: datetime,
    rationale: str,
) -> OrderIntent:
    gate = evaluate_pre_order(
        packet_id=packet_id,
        review_history=review_history,
        risk_constraints=risk_constraints,
        risk_context=risk_context,
    )
    if not gate.approved:
        raise PreOrderBlocked(
            f"pre-order gate blocked packet {packet_id}: {', '.join(gate.blockers)}"
        )
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    if ticker != risk_context.symbol:
        raise ValueError("ticker does not match risk context symbol")
    if side.lower() != risk_context.side.lower():
        raise ValueError("side does not match risk context side")
    if quantity != risk_context.quantity:
        raise ValueError("quantity does not match risk context quantity")

    return OrderIntent(
        intent_id=intent_id,
        ticker=ticker,
        side=side,
        quantity=quantity,
        created_at=created_at,
        rationale=rationale,
        source_packet_id=packet_id,
        source_review_id=gate.review_id,
    )
