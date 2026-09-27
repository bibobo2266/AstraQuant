from pathlib import Path

import pandas as pd
import pytest

from astraquant.data.source_adapter import SourceDataAdapter, SourceDataError


def test_adapter_reads_and_has_no_write_api(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    pd.DataFrame({"ticker": ["2330"], "close": [1000.0]}).to_parquet(source / "sample.parquet")

    adapter = SourceDataAdapter(source)
    result = adapter.read_parquet("sample.parquet")

    assert len(result) == 1
    assert not hasattr(adapter, "write")
    assert not hasattr(adapter, "delete")
    assert not hasattr(adapter, "rename")
    assert not hasattr(adapter, "update")


def test_adapter_rejects_path_escape(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    adapter = SourceDataAdapter(source)

    with pytest.raises(SourceDataError):
        adapter.exists("../outside.parquet")
