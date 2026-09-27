from __future__ import annotations

from datetime import datetime
from typing import Any

from astraquant.research.results import ResearchResultSummary

from .models import DecisionPacket


def build_decision_packet(
    *,
    symbol: str,
    as_of: datetime,
    result: ResearchResultSummary,
    market_context: dict[str, Any] | None = None,
    portfolio_context: dict[str, Any] | None = None,
    signals: list[dict[str, Any]] | None = None,
    thesis: str | None = None,
    thesis_invalidation: list[str] | None = None,
    suggested_action: str | None = None,
    allowed_actions: list[str] | None = None,
    risk_constraints: list[str] | None = None,
    portfolio_conflicts: list[str] | None = None,
    data_freshness: dict[str, Any] | None = None,
    confidence: float | None = None,
    created_at: datetime | None = None,
) -> DecisionPacket:
    result.validate()

    unresolved = list(result.unresolved_questions)
    unresolved.extend(result.limitations)

    return DecisionPacket(
        symbol=symbol,
        as_of=as_of,
        market_context=market_context or {},
        portfolio_context=portfolio_context or {},
        signals=signals or [],
        evidence_supporting=list(result.evidence_supporting),
        evidence_contradicting=list(result.evidence_contradicting),
        thesis=thesis,
        thesis_invalidation=thesis_invalidation or [],
        suggested_action=suggested_action,
        allowed_actions=allowed_actions or [],
        risk_constraints=risk_constraints or [],
        portfolio_conflicts=portfolio_conflicts or [],
        data_freshness=data_freshness or {},
        unresolved_questions=unresolved,
        confidence=confidence,
        created_at=created_at or datetime.utcnow(),
    )
