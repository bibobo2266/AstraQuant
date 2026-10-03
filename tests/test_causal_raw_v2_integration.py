from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from astraquant.research.causal_raw_v2 import (
    FORMULA_VERSION,
    PRICE_COORDINATE,
    build_causal_raw_v2_features,
)
from astraquant.research.feature_panel_integration import (
    AvailabilityStatus,
    FeaturePanelIntegrationConfig,
    FeaturePanelIntegrationError,
    FeaturePanelIntegrator,
    FeatureRequest,
)


def _panel(n: int = 140) -> pd.DataFrame:
    dates = pd.bdate_range("2020-01-02", periods=n)
    return pd.DataFrame(
        {
            "date": dates,
            "stock_id": ["2330"] * n,
            "raw_close": np.full(n, 100.0),
            "Trading_money": np.full(n, 30_000_000.0),
            "observed_trade": True,
            "valid_ohlc": True,
            "decision_cutoff_at": dates + pd.Timedelta(days=1, hours=8, minutes=45),
        }
    )


def _empty_events() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "stock_id",
            "effective_date",
            "event_kind",
            "known_at",
            "cash_per_share",
            "share_multiplier",
        ]
    )


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path, *, late_source_index: int | None = None):
    source_revision = "causal-v2-source-fixture"
    features = build_causal_raw_v2_features(_panel(), _empty_events())
    features["available_at_date"] = features["date"]
    features["source_available_at"] = features["date"] + pd.Timedelta(hours=18)

    selected = features.loc[118:121].copy().reset_index(drop=True)
    cutoff = selected["date"] + pd.Timedelta(days=1, hours=8, minutes=45)
    if late_source_index is not None:
        selected.loc[late_source_index, "source_available_at"] = cutoff.iloc[
            late_source_index
        ]

    artifact_root = tmp_path / "artifact"
    artifact_root.mkdir()
    parquet = artifact_root / "stock_features_2020.parquet"
    selected.to_parquet(parquet, index=False)

    manifest = {
        "artifact_name": "causal-raw-v2-fixture",
        "source_revision": source_revision,
        "formula_version": FORMULA_VERSION,
        "epoch": "E1",
        "period": ["2016-01-04", "2021-12-31"],
        "stock_files": [
            {
                "path": "artifacts/causal_raw_v2/stock_features_2020.parquet",
                "rows": len(selected),
                "sha256": _sha256(parquet),
            }
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    requested = (
        FeatureRequest(
            column="close_to_ma120",
            kind="RAW",
            required=True,
            warmup_sessions=120,
            dependencies=("synthetic_verified_input",),
            status=AvailabilityStatus.VERIFIED,
        ),
        FeatureRequest(
            column="n60_first_cross",
            kind="RAW",
            required=True,
            warmup_sessions=62,
            dependencies=("synthetic_verified_input",),
            status=AvailabilityStatus.VERIFIED,
        ),
        FeatureRequest(
            column="ma120_comparable",
            kind="RAW",
            required=True,
            warmup_sessions=None,
            dependencies=("synthetic_verified_input",),
            status=AvailabilityStatus.VERIFIED,
        ),
        FeatureRequest(
            column="n60_comparable",
            kind="RAW",
            required=True,
            warmup_sessions=None,
            dependencies=("synthetic_verified_input",),
            status=AvailabilityStatus.VERIFIED,
        ),
        FeatureRequest(
            column="price_coordinate",
            kind="RAW",
            required=True,
            warmup_sessions=None,
            dependencies=("synthetic_verified_input",),
            status=AvailabilityStatus.VERIFIED,
        ),
    )
    cfg = FeaturePanelIntegrationConfig(
        name="causal_raw_v2_synthetic_integration",
        epoch="E1",
        manifest_path=manifest_path,
        expected_artifact_name="causal-raw-v2-fixture",
        expected_source_revision=source_revision,
        expected_formula_version=FORMULA_VERSION,
        expected_epoch="E1",
        strategy_required_status=AvailabilityStatus.VERIFIED,
        requested_features=requested,
    )
    canonical = selected[["date", "stock_id"]].copy()
    canonical["__decision_cutoff_at"] = cutoff
    return cfg, manifest_path, artifact_root, canonical, selected


def test_comparable_flags_match_feature_states_and_coordinate_gate():
    panel = _panel()
    event_date = panel.loc[120, "date"]
    known_at = panel.loc[124, "date"] + pd.Timedelta(hours=12)
    events = pd.DataFrame(
        [["2330", event_date, "CASH_DIVIDEND", known_at, 5.0, np.nan]],
        columns=[
            "stock_id",
            "effective_date",
            "event_kind",
            "known_at",
            "cash_per_share",
            "share_multiplier",
        ],
    )
    panel.loc[panel.index >= 120, "raw_close"] = 95.0
    out = build_causal_raw_v2_features(panel, events)

    assert out["ma120_comparable"].equals(out["ma120_state"].eq("READY"))
    assert out["n60_comparable"].equals(out["n60_state"].eq("READY"))
    blocked = out["coordinate_status"].ne("READY")
    assert (~out.loc[blocked, "ma120_comparable"]).all()
    assert (~out.loc[blocked, "n60_comparable"]).all()


def test_v2_artifact_hydrates_exact_fields_version_coordinate_and_cutoff(tmp_path):
    cfg, manifest_path, artifact_root, canonical, source = _fixture(tmp_path)
    result = FeaturePanelIntegrator(
        config=cfg,
        artifact_root=artifact_root,
        manifest_path=manifest_path,
        verified_only=True,
    ).hydrate(canonical)

    assert len(result.frame) == len(canonical)
    assert result.manifest["formula_version"] == FORMULA_VERSION
    assert result.manifest["source_revision"] == "causal-v2-source-fixture"
    assert result.frame["price_coordinate"].eq(PRICE_COORDINATE).all()
    assert "causal_close" not in result.frame
    assert result.frame["source_available_at"].lt(
        result.frame["__decision_cutoff_at"]
    ).all()

    expected = source["close_to_ma120"].reset_index(drop=True)
    pd.testing.assert_series_equal(
        result.frame["close_to_ma120"].reset_index(drop=True),
        expected,
        check_names=False,
    )
    assert pd.isna(result.frame.loc[0, "close_to_ma120"])
    assert (
        result.frame.loc[0, "__feature_missing_reason__close_to_ma120"]
        == "WARMUP_INSUFFICIENT"
    )
    assert (
        result.frame.loc[1, "__feature_missing_reason__close_to_ma120"]
        == ""
    )
    assert set(result.audit["availability_status"]) == {"VERIFIED"}


def test_v2_hydration_rejects_source_at_decision_cutoff(tmp_path):
    cfg, manifest_path, artifact_root, canonical, _ = _fixture(
        tmp_path, late_source_index=2
    )
    with pytest.raises(
        FeaturePanelIntegrationError,
        match="not available before decision cutoff",
    ):
        FeaturePanelIntegrator(
            config=cfg,
            artifact_root=artifact_root,
            manifest_path=manifest_path,
            verified_only=True,
        ).hydrate(canonical)


def test_v2_hydration_rejects_e2_key_before_artifact_read(tmp_path):
    cfg, manifest_path, _, _, _ = _fixture(tmp_path)
    outside = pd.DataFrame(
        {
            "date": [pd.Timestamp("2022-01-03")],
            "stock_id": ["2330"],
            "__decision_cutoff_at": [pd.Timestamp("2022-01-04 08:45:00")],
        }
    )
    with pytest.raises(FeaturePanelIntegrationError, match="E1-only"):
        FeaturePanelIntegrator(
            config=cfg,
            artifact_root="/definitely/not/present",
            manifest_path=manifest_path,
            verified_only=True,
        ).hydrate(outside)
