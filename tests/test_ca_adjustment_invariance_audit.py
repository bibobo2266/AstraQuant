from __future__ import annotations

import numpy as np
import pandas as pd

from astraquant.research.ca_adjustment_audit import (
    BOUNDARY_BAND,
    RATIO_HI,
    RATIO_LO,
    current_price_feature_frame,
    future_factor_for_rows,
    normalize_dividend_events,
    online_asof_price_features,
    rebuild_final_adjusted_close,
    synthetic_uniform_scale_case,
    universe_masks,
)

NO_EVENTS = pd.DataFrame(
    {
        "stock_id": pd.Series(dtype=str),
        "date": pd.Series(dtype="datetime64[ns]"),
        "ratio": pd.Series(dtype=float),
    }
)


def _rows(stock_id, close, start="2020-01-01"):
    dates = pd.bdate_range(start, periods=len(close))
    return pd.DataFrame(
        {"date": dates, "stock_id": stock_id, "close": np.asarray(close, dtype=float)}
    )


def _online_rows(stock_id, raw_close, start="2020-01-01"):
    dates = pd.bdate_range(start, periods=len(raw_close))
    return pd.DataFrame(
        {"date": dates, "stock_id": stock_id, "raw_close": np.asarray(raw_close, dtype=float)}
    )


def _events(**cols):
    return normalize_dividend_events(pd.DataFrame(cols))


def _features(close, stock_id="2330"):
    frame = _rows(stock_id, close)
    return current_price_feature_frame(frame, future_factor=np.ones(len(frame)))

def test_uniform_positive_scale_preserves_ma120_and_n60_but_not_absolute_gate():
    out = synthetic_uniform_scale_case()
    assert out["max_ma120_abs_diff"] < 1e-12
    assert out["ma120_gate_flips"] == 0
    assert out["n60_flips"] == 0
    assert out["absolute_close_threshold_flips"] is True

def test_event_on_t_is_not_a_future_factor_and_same_day_events_multiply():
    events = normalize_dividend_events(pd.DataFrame({
        "date":["2020-02-01","2020-02-01","2020-03-01"],
        "stock_id":["2330","2330","2330"],
        "before_price":[100,100,100],
        "after_price":[90,80,50],
    }))
    # 0.5 is accepted; same-day product is 0.72.
    assert len(events) == 2
    rows = pd.DataFrame({"date":pd.to_datetime(["2020-02-01","2020-02-29"]), "stock_id":["2330","2330"]})
    f = future_factor_for_rows(rows, events)
    assert np.isclose(f[0], 0.5)
    assert np.isclose(f[1], 0.5)

def test_factor_only_strict_breakout_has_no_tolerance_flip():
    dates = pd.bdate_range("2020-01-01", periods=130)
    close = np.arange(1,131,dtype=float)
    panel = pd.DataFrame({"date":dates,"stock_id":"2330","close":close})
    events = normalize_dividend_events(pd.DataFrame({
        "date":[dates[-1] + pd.Timedelta(days=10)],"stock_id":["2330"],
        "before_price":[100.0],"after_price":[80.0],
    }))
    scaled = panel.copy()
    scaled["close"] *= 0.8
    f = future_factor_for_rows(scaled,events)
    result = current_price_feature_frame(scaled,future_factor=f)
    assert not result["ma120_gate_flip"].any()
    assert not result["n60_flip"].any()

def test_online_event_day_scales_history_before_appending_current_raw():
    dates = pd.bdate_range("2020-01-01", periods=125)
    raw = pd.DataFrame({"date":dates,"stock_id":"2330","raw_close":np.linspace(100,124,125)})
    event_day = dates[120]
    events = normalize_dividend_events(pd.DataFrame({
        "date":[event_day],"stock_id":["2330"],"before_price":[100.0],"after_price":[50.0],
    }))
    out = online_asof_price_features(raw,events)
    # The event-day ratio applies to previous history, while event-day raw is appended unscaled.
    assert out.loc[120,"close_to_ma120_online_asof"] > 0

