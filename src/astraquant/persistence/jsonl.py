from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
import json
from typing import Any


class AppendOnlyJsonlStore:
    """Minimal append-only persistence for audit/review/result records."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: Any) -> None:
        if is_dataclass(record):
            payload = asdict(record)
        elif hasattr(record, "model_dump"):
            payload = record.model_dump(mode="json")
        elif isinstance(record, dict):
            payload = record
        else:
            raise TypeError("record must be a dataclass, pydantic model, or dict")

        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, default=str, sort_keys=True))
            handle.write("\n")

    def read_all(self) -> tuple[dict[str, Any], ...]:
        if not self.path.exists():
            return ()
        records: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if stripped:
                    records.append(json.loads(stripped))
        return tuple(records)
