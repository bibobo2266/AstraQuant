import pandas as pd
import pytest

from astraquant.research.outcomes import (
    build_forward_outcomes_with_cross_sectional_demean,
)


def _panel():
    rows = []
    dates = pd.to_datetime(["2026-01-02", "2026-01-05"])
    for ticker, p0, p1 in [
        ("1101", 100.0, 110.0),
        ("1102", 100.0, 120.0),
        ("1103", 100.0, 90.0),
    ]:
        rows += [
            {
                "date": dates[0],
                "stock_id": ticker,
                "close": p0,
                "observed_trade": True,
                "valid_ohlc": True,
            },
            {
                "date": dates[1],
                "stock_id": ticker,
                "close": p1,
                "observed_trade": True,
                "valid_ohlc": True,
            },
        ]
    return pd.DataFrame(rows)


def test_demeaned_forward_return_uses_same_day_common_support_mean():
    out = build_forward_outcomes_with_cross_sectional_demean(
        _panel(),
        excluded_tickers=set(),
        forward_sessions=1,
        min_cross_section=3,
    )
    day = out[out["date"].eq(pd.Timestamp("2026-01-02"))].set_index("stock_id")
    mean = (0.10 + 0.20 - 0.10) / 3.0
    assert day.loc["1101", "demean_cross_section_mean"] == pytest.approx(mean)
    assert day.loc["1101", "demeaned_forward_return"] == pytest.approx(0.10 - mean)
    assert day["demeaned_forward_return"].sum() == pytest.approx(0.0)
    assert day["demean_cross_section_count"].nunique() == 1
    assert int(day["demean_cross_section_count"].iloc[0]) == 3


def test_demean_exclusion_set_changes_mean_but_preserves_absolute_return():
    out = build_forward_outcomes_with_cross_sectional_demean(
        _panel(),
        excluded_tickers={"1102"},
        forward_sessions=1,
        min_cross_section=2,
    )
    day = out[out["date"].eq(pd.Timestamp("2026-01-02"))].set_index("stock_id")
    assert day.loc["1101", "forward_return"] == pytest.approx(0.10)
    assert day.loc["1101", "demean_cross_section_mean"] == pytest.approx(0.0)
    assert int(day.loc["1101", "demean_cross_section_count"]) == 2


def test_demeaned_outcome_is_missing_below_minimum_cross_section():
    out = build_forward_outcomes_with_cross_sectional_demean(
        _panel(),
        excluded_tickers=set(),
        forward_sessions=1,
        min_cross_section=4,
    )
    day = out[out["date"].eq(pd.Timestamp("2026-01-02"))]
    assert day["forward_return"].notna().all()
    assert day["demeaned_forward_return"].isna().all()