def test_raw_close_threshold_can_change_final_turnover_membership():
    frame = pd.DataFrame({
        "date":pd.to_datetime(["2020-01-02"]*4),
        "stock_id":["1101","1102","1103","1104"],
        "adjusted_close":[9.0,20.0,20.0,20.0],
        "raw_close":[11.0,20.0,20.0,20.0],
        "Trading_money":[1000.0,900.0,800.0,700.0],
        "observed_trade":[True]*4,"valid_ohlc":[True]*4,
    })
    u = universe_masks(frame,excluded=set(),turnover_top_fraction=0.25)
    assert not bool(u.loc[u.stock_id.eq("1101"),"adjusted_base_pass"].iloc[0])
    assert bool(u.loc[u.stock_id.eq("1101"),"raw_base_pass"].iloc[0])
    assert bool((u["adjusted_counts"] != u["raw_counts"]).any())


def test_factor_alignment_survives_unsorted_input():
    rows = pd.DataFrame({
        "date": pd.to_datetime(["2020-01-03", "2020-01-02", "2020-01-06"]),
        "stock_id": ["2330", "2317", "2330"],
        "close": [30.0, 20.0, 31.0],
    })
    factors = np.array([0.8, 0.9, 0.8])
    out = current_price_feature_frame(rows, future_factor=factors)
    got = {
        (str(r.stock_id), pd.Timestamp(r.date)): float(r.future_factor)
        for r in out.itertuples(index=False)
    }
    assert got[("2330", pd.Timestamp("2020-01-03"))] == 0.8
    assert got[("2317", pd.Timestamp("2020-01-02"))] == 0.9
    assert got[("2330", pd.Timestamp("2020-01-06"))] == 0.8


# ==========================================================================
# 以下為 2026-09-30 依審查端裁定補齊的性質。
# 舊的 tests/test_ca_adjustment_audit.py 是前一版設計的殘留（import 六個模組
# 不存在的名稱，導致 collection error），已刪除；其涵蓋的性質由本檔承接。
# 裁定：以模組實際呼叫契約為準，不新增相容 wrapper，不為測試通過改訊號門檻。
# ==========================================================================


# -- 突破邊界：保留正式的 > 與 <=，不得用近似比較改寫交易判定 ----------------

def test_breakout_requires_strictly_greater_than_prior_high():
    out = _features([10.0] * 60 + [12.0] + [10.0] * 59 + [12.0])
    last = out.iloc[-1]
    assert float(last["prior_high60_current"]) == 12.0
    # 恰好等於前高：嚴格 > 為假。
    assert bool(last["n60_current"]) is False


def test_breakout_fires_on_first_cross_only_and_not_while_already_above():
    # 需 61 列暖機：previous_prior 是 prior_high60 再 shift(1)，比 prior_high60 晚一天成立。
    out = _features([10.0] * 61 + [15.0, 16.0, 17.0])
    assert out["n60_current"].to_numpy()[-3:].tolist() == [True, False, False]


def test_breakout_and_gate_are_false_during_warmup():
    out = _features(list(np.linspace(10.0, 20.0, 40)))
    assert not out["n60_current"].any()
    assert not out["n60_comparable"].any()


def test_missing_close_does_not_fabricate_a_breakout_or_gate():
    out = _features([10.0] * 60 + [np.nan, 11.0])
    row = out.iloc[60]
    assert bool(row["n60_current"]) is False
    assert bool(row["ma120_gate_current"]) is False
    assert not bool(row["ma120_comparable"])


def test_near_boundary_is_only_a_flag_and_does_not_change_the_decision():
    out = _features([10.0] * 61 + [10.0 * (1.0 + BOUNDARY_BAND / 2.0)])
    last = out.iloc[-1]
    assert bool(last["n60_near_boundary"]) is True
    assert bool(last["n60_current"]) is True


# -- 事件處理 ---------------------------------------------------------------

def test_events_outside_the_source_ratio_range_are_dropped():
    got = normalize_dividend_events(
        pd.DataFrame(
            {
                "date": ["2020-01-03", "2020-01-06", "2020-01-07", "bad", "2020-01-08"],
                "stock_id": ["2330"] * 5,
                "before_price": [100, 100, 100, 100, 0],
                "after_price": [90, 40, 130, 90, 90],
            }
        )
    )
    assert len(got) == 1
    assert RATIO_LO <= float(got.iloc[0]["ratio"]) <= RATIO_HI


def test_no_events_means_factor_is_exactly_one():
    rows = _rows("2330", [10.0] * 5)
    np.testing.assert_array_equal(future_factor_for_rows(rows, NO_EVENTS), np.ones(5))


