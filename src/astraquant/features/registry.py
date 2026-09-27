from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


@dataclass(frozen=True)
class FeatureDefinition:
    name: str
    version: str
    family: str
    description: str
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    point_in_time_safe: bool = False
    availability_rule: str | None = None


class FeatureRegistry:
    def __init__(self) -> None:
        self._features: dict[tuple[str, str], FeatureDefinition] = {}

    def register(self, feature: FeatureDefinition) -> None:
        key = (feature.name, feature.version)
        if key in self._features:
            raise ValueError(f"Feature already registered: {feature.name}@{feature.version}")
        self._features[key] = feature

    def get(self, name: str, version: str) -> FeatureDefinition:
        return self._features[(name, version)]

    def list(self) -> Sequence[FeatureDefinition]:
        return tuple(self._features.values())
