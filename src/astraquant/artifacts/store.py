from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from typing import Any


@dataclass(frozen=True)
class ArtifactRef:
    run_id: str
    relative_path: str
    media_type: str
    description: str | None = None


class LocalArtifactStore:
    """Store AstraQuant-owned research artifacts under a configured root."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        path = (self.root / run_id).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("run path escapes artifact root") from exc
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_json(
        self,
        run_id: str,
        name: str,
        payload: dict[str, Any],
        *,
        description: str | None = None,
    ) -> ArtifactRef:
        if "/" in name or chr(92) in name:
            raise ValueError("artifact name must be a simple filename")
        target = self.run_dir(run_id) / name
        target.write_text(json.dumps(payload, default=str, indent=2), encoding="utf-8")
        return ArtifactRef(
            run_id=run_id,
            relative_path=str(target.relative_to(self.root)),
            media_type="application/json",
            description=description,
        )