def test_an_event_on_one_stock_never_touches_another():
    rows = pd.concat(
        [_rows("2330", [10.0] * 5), _rows("2454", [10.0] * 5)], ignore_index=True
    )
    ev = _events(
        date=[rows["date"].iloc[2]], stock_id=["2330"],
        before_price=[100.0], after_price=[80.0],
    )
    ff = future_factor_for_rows(rows, ev)
    np.testing.assert_allclose(ff[:5], [0.8, 0.8, 1.0, 1.0, 1.0])
    np.testing.assert_array_equal(ff[5:], np.ones(5))


# -- 逐時重建：T 後新增的事件不得改變 T 及以前的輸出 ------------------------

def test_events_after_t_do_not_change_online_output_at_or_before_t():
    rows = _online_rows("2330", np.linspace(20.0, 30.0, 200))
    cut = rows["date"].iloc[150]
    ev = _events(
        date=[rows["date"].iloc[180]], stock_id=["2330"],
        before_price=[100.0], after_price=[80.0],
    )
    without = online_asof_price_features(rows, NO_EVENTS)
    with_future = online_asof_price_features(rows, ev)
    upto = with_future["date"].le(cut)
    np.testing.assert_allclose(
        without.loc[upto, "close_to_ma120_online_asof"].to_numpy(float),
        with_future.loc[upto, "close_to_ma120_online_asof"].to_numpy(float),
        rtol=0.0, atol=0.0, equal_nan=True,
    )
    assert without.loc[upto, "n60_online_asof"].equals(
        with_future.loc[upto, "n60_online_asof"]
    )


def test_an_event_dated_on_a_day_without_a_price_row_is_not_silently_dropped():
    rows = _rows("2330", [10.0] * 6)
    gap_day = rows["date"].iloc[3]
    rows = rows.drop(index=3).reset_index(drop=True)
    ev = _events(
        date=[gap_day], stock_id=["2330"], before_price=[100.0], after_price=[80.0]
    )
    ff = future_factor_for_rows(rows, ev)
    assert len(ff) == len(rows)
    # 事件日之前的列仍被縮放；事件日無行情列不會讓該事件失效。
    np.testing.assert_allclose(ff, [0.8, 0.8, 0.8, 1.0, 1.0])


def test_missing_raw_close_is_reported_separately_from_a_price_condition():
    rows = _online_rows("2330", [10.0] * 3 + [np.nan] + [10.0] * 2)
    out = online_asof_price_features(rows, NO_EVENTS)
    assert bool(out.iloc[3]["raw_close_missing"]) is True
    assert bool(out.iloc[3]["ma120_gate_online_asof"]) is False


# -- 四捨五入：比較兩種重建，不強迫相等 --------------------------------------

def test_round_once_and_sequential_round_are_compared_not_forced_equal():
    rows = _online_rows("2330", np.linspace(20.0, 35.0, 40))
    d = rows["date"]
    ev = _events(
        date=[d.iloc[10], d.iloc[20], d.iloc[30]],
        stock_id=["2330"] * 3,
        before_price=[100.0] * 3,
        after_price=[83.0, 91.0, 77.0],
    )
    out = rebuild_final_adjusted_close(rows, ev)
    once = out["rebuild_round_once"].to_numpy(float)
    seq = out["rebuild_sequential_round4"].to_numpy(float)
    assert once.shape == seq.shape
    assert np.isfinite(once).all() and np.isfinite(seq).all()
    # 兩者不主張相等；差異本身就是稽核要回報的量，此處只界定量級。
    assert np.abs(once - seq).max() < 1.0


# -- 可比較樣本：暖機不足造成的 False 不得計為翻轉 --------------------------

def test_warmup_rows_are_not_comparable_and_are_not_counted_as_flips():
    out = _features(np.linspace(10.0, 20.0, 130))
    assert not out["ma120_comparable"].iloc[:119].any()
    assert out["ma120_comparable"].iloc[119:].all()
    assert not out["ma120_gate_flip"].iloc[:119].any()


def test_a_non_positive_factor_makes_the_row_not_comparable():
    frame = _rows("2330", np.linspace(10.0, 20.0, 130))
    ff = np.ones(len(frame))
    ff[125] = 0.0
    out = current_price_feature_frame(frame, future_factor=ff)
    assert not bool(out.iloc[125]["n60_comparable"])


