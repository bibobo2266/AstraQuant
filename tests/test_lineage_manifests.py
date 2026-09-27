from datetime import datetime
import json

from astraquant.lineage.manifests import (
    DatasetManifest,
    RunManifest,
    SourceArtifact,
    write_manifest,
)


def test_dataset_manifest_serializes(tmp_path):
    manifest = DatasetManifest(
        dataset_id="ds-v1",
        created_at=datetime(2026, 1, 1),
        created_by="test",
        sources=(
            SourceArtifact(
                repository="source/repo",
                path="data/prices.parquet",
                version="blob-sha",
            ),
        ),
        code_version="commit-sha",
        point_in_time_validated=False,
    )
    target = tmp_path / "dataset.json"
    write_manifest(manifest, target)
    payload = json.loads(target.read_text())
    assert payload["dataset_id"] == "ds-v1"
    assert payload["sources"][0]["path"] == "data/prices.parquet"


def test_run_manifest_requires_explicit_selection_role(tmp_path):
    manifest = RunManifest(
        run_id="run-1",
        experiment_id="EXP-R001",
        created_at=datetime(2026, 1, 1),
        dataset_id="ds-v1",
        code_version="commit-sha",
        parameters={"lookback": 120},
        feature_versions={"rs": "v1"},
        trial_number=1,
        selection_role="validation",
    )
    target = tmp_path / "run.json"
    write_manifest(manifest, target)
    payload = json.loads(target.read_text())
    assert payload["selection_role"] == "validation"
