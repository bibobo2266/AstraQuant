import pytest

from astraquant.artifacts.index import ArtifactIndex
from astraquant.artifacts.store import ArtifactRef


def test_artifact_index_groups_by_run():
    index = ArtifactIndex()
    ref = ArtifactRef(
        run_id="RUN-1",
        relative_path="RUN-1/metrics.json",
        media_type="application/json",
    )
    index.add(ref)
    assert index.for_run("RUN-1") == (ref,)


def test_duplicate_artifact_path_is_rejected():
    index = ArtifactIndex()
    ref = ArtifactRef(
        run_id="RUN-1",
        relative_path="RUN-1/metrics.json",
        media_type="application/json",
    )
    index.add(ref)
    with pytest.raises(ValueError):
        index.add(ref)
