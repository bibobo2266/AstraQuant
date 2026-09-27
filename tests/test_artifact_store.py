import json

import pytest

from astraquant.artifacts.store import LocalArtifactStore


def test_artifact_store_writes_under_configured_root(tmp_path):
    store = LocalArtifactStore(tmp_path / "artifacts")
    ref = store.write_json("run-1", "metrics.json", {"sharpe": 1.2})
    assert ref.relative_path == "run-1/metrics.json"
    payload = json.loads((tmp_path / "artifacts" / "run-1" / "metrics.json").read_text())
    assert payload["sharpe"] == 1.2


def test_artifact_name_cannot_escape_run_directory(tmp_path):
    store = LocalArtifactStore(tmp_path / "artifacts")
    with pytest.raises(ValueError):
        store.write_json("run-1", "../escape.json", {"x": 1})
