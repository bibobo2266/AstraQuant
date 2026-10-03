import numpy as np
import pandas as pd
import pytest

from astraquant.research.causal_raw_v2 import (
    CausalRawV2Error,
    build_causal_raw_v2_features,
    normalize_event_groups,
    raw_universe_panel,
)


def _panel(n=140, *, start="2020-01-02", close=100.0, amount=30_000_000.0):
    dates = pd.bdate_range(start, periods=n)
    return pd.DataFrame(
        {
            "date": dates,
            "stock_id": ["2330"] * n,
            "raw_close": np.full(n, close, dtype=float),
            "Trading_money": np.full(n, amount, dtype=float),
            "observed_trade": True,
            "valid_ohlc": True,
            "decision_cutoff_at": dates + pd.Timedelta(days=1),
        }
    )


def _events(rows):
    return pd.DataFrame(rows, columns=[
        "stock_id", "effective_date", "event_kind", "known_at",
        "cash_per_share", "share_multiplier",
    ])


def test_future_event_does_not_rewrite_earlier_feature_rows():
    p = _panel(150)
    event_date = p.loc[130, "date"]
    known = p.loc[100, "date"] + pd.Timedelta(hours=10)
    future = _events([["2330", event_date, "CASH_DIVIDEND", known, 5.0, np.nan]])

    base = build_causal_raw_v2_features(p, _events([]))
    changed = build_causal_raw_v2_features(p, future)

    cols = ["close_to_ma120", "prior_high60", "n60_first_cross", "coordinate_status"]
    pd.testing.assert_frame_equal(
        base.loc[:129, cols], changed.loc[:129, cols], check_dtype=False
    )


def test_no_market_date_event_is_applied_once_on_next_session_without_rounding():
    p = _panel(140)
    friday = p.loc[121, "date"]
    assert friday.dayofweek == 4
    saturday = friday + pd.Timedelta(days=1)
    monday = p.loc[122, "date"]
    assert monday.dayofweek == 0
    p.loc[p.index >= 122, "raw_close"] = 94.87654321
    e = _events([["2330", saturday, "CASH_DIVIDEND", friday, 5.12345679, np.nan]])

    out = build_causal_raw_v2_features(p, e)

    assert out.loc[122, "event_groups_applied"] == 1
    assert out.loc[123, "event_groups_applied"] == 0
    assert out.loc[123, "event_groups_applied_cumulative"] == 1
    assert out.loc[122, "ma120"] == pytest.approx(94.87654321, abs=1e-12)
    assert out.loc[122, "close_to_ma120"] == pytest.approx(0.0, abs=1e-12)


def test_cash_and_stock_same_date_use_one_same_coordinate_transform():
    p = _panel(140)
    event_date = p.loc[125, "date"]
    p.loc[p.index >= 125, "raw_close"] = 45.0
    e = _events([
        ["2330", event_date, "CASH_DIVIDEND", p.loc[100, "date"], 10.0, np.nan],
        ["2330", event_date, "STOCK_DIVIDEND", p.loc[100, "date"], np.nan, 2.0],
    ])
    grouped = normalize_event_groups(e)
    assert grouped.loc[0, "cash_per_share"] == 10.0
    assert grouped.loc[0, "share_multiplier"] == 2.0

    out = build_causal_raw_v2_features(p, e)
    assert out.loc[125, "ma120"] == pytest.approx(45.0)
    assert out.loc[125, "close_to_ma120"] == pytest.approx(0.0)


def test_effective_but_not_known_blocks_then_resumes_without_mixed_window():
    p = _panel(140)
    event_date = p.loc[120, "date"]
    known_at = p.loc[124, "date"] + pd.Timedelta(hours=12)
    p.loc[p.index >= 120, "raw_close"] = 95.0
    e = _events([["2330", event_date, "CASH_DIVIDEND", known_at, 5.0, np.nan]])

    out = build_causal_raw_v2_features(p, e)

    for i in range(120, 124):
        assert out.loc[i, "coordinate_status"] == "EVENT_NOT_YET_KNOWN"
        assert out.loc[i, "ma120_state"] == "CA_COORDINATE_BLOCKED"
        assert pd.isna(out.loc[i, "n60_first_cross"])
    assert out.loc[124, "coordinate_status"] == "READY"
    assert out.loc[124, "event_groups_applied"] == 1
    assert out.loc[124, "ma120"] == pytest.approx(95.0)


def test_unknown_known_at_fails_closed_after_effective_date():
    p = _panel(130)
    event_date = p.loc[120, "date"]
    e = _events([["2330", event_date, "CASH_DIVIDEND", pd.NaT, 5.0, np.nan]])
    out = build_causal_raw_v2_features(p, e)
    assert out.loc[119, "coordinate_status"] == "READY"
    assert out.loc[120, "coordinate_status"] == "EVENT_KNOWN_AT_UNKNOWN"
    assert out.loc[120, "ma120_state"] == "CA_COORDINATE_BLOCKED"


