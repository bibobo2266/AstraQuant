"""AQ-EXP-CAL-001 — 共同日曆完整性。

公開部分只驗聚合檔自洽；真實掃描與缺日模擬需要固定 source 與 producer，缺則 skip。
缺日那一支同時是回歸閘門：日曆前提若被打破，它會紅。

資料層診斷，不含勝率／賠率／每筆期望值。
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "out" / "aq_exp_cal_001_calendar_completeness.json"
R2_MANIFEST = ROOT / "out" / "aq_exp_data_001_r2_manifest.json"

UNIVERSE_ROWS = 458315
UNIVERSE_STOCKS = 1394
ALL_FOUR = 428102
PANEL_ROWS = 2427931
SESSIONS_TOTAL = 1712
SESSIONS_E1 = 1468
DERIVED_MISSING = 6996
UNKNOWN_WEEKDAYS = 104
YEARS = ["2016", "2017", "2018", "2019", "2020", "2021"]


@pytest.fixture(scope="module")
def art():
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def test_result_is_exact_zero_not_a_bound(art):
    r = art["result"]
    assert r["real_affected_rows_in_universe"] == 0
    assert r["is_exact"] is True
    assert r["duplicate_date_stock_rows"] == 0
    assert r["missing_rows_within_active_span"] == 0
    assert r["stocks_with_missing_rows"] == 0
    assert r["stocks_with_more_rows_than_sessions"] == 0


def test_four_way_delta_is_zero_and_names_no_dominant_feature(art):
    f = art["four_way_intersection"]
    assert f["before"] == ALL_FOUR
    assert f["after"] == ALL_FOUR
    assert f["delta"] == 0
    assert f["dominant_feature_for_delta"] is None
    for name, blk in art["per_feature_unchanged"].items():
        assert blk["numeric_computable"] >= ALL_FOUR, name
    assert art["per_feature_unchanged"]["MA120"]["numeric_computable"] == ALL_FOUR


def test_ma120_c_breakdown_adds_up(art):
    ma = art["per_feature_unchanged"]["MA120"]
    assert sum(ma["issue_C_breakdown"].values()) == ma["issue_C_days"]
    assert ma["numeric_computable"] + ma["issue_C_days"] == UNIVERSE_ROWS


def test_both_cross_source_directions_are_recorded(art):
    r = art["result"]
    # 被靜默丟棄的方向必須是 0；不是 0 的話那些列連成為候選的機會都沒有。
    assert r["raw_only_keys_silently_dropped"] == 0
    # 反方向保留成 null 列是正確行為，但不得進入母體。
    assert r["tradability_only_keys_derived_missing_row"] == DERIVED_MISSING
    assert r["derived_missing_rows_inside_universe"] == 0


def test_canonical_calendar_is_self_defined_and_consistent(art):
    cal = art["canonical_calendar"]
    assert cal["sessions_warmup_to_e1_end"] == SESSIONS_TOTAL
    assert cal["sessions_in_e1"] == SESSIONS_E1
    assert cal["panel_dates_with_no_trading_stock"] == 0
    assert art["result"]["sessions_in_e1"] == SESSIONS_E1
    sessions_by_year = art["unknown_fail_closed"]["sessions_by_year"]
    assert sum(sessions_by_year[y] for y in YEARS) == SESSIONS_E1


def test_unclassifiable_weekdays_stay_unknown(art):
    u = art["unknown_fail_closed"]
    assert u["e1_weekdays_that_are_not_sessions"] == UNKNOWN_WEEKDAYS
    assert u["classification"] == "UNKNOWN"
    assert sum(u["by_year"][y] for y in YEARS) == UNKNOWN_WEEKDAYS
    # 數量與假日同量級不得被寫成已驗證。
    assert "UNKNOWN" in u["consistency_note"] or "不等於" in u["consistency_note"]


def test_sensitivity_shows_when_it_would_start_to_matter(art):
    s = art["sensitivity_when_it_would_start_to_matter"]
    assert s["four_way_before"] == ALL_FOUR
    assert s["four_way_after"] == s["four_way_before"] + s["four_way_delta"]
    # 方向必須是變少，不是變多。
    assert s["four_way_delta"] < 0
    assert s["dominant_feature"] == "MA120"
    assert s["per_feature_delta"]["MA120"] == s["four_way_delta"]
    # ATR14 / LOW20 用 valid_bar_ordinal，空值列不計，必須完全不動。
    assert s["per_feature_delta"]["ATR14"] == 0
    assert s["per_feature_delta"]["LOW20"] == 0
    assert s["universe_rows_before"] == s["universe_rows_after"] == UNIVERSE_ROWS
    # 敏感度量級必須遠大於本輪量到的 0，否則這段就白寫了。
    assert abs(s["four_way_delta"]) > 1000


def test_layer_is_data_diagnostic_not_strategy(art):
    assert art["measurement_layer"] == "DATA_LAYER_DIAGNOSTIC"
    for banned in ("win_rate", "payoff_ratio", "expectancy_per_trade"):
        assert banned in art["metrics_not_reported"]
    text = ARTIFACT.read_text(encoding="utf-8")
    for banned in ("win_rate\":", "payoff_ratio\":", "expectancy\":"):
        assert banned not in text


def test_gate_and_scope_are_not_relaxed(art):
    assert art["execution_authorized"] is False
    assert art["formal_research_gate"] == "BLOCKED_UNCONDITIONALLY"
    assert art["scope"] == "SOURCE_EVIDENCE"
    assert art["contradicts_pr8"] is False


def test_artifact_inputs_match_the_r2_manifest(art):
    man = json.loads(R2_MANIFEST.read_text(encoding="utf-8"))
    inp, fixed = art["inputs"], man["fixed_inputs"]
    assert inp["private_delivery_commit"] == fixed["private_delivery_commit"]
    assert inp["source_revision"] == fixed["source_revision"]
    assert inp["astra_contract_revision"] == fixed["astra_contract_revision"]
    assert inp["exclusion_sha256"] == fixed["p2_060_exclusion_sha256"]
    assert inp["producer_revision"] == man["producer"]["revision"]
    assert inp["producer_sha256"] == man["producer"]["sha256"]
    assert man["denominator"]["row_count"] == UNIVERSE_ROWS


def test_no_private_row_content_in_the_public_artifact(art):
    text = ARTIFACT.read_text(encoding="utf-8")
    assert "stock_id" not in text
    # 模擬日期是本文件自己選的公開參數，不是私有逐列內容。
    assert art["sensitivity_when_it_would_start_to_matter"]["simulated_date"] in text


# --- 真實掃描 ---------------------------------------------------------------

def _build_panel():
    import pandas as pd

    spec = importlib.util.spec_from_file_location("aq_producer", os.environ["AQ_PRODUCER"])
    producer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(producer)
    excluded = set(
        pd.read_csv(ROOT / "docs" / "SOURCE_CA_PIT_EXCLUSIONS.csv", dtype={"ticker": str})["ticker"]
    )
    panel = producer.add_c_states(
        producer.add_universe(producer.load_panel(Path(os.environ["AQ_SOURCE_ROOT"]), excluded))
    )
    return producer, panel


_needs_source = pytest.mark.skipif(
    not (os.environ.get("AQ_SOURCE_ROOT") and os.environ.get("AQ_PRODUCER")),
    reason="frozen source / producer not available",
)


@_needs_source
def test_clean_path_calendar_has_no_gaps_or_duplicates(art):
    """乾淨路徑：每檔在活躍區間內每個 session 都有一列，無重複。"""
    import bisect

    import pandas as pd

    _, panel = _build_panel()
    assert int(panel["all_liquid"].sum()) == UNIVERSE_ROWS
    assert panel.loc[panel["all_liquid"], "stock_id"].nunique() == UNIVERSE_STOCKS
    assert len(panel) == PANEL_ROWS
    assert int(panel.duplicated(["date", "stock_id"]).sum()) == 0

    sessions = panel.loc[panel["observed_trade"], "date"].drop_duplicates().sort_values()
    assert len(sessions) == SESSIONS_TOTAL
    assert len(panel["date"].drop_duplicates()) == SESSIONS_TOTAL  # 無「無人成交」的日期

    arr = sessions.to_numpy()
    grouped = panel.groupby("stock_id")["date"]
    first, last, count = grouped.min(), grouped.max(), grouped.size()
    missing_total = 0
    for sid in first.index:
        lo = bisect.bisect_left(arr, first[sid])
        hi = bisect.bisect_right(arr, last[sid])
        missing_total += (hi - lo) - int(count[sid])
    assert missing_total == 0
    assert art["result"]["missing_rows_within_active_span"] == 0

    derived = panel["source"].eq("DERIVED_MISSING_ROW")
    assert int(derived.sum()) == DERIVED_MISSING
    assert int((derived & panel["all_liquid"]).sum()) == 0


@_needs_source
def test_missing_session_path_moves_the_four_way_intersection(art):
    """缺日路徑：補回一個 session 會讓四項交集以數萬列的量級變少，由 MA120 主導。"""
    import numpy as np
    import pandas as pd

    producer, panel = _build_panel()
    s = art["sensitivity_when_it_would_start_to_matter"]
    day = pd.Timestamp(s["simulated_date"])
    assert day not in set(panel["date"].unique()), "模擬日必須本來就不是 session"

    base_cols = ["date", "stock_id", "observed_trade", "valid_ohlc", "reason", "open",
                 "max", "min", "close", "Trading_money", "market", "source"]
    window = panel["date"].between(day - pd.Timedelta(days=30), day + pd.Timedelta(days=30))
    stocks = panel.loc[window, "stock_id"].unique()
    inserted = pd.DataFrame({
        "date": day, "stock_id": stocks, "observed_trade": False, "valid_ohlc": False,
        "reason": "SIMULATED_RESTORED_SESSION", "open": np.nan, "max": np.nan,
        "min": np.nan, "close": np.nan, "Trading_money": np.nan,
        "market": "", "source": "SIMULATED"})
    assert len(inserted) == s["inserted_null_rows"]

    merged = (pd.concat([panel[base_cols], inserted], ignore_index=True)
              .sort_values(["stock_id", "date"], kind="stable").reset_index(drop=True))
    merged["panel_index"] = np.arange(len(merged), dtype=np.int64)
    merged = producer.add_c_states(producer.add_universe(merged))

    def four_way(frame):
        rows = frame[frame["all_liquid"]]
        ok = (rows["ma120_c_reason"].eq("") & rows["n60_c_reason"].eq("")
              & rows["atr14_c_reason"].eq("") & rows["low20_c_reason"].eq(""))
        return len(rows), int(ok.sum())

    rows_before, four_before = four_way(panel)
    rows_after, four_after = four_way(merged)
    assert rows_before == rows_after == UNIVERSE_ROWS
    assert four_before == ALL_FOUR
    assert four_after == s["four_way_after"]
    assert four_after - four_before == s["four_way_delta"] < 0

    for feature, expected in s["per_feature_delta"].items():
        col = f"{feature.lower()}_c_reason"
        before = int(panel.loc[panel["all_liquid"], col].eq("").sum())
        after = int(merged.loc[merged["all_liquid"], col].eq("").sum())
        assert after - before == expected, feature