# -- 母體：與 universe_engine 的排序、同值與缺值語意對照 ---------------------

def _universe_frame():
    day = pd.Timestamp("2021-06-01")
    return pd.DataFrame(
        {
            "date": [day] * 4,
            "stock_id": ["2330", "2454", "1301", "1303"],
            "adjusted_close": [50.0, 9.5, 20.0, 30.0],
            "raw_close": [50.0, 10.5, 20.0, 30.0],
            "Trading_money": [400.0, 300.0, 200.0, 200.0],
            "observed_trade": [True] * 4,
            "valid_ohlc": [True] * 4,
        }
    )


def test_turnover_ranking_matches_universe_engine_semantics():
    frame = _universe_frame()
    out = universe_masks(frame, excluded=set())
    base = out["adjusted_base_pass"]
    # 與 universe_engine._all_pool 相同：pct=True, ascending=False, method="average"
    expected = (
        frame["Trading_money"].where(base)
        .groupby(frame["date"])
        .rank(pct=True, ascending=False, method="average")
    )
    pd.testing.assert_series_equal(
        out["adjusted_turnover_pct"], expected, check_names=False
    )
    # 同值取平均名次；未通過 base 的列 pct 為 NaN 且不得算入。
    tie = out[out["stock_id"].isin(["1301", "1303"])]["adjusted_turnover_pct"]
    assert tie.nunique() == 1
    assert out.loc[~base, "adjusted_turnover_pct"].isna().all()
    assert not out.loc[~base, "adjusted_counts"].any()


def test_excluded_and_malformed_ids_never_enter_the_base():
    frame = _universe_frame()
    frame.loc[len(frame)] = {
        "date": frame["date"].iloc[0], "stock_id": "00878",
        "adjusted_close": 20.0, "raw_close": 20.0, "Trading_money": 999.0,
        "observed_trade": True, "valid_ohlc": True,
    }
    out = universe_masks(frame, excluded={"1301"})
    assert not bool(out[out["stock_id"] == "00878"].iloc[0]["fixed_other_qualifiers"])
    assert not bool(out[out["stock_id"] == "1301"].iloc[0]["fixed_other_qualifiers"])


# -- 多股票與列順序 ----------------------------------------------------------

def test_two_stocks_do_not_contaminate_each_others_rolling_windows():
    rows = pd.concat(
        [_rows("2330", [10.0] * 61 + [15.0]), _rows("2454", [100.0] * 61 + [1.0])],
        ignore_index=True,
    )
    out = current_price_feature_frame(rows, future_factor=np.ones(len(rows)))
    a = out[out["stock_id"] == "2330"].reset_index(drop=True)
    b = out[out["stock_id"] == "2454"].reset_index(drop=True)
    assert bool(a.iloc[61]["n60_current"]) is True
    assert bool(b.iloc[61]["n60_current"]) is False
    assert float(a.iloc[61]["prior_high60_current"]) == 10.0
    assert float(b.iloc[61]["prior_high60_current"]) == 100.0


def test_shuffled_rows_keep_each_factor_bound_to_its_stock_day():
    rows = pd.concat(
        [_rows("2330", [10.0] * 6), _rows("2454", [20.0] * 6)], ignore_index=True
    )
    ev = _events(
        date=[rows["date"].iloc[3]], stock_id=["2330"],
        before_price=[100.0], after_price=[80.0],
    )
    ordered = current_price_feature_frame(
        rows, future_factor=future_factor_for_rows(rows, ev)
    )
    shuffled = rows.sample(frac=1.0, random_state=7).reset_index(drop=True)
    shuffled_out = current_price_feature_frame(
        shuffled, future_factor=future_factor_for_rows(shuffled, ev)
    )
    key = ["stock_id", "date"]
    pd.testing.assert_frame_equal(
        ordered.sort_values(key).reset_index(drop=True)[key + ["close", "future_factor"]],
        shuffled_out.sort_values(key).reset_index(drop=True)[key + ["close", "future_factor"]],
    )


# ==========================================================================
# 2026-09-30 第二輪：審查端指出前一輪的測試打到錯誤路徑。
# 「事件日無行情列」原測 future_factor_for_rows（本來就用區間遮罩，測不到問題），
# 真正會漏事件的是 online_asof_price_features 的逐日重建。以下直接打正式路徑。
# ==========================================================================


