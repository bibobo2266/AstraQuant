from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from astraquant.research.feature_panel_integration import (
    AvailabilityStatus,
    FeaturePanelIntegrationError,
    FeaturePanelIntegrator,
    combine_availability_status,
    load_feature_panel_integration_config,
)
from astraquant.research.strategy_config import ComponentSpec
from astraquant.research.technical_components import column_threshold


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(
    tmp_path: Path,
    *,
    status: str = "VERIFIED",
    values: list[object] | None = None,
    source_available_at: list[object] | None = None,
    duplicate_feature_key: bool = False,
    formula_version: str = "fixture-formula-v1",
) -> tuple[Path, Path, Path]:
    values = values or [-0.01, 0.0, 0.02, None]
    dates = pd.to_datetime(
        ["2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07"]
    )
    feature = pd.DataFrame(
        {
            "date": dates,
            "stock_id": ["2330"] * 4,
            "close_to_ma120": values,
            "available_at_date": dates,
            "bars_seen": [150, 151, 152, 153],
            "unrequested_future_like_column": [1, 2, 3, 4],
        }
    )
    if source_available_at is not None:
        feature["source_available_at"] = pd.to_datetime(source_available_at)
    if duplicate_feature_key:
        feature = pd.concat([feature, feature.iloc[[0]]], ignore_index=True)

    root = tmp_path / "artifact"
    root.mkdir()
    parquet = root / "stock_features_2020.parquet"
    feature.to_parquet(parquet, index=False)

    manifest = {
        "artifact_name": "fixture-artifact",
        "source_revision": "fixture-source",
        "formula_version": formula_version,
        "epoch": "E1",
        "period": ["2016-01-04", "2021-12-31"],
        "stock_files": [
            {
                "path": "artifacts/x/stock_features_2020.parquet",
                "rows": len(feature),
                "sha256": _sha256(parquet),
            }
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    config = {
        "schema_version": "1",
        "name": "fixture",
        "epoch": "E1",
        "artifact": {
            "manifest_path": str(manifest_path),
            "artifact_name": "fixture-artifact",
            "source_revision": "fixture-source",
            "formula_version": "fixture-formula-v1",
            "epoch": "E1",
        },
        "policy": {"strategy_required_status": "VERIFIED"},
        "availability_groups": {
            "adjusted": {"status": status},
        },
        "requested_features": [
            {
                "column": "close_to_ma120",
                "kind": "RAW",
                "required": True,
                "warmup_sessions": 120,
                "dependencies": ["adjusted"],
                "expected_status": status,
            }
        ],
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
    )
    return config_path, manifest_path, root


def _panel() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07"]
            ),
            "stock_id": ["2330"] * 4,
            "close": [99.0, 100.0, 102.0, 101.0],
        }
    )


def test_status_aggregation_fails_closed():
    assert combine_availability_status(
        [AvailabilityStatus.VERIFIED]
    ) is AvailabilityStatus.VERIFIED
    assert combine_availability_status(
        [AvailabilityStatus.VERIFIED, AvailabilityStatus.ASSUMPTION_ONLY]
    ) is AvailabilityStatus.ASSUMPTION_ONLY
    assert combine_availability_status(
        [AvailabilityStatus.VERIFIED, AvailabilityStatus.UNKNOWN]
    ) is AvailabilityStatus.UNKNOWN
    assert combine_availability_status(
        [AvailabilityStatus.UNKNOWN, AvailabilityStatus.UNAVAILABLE]
    ) is AvailabilityStatus.UNAVAILABLE


def test_real_ma120_contract_is_blocked_before_artifact_read():
    cfg = load_feature_panel_integration_config(
        "configs/quality/pit_feature_matrix_layer1_integration_v1.yaml"
    )
    assert cfg.requested_features[0].column == "close_to_ma120"
    assert (
        cfg.requested_features[0].status
        is AvailabilityStatus.UNAVAILABLE
    )
    integrator = FeaturePanelIntegrator(
        config=cfg,
        artifact_root="/definitely/not/present",
        verified_only=True,
    )
    with pytest.raises(
        FeaturePanelIntegrationError,
        match="close_to_ma120:UNAVAILABLE",
    ):
        integrator.hydrate(
            pd.DataFrame(
                {
                    "date": [pd.Timestamp("2020-01-02")],
                    "stock_id": ["2330"],
                }
            )
        )


def test_exact_key_join_preserves_rows_nulls_and_only_requested_columns(tmp_path):
    config_path, manifest_path, root = _fixture(tmp_path)
    cfg = load_feature_panel_integration_config(config_path)
    result = FeaturePanelIntegrator(
        config=cfg,
        artifact_root=root,
        manifest_path=manifest_path,
    ).hydrate(_panel())

    assert len(result.frame) == 4
    assert result.frame["close_to_ma120"].tolist()[:3] == [-0.01, 0.0, 0.02]
    assert pd.isna(result.frame.loc[3, "close_to_ma120"])
    assert "unrequested_future_like_column" not in result.frame
    assert (
        result.frame.loc[3, "__feature_missing_reason__close_to_ma120"]
        == "FEATURE_VALUE_NULL"
    )
    assert result.audit.iloc[0]["value_nonnull"] == 3


