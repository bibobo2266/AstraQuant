from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
import json


@dataclass(frozen=True)
class SourceArtifact:
    repository: str | None
    path: str
    version: str | None = None
    fingerprint: str | None = None
    size_bytes: int | None = None


@dataclass(frozen=True)
class DatasetManifest:
    dataset_id: str
    created_at: datetime
    created_by: str
    sources: tuple[SourceArtifact, ...]
    code_version: str
    config_version: str | None = None
    row_count: int | None = None
    min_effective_at: datetime | None = None
    max_effective_at: datetime | None = None
    point_in_time_validated: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    experiment_id: str
    created_at: datetime
    dataset_id: str
    code_version: str
    parameters: dict[str, Any]
    feature_versions: dict[str, str]
    trial_number: int
    selection_role: str
    artifacts: tuple[str, ...] = field(default_factory=tuple)


def write_manifest(manifest: DatasetManifest | RunManifest, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(asdict(manifest), default=str, indent=2), encoding="utf-8")
