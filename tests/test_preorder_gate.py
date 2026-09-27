from datetime import datetime

import pytest

from astraquant.decision.preorder import PreOrderBlocked, create_order_intent
from astraquant.decision.review import HumanDecision, ReviewHistory, ReviewRecord
from astraquant.risk.constraints import MaxPositionCountConstraint, RiskContext


def approved_history() -> ReviewHistory:
    history = ReviewHistory()
    history.append(
        ReviewRecord(
            review_id="R1",
            packet_id="DP-1",
            reviewer="human",
            decision=HumanDecision.APPROVED,
            reason="approved",
            reviewed_at=datetime(2026, 1, 1),
        )
    )
    return history


def test_approved_review_and_passing_risk_allows_intent():
    intent = create_order_intent(
        packet_id="DP-1",
        review_history=approved_history(),
        risk_constraints=[MaxPositionCountConstraint(max_positions=5)],
        risk_context=RiskContext(
            symbol="2330",
            side="buy",
            quantity=10,
            portfolio_state={"position_count": 2, "opening_new_position": True},
        ),
        intent_id="I1",
        ticker="2330",
        side="buy",
        quantity=10,
        created_at=datetime(2026, 1, 1),
        rationale="approved and risk-passed",
    )
    assert intent.source_packet_id == "DP-1"
    assert intent.source_review_id == "R1"


def test_risk_failure_blocks_even_with_human_approval():
    with pytest.raises(PreOrderBlocked):
        create_order_intent(
            packet_id="DP-1",
            review_history=approved_history(),
            risk_constraints=[MaxPositionCountConstraint(max_positions=2)],
            risk_context=RiskContext(
                symbol="2330",
                side="buy",
                quantity=10,
                portfolio_state={"position_count": 2, "opening_new_position": True},
            ),
            intent_id="I1",
            ticker="2330",
            side="buy",
            quantity=10,
            created_at=datetime(2026, 1, 1),
            rationale="should be blocked by risk",
        )