def test_ma120_threshold_zero_and_null_is_distinct_from_below_ma(tmp_path):
    config_path, manifest_path, root = _fixture(tmp_path)
    cfg = load_feature_panel_integration_config(config_path)
    frame = FeaturePanelIntegrator(
        config=cfg,
        artifact_root=root,
        manifest_path=manifest_path,
    ).hydrate(_panel()).frame
    passed = column_threshold(
        panel=frame,
        spec=ComponentSpec(
            type="COLUMN_THRESHOLD",
            params={"column": "close_to_ma120", "min": 0.0},
        ),
        cache=None,
        context=None,
    )
    assert passed.tolist() == [False, True, True, False]
    assert (
        frame.loc[0, "__feature_missing_reason__close_to_ma120"] == ""
    )
    assert (
        frame.loc[3, "__feature_missing_reason__close_to_ma120"]
        == "FEATURE_VALUE_NULL"
    )


def test_duplicate_panel_key_fails(tmp_path):
    config_path, manifest_path, root = _fixture(tmp_path)
    panel = pd.concat([_panel(), _panel().iloc[[0]]], ignore_index=True)
    with pytest.raises(
        FeaturePanelIntegrationError,
        match="canonical panel contains duplicate logical keys",
    ):
        FeaturePanelIntegrator(
            config=load_feature_panel_integration_config(config_path),
            artifact_root=root,
            manifest_path=manifest_path,
        ).hydrate(panel)


def test_duplicate_artifact_key_fails(tmp_path):
    config_path, manifest_path, root = _fixture(
        tmp_path, duplicate_feature_key=True
    )
    with pytest.raises(
        FeaturePanelIntegrationError,
        match="duplicate logical keys",
    ):
        FeaturePanelIntegrator(
            config=load_feature_panel_integration_config(config_path),
            artifact_root=root,
            manifest_path=manifest_path,
        ).hydrate(_panel())


def test_column_conflict_fails(tmp_path):
    config_path, manifest_path, root = _fixture(tmp_path)
    panel = _panel()
    panel["close_to_ma120"] = 999
    with pytest.raises(
        FeaturePanelIntegrationError,
        match="column conflict",
    ):
        FeaturePanelIntegrator(
            config=load_feature_panel_integration_config(config_path),
            artifact_root=root,
            manifest_path=manifest_path,
        ).hydrate(panel)


def test_manifest_version_mismatch_fails(tmp_path):
    config_path, manifest_path, root = _fixture(
        tmp_path, formula_version="wrong-formula"
    )
    with pytest.raises(
        FeaturePanelIntegrationError,
        match="formula_version mismatch",
    ):
        FeaturePanelIntegrator(
            config=load_feature_panel_integration_config(config_path),
            artifact_root=root,
            manifest_path=manifest_path,
        ).hydrate(_panel())


def test_checksum_mismatch_fails(tmp_path):
    config_path, manifest_path, root = _fixture(tmp_path)
    parquet = root / "stock_features_2020.parquet"
    changed = pd.read_parquet(parquet)
    changed.loc[0, "close_to_ma120"] = 9.0
    changed.to_parquet(parquet, index=False)
    with pytest.raises(
        FeaturePanelIntegrationError,
        match="checksum mismatch",
    ):
        FeaturePanelIntegrator(
            config=load_feature_panel_integration_config(config_path),
            artifact_root=root,
            manifest_path=manifest_path,
        ).hydrate(_panel())


def test_source_available_at_at_or_after_explicit_cutoff_fails(tmp_path):
    source_times = [
        "2020-01-02 18:00:00",
        "2020-01-03 18:00:00",
        "2020-01-06 18:00:00",
        "2020-01-08 08:59:00",
    ]
    config_path, manifest_path, root = _fixture(
        tmp_path, source_available_at=source_times
    )
    panel = _panel()
    panel["__decision_cutoff_at"] = pd.to_datetime(
        [
            "2020-01-03 08:45:00",
            "2020-01-06 08:45:00",
            "2020-01-07 08:45:00",
            "2020-01-08 08:45:00",
        ]
    )
    with pytest.raises(
        FeaturePanelIntegrationError,
        match="not available before decision cutoff",
    ):
        FeaturePanelIntegrator(
            config=load_feature_panel_integration_config(config_path),
            artifact_root=root,
            manifest_path=manifest_path,
        ).hydrate(panel)


def test_outside_e1_is_blocked(tmp_path):
    config_path, manifest_path, root = _fixture(tmp_path)
    panel = pd.DataFrame(
        {"date": [pd.Timestamp("2022-01-03")], "stock_id": ["2330"]}
    )
    with pytest.raises(
        FeaturePanelIntegrationError,
        match="E1-only",
    ):
        FeaturePanelIntegrator(
            config=load_feature_panel_integration_config(config_path),
            artifact_root=root,
            manifest_path=manifest_path,
        ).hydrate(panel)


def test_future_artifact_row_change_does_not_rewrite_past_join(tmp_path):
    config_path, manifest_path, root = _fixture(tmp_path)
    cfg = load_feature_panel_integration_config(config_path)
    integrator = FeaturePanelIntegrator(
        config=cfg,
        artifact_root=root,
        manifest_path=manifest_path,
    )
    before = integrator.hydrate(_panel()).frame.loc[
        :1, ["date", "stock_id", "close_to_ma120"]
    ].copy()

    parquet = root / "stock_features_2020.parquet"
    feature = pd.read_parquet(parquet)
    feature.loc[feature["date"].eq(pd.Timestamp("2020-01-07")), "close_to_ma120"] = 999
    feature.to_parquet(parquet, index=False)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["stock_files"][0]["sha256"] = _sha256(parquet)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    after = FeaturePanelIntegrator(
        config=cfg,
        artifact_root=root,
        manifest_path=manifest_path,
    ).hydrate(_panel()).frame.loc[
        :1, ["date", "stock_id", "close_to_ma120"]
    ]
    pd.testing.assert_frame_equal(before, after)
