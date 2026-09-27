from datetime import datetime

from astraquant.decision.builder import build_decision_packet
from astraquant.research.results import ResearchResultSummary


def test_builder_carries_supporting_and_contradicting_evidence():
    result = ResearchResultSummary(
        experiment_id="EXP-R001",
        run_id="RUN-1",
        dataset_id="DS-1",
        headline_metrics={"rank_ic": 0.04},
        evidence_supporting=("positive WFO IC",),
        evidence_contradicting=("weak bear regime",),
        limitations=("small sample",),
        unresolved_questions=("execution sensitivity",),
    )

    packet = build_decision_packet(
        packet_id="DP-1",
        symbol="2330",
        as_of=datetime(2026, 1, 5),
        result=result,
        suggested_action="review",
        allowed_actions=["hold", "watch"],
        created_at=datetime(2026, 1, 5, 12, 0),
    )

    assert packet.packet_id == "DP-1"
    assert packet.evidence_supporting == ["positive WFO IC"]
    assert packet.evidence_contradicting == ["weak bear regime"]
    assert "small sample" in packet.unresolved_questions