def test_n60_is_nullable_for_warmup_and_missing_not_false():
    p = _panel(80)
    out = build_causal_raw_v2_features(p, _events([]))
    assert out.loc[60, "n60_state"] == "WARMUP_INSUFFICIENT"
    assert pd.isna(out.loc[60, "n60_first_cross"])
    assert out.loc[61, "n60_state"] == "READY"
    assert bool(out.loc[61, "n60_first_cross"]) is False

    p2 = p.copy()
    p2.loc[50, ["raw_close", "Trading_money"]] = np.nan
    p2.loc[50, ["observed_trade", "valid_ohlc"]] = False
    out2 = build_causal_raw_v2_features(p2, _events([]))
    assert out2.loc[61, "n60_state"] == "INPUT_MISSING"
    assert pd.isna(out2.loc[61, "n60_first_cross"])


def test_n60_strict_first_cross_matches_existing_contract():
    p = _panel(80)
    p.loc[61, "raw_close"] = 101.0
    out = build_causal_raw_v2_features(p, _events([]))
    assert bool(out.loc[61, "n60_first_cross"]) is True
    p_equal = _panel(80)
    p_equal.loc[61, "raw_close"] = 100.0
    equal = build_causal_raw_v2_features(p_equal, _events([]))
    assert bool(equal.loc[61, "n60_first_cross"]) is False


def test_prior20_amount_uses_only_prior_common_session_rows():
    p = _panel(30)
    p.loc[20, "Trading_money"] = 9_999_999_999.0
    out = build_causal_raw_v2_features(p, _events([]))
    assert out.loc[19, "prior20_amount_state"] == "WARMUP_INSUFFICIENT"
    assert out.loc[20, "prior20_amount_twd"] == pytest.approx(30_000_000.0)
    p.loc[10, "Trading_money"] = np.nan
    out2 = build_causal_raw_v2_features(p, _events([]))
    assert out2.loc[20, "prior20_amount_state"] == "INPUT_MISSING"
    assert pd.isna(out2.loc[20, "prior20_amount_twd"])


def test_raw_absolute_close_is_the_universe_qualification_coordinate():
    p = _panel(2)
    p.loc[0, "raw_close"] = 9.99
    p.loc[1, "raw_close"] = 10.0
    u = raw_universe_panel(p.drop(columns="decision_cutoff_at"))
    assert u["close"].tolist() == [9.99, 10.0]


def test_unsupported_event_kind_and_missing_cutoff_fail_closed():
    p = _panel(2)
    bad = _events([["2330", p.loc[1, "date"], "SPLIT", p.loc[0, "date"], 0.0, 2.0]])
    with pytest.raises(CausalRawV2Error, match="unsupported event_kind"):
        build_causal_raw_v2_features(p, bad)

    with pytest.raises(CausalRawV2Error, match="decision_cutoff_at"):
        build_causal_raw_v2_features(p.drop(columns="decision_cutoff_at"), _events([]))


def test_earlier_unresolved_event_prevents_later_event_from_applying_out_of_order():
    p = _panel(140)
    first = p.loc[120, "date"]
    second = p.loc[121, "date"]
    e = _events([
        ["2330", first, "CASH_DIVIDEND", pd.NaT, 5.0, np.nan],
        ["2330", second, "CASH_DIVIDEND", p.loc[100, "date"], 2.0, np.nan],
    ])
    out = build_causal_raw_v2_features(p, e)
    assert out.loc[121, "coordinate_status"] == "EVENT_KNOWN_AT_UNKNOWN"
    assert out.loc[121, "event_groups_applied_cumulative"] == 0


def test_known_at_equal_to_decision_cutoff_is_not_treated_as_available():
    p = _panel(130)
    event_date = p.loc[120, "date"]
    cutoff = p.loc[120, "decision_cutoff_at"]
    e = _events([["2330", event_date, "CASH_DIVIDEND", cutoff, 5.0, np.nan]])
    out = build_causal_raw_v2_features(p, e)
    assert out.loc[120, "coordinate_status"] == "EVENT_NOT_YET_KNOWN"


def test_frozen_v2_parameters_reject_unapproved_drift():
    from astraquant.research.causal_raw_v2 import CausalRawV2Parameters
    with pytest.raises(CausalRawV2Error, match="frozen"):
        CausalRawV2Parameters(ma_window=119)


def test_quality_contract_freezes_same_windows_and_keeps_gate_blocked():
    from pathlib import Path
    import yaml

    path = Path(__file__).parents[1] / "configs/quality/layer1_60d_ma120_causal_raw_v2.yaml"
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert cfg["frozen_parameters"] == {
        "ma_window": 120,
        "breakout_lookback": 60,
        "liquidity_lookback": 20,
    }
    assert cfg["price_coordinates"]["eligibility_absolute_price"] == "RAW_EXECUTION"
    assert cfg["rolling_contract"]["n60_missing"] == "nullable_not_false"
    assert cfg["availability_gate"]["current_result"] == "BLOCKED"
    statuses = {
        item["status"]
        for item in cfg["availability_gate"]["dependencies"].values()
    }
    assert statuses <= {"UNKNOWN", "UNAVAILABLE"}
    assert cfg["artifact_policy"]["current_formal_artifact"] is None
