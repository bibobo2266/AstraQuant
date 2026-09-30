from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from astraquant.research.technical_components import column_threshold
from astraquant.research.strategy_config import ComponentSpec
from pit_feature_matrix_layer1_review import combine_status, stable_stratified_sample


def test_stratified_sampler_cannot_spend_all_quota_on_first_year():
    rows = []
    for year in range(2016, 2022):
        for i in range(20):
            rows.append({
                "year": year,
                "date": pd.Timestamp(year=year, month=1, day=1) + pd.Timedelta(days=i),
                "stock_id": f"{year}-{i:02d}",
            })
    frame = pd.DataFrame(rows)
    sample = stable_stratified_sample(
        frame,
        year_col="year",
        per_year=5,
        seed=20260930,
        id_cols=["date", "stock_id"],
        years=list(range(2016, 2022)),
    )
    counts = sample.groupby("year").size().to_dict()
    assert counts == {year: 5 for year in range(2016, 2022)}
    assert len(sample) == 30


def test_unknown_availability_is_never_promoted_to_pass():
    assert combine_status(["PASS"]) == "PASS"
    assert combine_status(["PASS", "UNKNOWN"]) == "UNKNOWN"
    assert combine_status(["UNKNOWN"]) == "UNKNOWN"
    assert combine_status(["PASS", "FAIL"]) == "FAIL"


def test_ma120_ratio_threshold_is_zero_not_one():
    panel = pd.DataFrame({
        "close_to_ma120": [-0.01, 0.0, 0.02, pd.NA],
    })
    result = column_threshold(
        panel=panel,
        spec=ComponentSpec(
            type="COLUMN_THRESHOLD",
            params={"column": "close_to_ma120", "min": 0.0},
        ),
        cache=None,
        context=None,
    )
    assert result.tolist() == [False, True, True, False]
