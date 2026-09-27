from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd
import pyarrow.parquet as pq


class SourceDataError(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceFileInfo:
    relative_path: str
    size_bytes: int


class SourceDataAdapter:
    """Read-only adapter for an external source-data root.

    This class deliberately exposes no write, update, rename, or delete methods.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        if not self.root.exists():
            raise SourceDataError(f"Source root does not exist: {self.root}")
        if not self.root.is_dir():
            raise SourceDataError(f"Source root is not a directory: {self.root}")

    def _resolve(self, relative_path: str | Path) -> Path:
        path = (self.root / relative_path).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise SourceDataError("Path escapes configured source root") from exc
        return path

    def exists(self, relative_path: str | Path) -> bool:
        return self._resolve(relative_path).exists()

    def list_files(
        self,
        relative_dir: str = "",
        suffixes: Iterable[str] | None = None,
    ) -> list[str]:
        base = self._resolve(relative_dir)
        if not base.exists():
            return []
        wanted = {s.lower() for s in (suffixes or [])}
        return sorted(
            str(path.relative_to(self.root))
            for path in base.rglob("*")
            if path.is_file() and (not wanted or path.suffix.lower() in wanted)
        )

    def file_info(self, relative_path: str | Path) -> SourceFileInfo:
        path = self._resolve(relative_path)
        return SourceFileInfo(
            relative_path=str(path.relative_to(self.root)),
            size_bytes=path.stat().st_size,
        )

    def parquet_schema(self, relative_path: str | Path) -> dict[str, str]:
        schema = pq.read_schema(self._resolve(relative_path))
        return {field.name: str(field.type) for field in schema}

    def parquet_metadata(self, relative_path: str | Path) -> dict[str, object]:
        parquet = pq.ParquetFile(self._resolve(relative_path))
        return {
            "num_rows": parquet.metadata.num_rows,
            "num_row_groups": parquet.metadata.num_row_groups,
            "num_columns": parquet.metadata.num_columns,
            "schema": {field.name: str(field.type) for field in parquet.schema_arrow},
        }

    def read_parquet(
        self,
        relative_path: str | Path,
        *,
        columns: list[str] | None = None,
    ) -> pd.DataFrame:
        return pd.read_parquet(self._resolve(relative_path), columns=columns)
