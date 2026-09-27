from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class MarketBar(BaseModel):
    ticker: str
    timestamp: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)


class PointInTimeRecord(BaseModel):
    ticker: str
    effective_at: datetime
    available_at: datetime
    recorded_at: datetime
    field: str
    value: float | int | str | None
    source: str
    version: str | None = None

    def is_available(self, simulation_time: datetime) -> bool:
        return self.available_at <= simulation_time
