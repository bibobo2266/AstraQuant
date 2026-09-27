from __future__ import annotations

from dataclasses import dataclass, field

from .store import ArtifactRef


@dataclass
class ArtifactIndex:
    _by_run: dict[str, list[ArtifactRef]] = field(default_factory=dict)

    def add(self, artifact: ArtifactRef) -> None:
        refs = self._by_run.setdefault(artifact.run_id, [])
        if any(x.relative_path == artifact.relative_path for x in refs):
            raise ValueError(
                f"artifact already indexed for run {artifact.run_id}: "
                f"{artifact.relative_path}"
            )
        refs.append(artifact)

    def for_run(self, run_id: str) -> tuple[ArtifactRef, ...]:
        return tuple(self._by_run.get(run_id, ()))
