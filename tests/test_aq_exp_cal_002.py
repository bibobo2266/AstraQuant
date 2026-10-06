"""AQ-EXP-CAL-002 — 外部台股交易日曆與 104 個 UNKNOWN 的逐日判定。

驗收標準第 4 點要求涵蓋「日曆可得」與「日曆不可得」兩條路徑，兩者都在這裡：
- 不可得：外部套件缺席時，判定表仍須自洽，且不得宣稱已權威確認。
- 可得：裝了 exchange_calendars 才跑真實比對。

資料層診斷，不含勝率／賠率／每筆期望值。
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "out" / "aq_exp_cal_002_external_calendar.json"
LEDGER = ROOT / "out" / "aq_exp_cal_002_adjudication.csv"
CAL1 = ROOT / "out" / "aq_exp_cal_001_calendar_completeness.json"

UNKNOWN_IN = 104
ALL_FOUR = 428102
PANEL_E1_SESSIONS = 1468
XTAI_E1_SESSIONS = 1460
MAKEUP_SATURDAYS = 8

_HAS_XC = importlib.util.find_spec("exchange_calendars") is not None


@pytest.fixture(scope="module")
def art():
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


# --- 日曆不可得路徑：只讀 repo 內的判定表與聚合檔 ---------------------------

def test_every_unknown_day_from_cal_001_is_adjudicated(art):
    cal1 = json.loads(CAL1.read_text(encoding="utf-8"))
    assert cal1["unknown_fail_closed"]["e1_weekdays_that_are_not_sessions"] == UNKNOWN_IN
    a = art["adjudication"]
    assert a["unknown_weekdays_in"] == UNKNOWN_IN
    assert a["resolved_non_trading_day"] + a["resolved_real_missing_session"] + a["still_unknown"] == UNKNOWN_IN
    assert a["still_unknown"] == 0


def test_ledger_matches_the_artifact_day_for_day():
    import csv

    with LEDGER.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == UNKNOWN_IN
    dates = [r["date"] for r in rows]
    assert dates == sorted(dates)
    assert len(set(dates)) == UNKNOWN_IN
    assert {r["verdict"] for r in rows} == {"NON_TRADING_DAY"}
    # 每一列都要有依據來源，且第三方來源必須自我標示為非權威。
    for r in rows:
        assert r["source"].strip()
        assert "NON-AUTHORITATIVE" in r["source"]


def test_third_party_source_is_labelled_non_authoritative(art):
    tiers = {t["name"]: t for t in art["source_ladder"]}
    xtai = tiers["exchange_calendars XTAI"]
    assert xtai["authoritative"] is False
    assert xtai["non_authoritative_label_required"] is True
    assert art["adjudication"]["primary_source_used"].startswith("exchange_calendars")
    # 公告型 tier 1 來源涵蓋不到 E1，必須明寫而不是靜默跳過。
    holiday_tier = tiers["TWSE 開(休)市日期表"]
    assert holiday_tier["authoritative"] is True
    assert holiday_tier["usable_for_e1"] is False


def test_no_same_source_circularity(art):
    """禁止以 panel 自推日曆再回去驗 panel。"""
    assert art["self_derived_calendar_used_for_adjudication"] is False
    cc = art["cross_check"]
    # panel 只能是被比對的一方：判定來自外部清單，不是 panel 自身。
    assert cc["panel_e1_sessions"] == PANEL_E1_SESSIONS
    assert cc["xtai_e1_sessions"] == XTAI_E1_SESSIONS
    assert cc["xtai_has_panel_lacks"] == art["adjudication"]["resolved_real_missing_session"]


def test_four_way_delta_is_actual_not_estimated(art):
    f = art["four_way_intersection"]
    assert f["before"] == ALL_FOUR
    assert f["after"] == ALL_FOUR
    assert f["delta"] == 0
    assert f["is_actual_not_estimated"] is True
    assert f["dominant_feature_for_delta"] is None
    # delta 為 0 的計算路徑必須可讀，不能只給結論。
    assert art["adjudication"]["resolved_real_missing_session"] == 0
    assert "空集合" in f["calculation_path"]


def test_residual_risk_admits_the_third_party_under_reports(art):
    r = art["residual_risk"]
    assert r["xtai_under_reports_sessions"] is True
    assert art["cross_check"]["panel_has_xtai_lacks"] == MAKEUP_SATURDAYS
    assert art["cross_check"]["panel_has_xtai_lacks_all_saturdays"] is True
    assert r["what_would_close_it"].strip()


def test_ledger_and_license_are_recorded(art):
    tiers = {t["name"]: t for t in art["source_ladder"]}
    assert tiers["exchange_calendars XTAI"]["license"] == "Apache-2.0"
    assert tiers["exchange_calendars XTAI"]["reproducible_fetch"].startswith("pip install")
    assert "license" in tiers["TWSE 每日市場成交資訊 FMTQIK"]
    assert tiers["TWSE 每日市場成交資訊 FMTQIK"]["endpoint"].startswith("https://")


def test_authoritative_spot_check_is_recorded_and_consistent(art):
    s = art["authoritative_spot_check"]
    assert s["identical"] is True
    assert s["all_confirmed_non_trading"] is True
    assert len(s["twse_sessions"]) == len(s["panel_sessions"])
    for day in s["unknown_weekdays_in_month"]:
        assert day not in s["twse_sessions"]
        assert day in art["adjudication"]["dates_non_trading_day"]


def test_layer_is_data_diagnostic(art):
    assert art["measurement_layer"] == "DATA_LAYER_DIAGNOSTIC"
    assert art["execution_authorized"] is False
    assert art["formal_research_gate"] == "BLOCKED_UNCONDITIONALLY"
    for banned in ("win_rate", "payoff_ratio", "expectancy_per_trade"):
        assert banned in art["metrics_not_reported"]


# --- 日曆可得路徑 -----------------------------------------------------------

@pytest.mark.skipif(not _HAS_XC, reason="exchange_calendars not installed")
def test_external_calendar_reproduces_the_adjudication(art):
    import exchange_calendars as xc
    import pandas as pd

    cal = xc.get_calendar("XTAI", start="2016-01-01", end="2021-12-31")
    sessions = {pd.Timestamp(d).normalize() for d in cal.sessions}
    e1 = {d for d in sessions
          if pd.Timestamp("2016-01-04") <= d <= pd.Timestamp("2021-12-30")}
    assert len(e1) == XTAI_E1_SESSIONS

    # 每一個被判定為非交易日的日期，都不得出現在外部日曆的 session 裡。
    for day in art["adjudication"]["dates_non_trading_day"]:
        assert pd.Timestamp(day) not in e1, day
    assert art["adjudication"]["resolved_real_missing_session"] == 0


@pytest.mark.skipif(
    not (_HAS_XC and os.environ.get("AQ_SOURCE_ROOT") and os.environ.get("AQ_PRODUCER")),
    reason="exchange_calendars / frozen source / producer not all available",
)
def test_full_cross_check_against_the_rebuilt_panel(art):
    import exchange_calendars as xc
    import pandas as pd

    spec = importlib.util.spec_from_file_location("aq_producer", os.environ["AQ_PRODUCER"])
    producer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(producer)
    excluded = set(
        pd.read_csv(ROOT / "docs" / "SOURCE_CA_PIT_EXCLUSIONS.csv", dtype={"ticker": str})["ticker"]
    )
    panel = producer.add_universe(producer.load_panel(Path(os.environ["AQ_SOURCE_ROOT"]), excluded))
    start, end = pd.Timestamp("2016-01-04"), pd.Timestamp("2021-12-30")
    panel_e1 = {d for d in pd.to_datetime(panel.loc[panel["observed_trade"], "date"].unique())
                if start <= d <= end}
    assert len(panel_e1) == PANEL_E1_SESSIONS

    cal = xc.get_calendar("XTAI", start="2016-01-01", end="2021-12-31")
    xtai_e1 = {d for d in (pd.Timestamp(x).normalize() for x in cal.sessions)
               if start <= d <= end}

    # 真缺日方向必須是空集合，這是本輪結論的全部依據。
    assert xtai_e1 - panel_e1 == set()
    # 反方向只允許補行交易週六。
    extra = sorted(panel_e1 - xtai_e1)
    assert len(extra) == MAKEUP_SATURDAYS
    assert all(d.weekday() == 5 for d in extra)
    assert [str(d.date()) for d in extra] == art["cross_check"]["panel_has_xtai_lacks_dates"]
