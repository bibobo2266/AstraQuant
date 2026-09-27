from __future__ import annotations

from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class DecisionPacket(BaseModel):
    symbol: str
    as_of: datetime
    market_context: dict[str, Any] = Field(default_factory=dict)
    portfolio_context: dict[str, Any] = Field(default_factory=dict)
    signals: list[dict[str, Any]] = Field(default_factory=list)
    evidence_supporting: list[str] = Field(default_factory=list)
    evidence_contradicting: list[str] = Field(default_factory=list)
    thesis: str | None = None
    thesis_invalidation: list[str] = Field(default_factory=list)
    suggested_action: str | None = None
    allowed_actions: list[str] = Field(default_factory=list)
    risk_constraints: list[str] = Field(default_factory=list)
    portfolio_conflicts: list[str] = Field(default_factory=list)
    data_freshness: dict[str, Any] = Field(default_factory=dict)
    unresolved_questions: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
    human_decision: str | None = None
    human_reason: str | None = None
    created_at: datetime
    reviewed_at: datetime | None = None
