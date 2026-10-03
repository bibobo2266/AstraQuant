from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from astraquant.research.causal_raw_v2 import (
    FORMULA_VERSION,
    PRICE_COORDINATE,
    build_causal_raw_v2_features,
)
from astraquant.research.feature_panel_integration import (
    FeaturePanelIntegrationError,
    FeaturePanelIntegrator,
    load_feature_panel_integration_config,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _raw_panel(n: int = 130) -> pd.DataFrame:
    dates = pd.bdate_range("2020-01-02", periods=n)
    close = 100.0 + np.linspace(0.0, 2.0, n)
    return pd.DataFrame(
        {
            "date": dates,
            "stock_id": ["2330"] * n,
            "raw_close": close,
            "Trading_money": np.full(n, 30_000_000.0),
            "observed_trade": True,
            "valid_ohlc": True,
            "decision_cutoff_at": dates + pd.Timedelta(days=1) + pd.Timedelta(hours=8, minutes=45),
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


def _fixture(tmp_path: Path, *, late_source: bool = False):
    raw = _raw_panel()
    feature = build_causal_raw_v2_features(raw, _empty_events())
    feature["available_at_date"] = feature["date"]
    feature["source_available_at"] = feature["date"] + pd.Timedelta(hours=18)
    if late_source:
        feature.loc[129, "source_available_at"] = raw.loc[129, "decision_cutoff_at"]

    keep = [
        "date",
        "stock_id",
        "available_at_date",
        "source_available_at",
        "bars_seen",
        "close_to_ma120",
        "n60_first_cross",
        "prior20_amount_twd",
        "ma120_state",
        "n60_state",
        "prior20_amount_state",
        "formula_version",
        "price_coordinate",
    ]
    root = tmp_path / "artifact"
    root.mkdir()
    parquet = root / "stock_features_2020.parquet"
    feature[keep].to_parquet(parquet, index=False)

    manifest = {
        "artifact_name": "causal-raw-v2-fixture",
        "source_revision": "fixture-source",
        "formula_version": FORMULA_VERSION,
        "epoch": "E1",
        "period": ["2016-01-04", "2021-12-31"],
        "stock_files": [
            {
                "path": "artifacts/causal_raw_v2/stock_features_2020.parquet",
                "rows": len(feature),
                "sha256": _sha256(parquet),
            }
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    feature_requests = [
        ("close_to_ma120", "RAW", True, 120),
        ("n60_first_cross", "RAW", True, 62),
        ("prior20_amount_twd", "RAW", True, 21),
        ("ma120_state", "METADATA", False, None),
        ("n60_state", "METADATA", False, None),
        ("prior20_amount_state", "METADATA", False, None),
        ("formula_version", "METADATA", False, None),
        ("price_coordinate", "METADATA", False, None),
    ]
    config = {
        "schema_version": "1",
        "name": "causal_raw_v2_fixture",
        "epoch": "E1",
        "artifact": {
            "manifest_path": str(manifest_path),
            "artifact_name": "causal-raw-v2-fixture",
            "source_revision": "fixture-source",
            "formula_version": FORMULA_VERSION,
            "epoch": "E1",
        },
        "policy": {"strategy_required_status": "VERIFIED"},
        "availability_groups": {
            "synthetic_verified": {"status": "VERIFIED"},
        },
        "requested_features": [
            {
                "column": column,
                "kind": kind,
                "required": required,
                "warmup_sessions": warmup,
                "dependencies": ["synthetic_verified"],
                "expected_status": "VERIFIED",
            }
            for column, kind, required, warmup in feature_requests
        ],
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=Falsi, encoding="utf-8")
    panel = raw [["date", "stock_id", "decision_cutoff_at"]].rename(
        columns={"decision_cutoff_at": "__decision_cutoff_at"}
    )
    return config_path, manifest_path, root, panel


def test_v2_artifact_hydrates_version_coordinate_and_explicit_states(tmp_path):
    config_path, manifest_path, root, panel = _fixture(tmp_path)
    result = FeaturePanelIntegrator(
        config=load_feature_panel_integration_config(config_path),
        artifact_root=root,
        manifest_path=manifest_path,
    ).hydrate(panel)

    assert len(result.frame) == len(panel)
    assert result.manifest["formula_version"] == FORMULA_VERSION
    assert result.manifest["source_revision"] == "fixture-source"
    assert set(result.frame["formula_version"].dropna()) == {FORMULA_VERSION}
    assert set(result.frame["price_coordinate"].dropna()) == {PRICE_COORDINATE}

    assert result.frame.loc[118, "ma120_state"] == "WARMUP_INSUFFICIENT"
    assert result.frame.loc[118, "__feature_missing_reason__close_to_ma120"] == "WARMUP_INSUFFICIENT"
    assert result.frame.loc[119, "ma120_state"] == "READY"
    assert result.frame.loc[119, "__feature_missing_reason__close_to_ma120"] == ""

    assert result.frame.loc[60, "n60_state"] == "WARMUP_INSUFFICIENT"
    assert result.frame.loc[60, "__feature_missing_reason__n60_first_cross"] == "WARMUP_INSUFFICIENT"
    assert result.frame.loc[61, "n60_state"] == "READY"

    assert result.frame.loc[19, "prior20_amount_state"] == "WARMUP_INSUFFICIENT"
    assert result.frame.loc[19, "__feature_missing_reason__prior20_amount_twd"] == "WARMUP_INSUFFICIENT"
    assert result.frame.loc[20, "prior20_amount_state"] == "READY"
    assert result.frame.loc[20, "prior20_amount_twd"] == pytest.approx(30_000_000.0)


def test_v2_hydration_rejects_source_available_at_equal_to_cutoff(tmp_path):
    config_path, manifest_path, root, panel = _fixture(tmp_path, late_source=True)
    with pytest.raises(
        FeaturePanelIntegrationError,
        match="not available before decision cutoff",
    ):
        FeaturePanelIntegrator(
            config=load_feature_panel_integration_config(config_path),
            artifact_root=root,
            manifest_path=manifest_path,
        ).hydrate(panel)


def test_v2_hydration_rejects_e2_key_before_artifact_read(tmp_path):
    config_path, manifest_path, root, _ = _fixture(tmp_path)
    panel = pd.DataFrame(
        {
            "date": [pd.Timestamp("2022-01-03")],
            "stock_id": ["2330"],
            "__decision_cutoff_at": [pd.Timestamp("2022-01-04 08:45:00")],
        }
    )
    with pytest.raises(FeaturePanelIntegrationError, match="E1-only"):
        FeaturePanelIntegrator(
            config=load_feature_panel_integration_config(config_path),
            artifact_root=root / "does-not-exist",
            manifest_path=manifest_path,
        ).hydrate(panel)
