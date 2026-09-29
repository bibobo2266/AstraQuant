from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Callable

import pandas as pd


@dataclass(frozen=True)
class FeatureCacheKey:
    source_revision: str
    feature_name: str
    params_json: str
    availability_policy: str

    @classmethod
    def build(
        cls,
        *,
        source_revision: str,
        feature_name: str,
        params: dict[str, Any],
        availability_policy: str,
    ) -> "FeatureCacheKey":
        return cls(
            source_revision=str(source_revision),
            feature_name=str(feature_name),
            params_json=json.dumps(params, sort_keys=True, ensure_ascii=False, separators=(",", ":")),
            availability_policy=str(availability_policy),
        )

    @property
    def digest(self) -> str:
        raw = "|".join(
            [
                self.source_revision,
                self.feature_name,
                self.params_json,
                self.availability_policy,
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class FeatureCache:
    _frames: dict[FeatureCacheKey, pd.Series] = field(default_factory=dict)
    hits: int = 0
    misses: int = 0

    def get_or_compute(
        self,
        key: FeatureCacheKey,
        compute: Callable[[], pd.Series],
    ) -> pd.Series:
        if key in self._frames:
            self.hits += 1
            return self._frames[key].copy()
        value = compute()
        if not isinstance(value, pd.Series):
            raise TypeError("feature cache values must be pandas Series")
        self._frames[key] = value.copy()
        self.misses += 1
        return value.copy()

    @property
    def size(self) -> int:
        return len(self._frames)
