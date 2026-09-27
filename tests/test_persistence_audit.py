from datetime import datetime

import pytest

from astraquant.audit.models import DecisionAuditTrail
from astraquant.persistence.jsonl import AppendOnlyJsonlStore


def test_audit_trail_requires_all_ids():
    trail = DecisionAuditTrail(
        experiment_id="EXP-R001",
        run_id="RUN-1",
        dataset_id="DS-1",
        packet_id="DP-1",
        review_id="R1",
        intent_id="I1",
        created_at=datetime(2026, 1, 1),
    )
    trail.validate()


def test_missing_audit_id_is_rejected():
    trail = DecisionAuditTrail(
        experiment_id="EXP-R001",
        run_id="RUN-1",
        dataset_id="",
        packet_id="DP-1",
        review_id="R1",
        intent_id="I1",
        created_at=datetime(2026, 1, 1),
    )
    with pytest.raises(ValueError):
        trail.validate()


def test_jsonl_store_appends_records(tmp_path):
    store = AppendOnlyJsonlStore(tmp_path / "audit.jsonl")
    store.append({"id": "A1"})
    store.append({"id": "A2"})
    records = store.read_all()
    assert [record["id"] for record in records] == ["A1", "A2"]