def _online_with_gap_event(ratio_after=50.0):
    dates = pd.bdate_range("2020-01-01", periods=130)
    rows = pd.DataFrame(
        {"date": dates, "stock_id": "2330", "raw_close": np.linspace(100.0, 130.0, 130)}
    )
    friday = next(d for d in dates[120:] if d.weekday() == 4)
    saturday = friday + pd.Timedelta(days=1)
    assert not (rows["date"] == saturday).any()
    ev = _events(
        date=[saturday], stock_id=["2330"],
        before_price=[100.0], after_price=[ratio_after],
    )
    return rows, ev, saturday


def test_online_rebuild_applies_an_event_dated_on_a_day_with_no_price_row():
    rows, ev, _ = _online_with_gap_event()
    with_event = online_asof_price_features(rows, ev)
    without = online_asof_price_features(rows, NO_EVENTS)
    changed = not np.allclose(
        with_event["close_to_ma120_online_asof"].to_numpy(float),
        without["close_to_ma120_online_asof"].to_numpy(float),
        equal_nan=True,
    )
    assert changed, "非交易日的事件被靜默漏掉"
    assert int(with_event["events_applied_online"].sum()) == 1


def test_online_and_rebuild_agree_on_which_rows_an_event_touches():
    rows, ev, saturday = _online_with_gap_event()
    rebuilt = rebuild_final_adjusted_close(rows, ev)
    # rebuild 用 date < event.date；online 現在採同一語意，兩者對「哪些列被調整」必須一致。
    touched = rebuilt["future_factor"].to_numpy(float) < 1.0
    expected = (rows["date"] < saturday).to_numpy()
    np.testing.assert_array_equal(touched, expected)


def test_online_applies_multiple_events_in_source_order_each_once():
    dates = pd.bdate_range("2020-01-01", periods=140)
    rows = pd.DataFrame(
        {"date": dates, "stock_id": "2330", "raw_close": np.linspace(100.0, 140.0, 140)}
    )
    ev = _events(
        date=[dates[125], dates[130], dates[135]],
        stock_id=["2330"] * 3,
        before_price=[100.0] * 3,
        after_price=[90.0, 80.0, 70.0],
    )
    out = online_asof_price_features(rows, ev)
    # 三個事件各套一次，不多不少。
    assert int(out["events_applied_online"].sum()) == 3
    applied = out.set_index("date")["events_applied_online"]
    assert applied.loc[dates[125]] == 1
    assert applied.loc[dates[130]] == 1
    assert applied.loc[dates[135]] == 1


def test_online_marks_short_history_as_not_comparable_instead_of_false_signal():
    rows = _online_rows("2330", np.linspace(20.0, 30.0, 80))
    out = online_asof_price_features(rows, NO_EVENTS)
    # 前 61 列歷史不足，N60 不可比較；MA120 需 120 列，全程不可比較。
    assert not out["n60_comparable_online"].iloc[:61].any()
    assert out["n60_comparable_online"].iloc[61:].all()
    assert not out["ma120_comparable_online"].any()
    # 不可比較處的 n60 為 False，但那是算不出來，不是觀測到沒突破。
    assert not out["n60_online_asof"].iloc[:61].any()


def test_online_nan_in_history_breaks_comparability_until_the_window_clears():
    raw = np.linspace(20.0, 40.0, 140)
    raw[70] = np.nan
    out = online_asof_price_features(_online_rows("2330", raw), NO_EVENTS)
    assert bool(out.iloc[70]["raw_close_missing"]) is True
    # NaN 落在視窗內時不可比較；視窗滑過之後恢復。
    assert not bool(out.iloc[75]["n60_comparable_online"])
    assert bool(out.iloc[135]["n60_comparable_online"])


def test_online_reports_a_normal_non_breakout_as_comparable_and_false():
    # 正常、資料完整、確實沒有突破：必須是「可比較且為 False」，
    # 與「不可比較的 False」區分得開。
    out = online_asof_price_features(_online_rows("2330", [10.0] * 130), NO_EVENTS)
    last = out.iloc[-1]
    assert bool(last["n60_comparable_online"]) is True
    assert bool(last["n60_online_asof"]) is False
