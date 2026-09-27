from datetime import datetime

import pytest

from astraquant.decision.guard import (
    HumanApprovalRequired,
    create_order_intent_after_approval,
)
from astraquant.decision.review import HumanDecision, ReviewHistory, ReviewRecord


def test_no_review_blocks_intent():
    history = ReviewHistory()
    with pytest.raises(HumanApprovalRequired):
        create_order_intent_after_approval(
            packet_id="DP-1",
            review_history=history,
            intent_id="I1",
            ticker="2330",
            side="buy",
            quantity=10,
            created_at=datetime(2026, 1, 1),
            rationale="test",
        )


def test_latest_approved_review_allows_intent():
    history = ReviewHistory()
    history.append(
        ReviewRecord(
            review_id="R1",
            packet_id="DP-1",
            reviewer="human",
            decision=HumanDecision.APPROVED,
            reason="approved after review",
            reviewed_at=datetime(2026, 1, 1),
        )
    )

    intent = create_order_intent_after_approval(
        packet_id="DP-1",
        review_history=history,
        intent_id="I1",
        ticker="2330",
        side="buy",
        quantity=10,
        created_at=datetime(2026, 1, 1),
        rationale="approved packet",
    )
    assert intent.intent_id == "I1"


def test_later_rejection_blocks_intent():
    history = ReviewHistory()
    history.append(
        ReviewRecord(
            review_id="R1",
            packet_id="DP-1",
            reviewer="human",
            decision=HumanDecision.APPROVED,
            reason="initial approval",
            reviewed_at=datetime(2026, 1, 1),
        )
    )
    history.append(
        ReviewRecord(
            review_id="R2",
            packet_id="DP-1",
            reviewer="human",
            decision=HumanDecision.REJECTED,
            reason="new conflicting information",
            reviewed_at=datetime(2026, 1, 2),
        )
    )

    with pytest.raises(HumanApprovalRequired):
        create_order_intent_after_approval(
            packet_id="DP-1",
            review_history=history,
            intent_id="I2",
            ticker="2330",
            side="buy",
            quantity=10,
            created_at=datetime(2026, 1, 2),
            rationale="should be blocked",
        )
