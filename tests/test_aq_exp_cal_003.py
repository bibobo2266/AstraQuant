"""AQ-EXP-CAL-003 — 以權威紀錄取代第三方日曆。

驗收標準第 5 點要求涵蓋「權威紀錄齊備」與「部分月份缺漏」兩條路徑，
兩者都用合成 fixture 在本地完成，不需網路、不需私有資料。

資料層診斷，不含勝率／賠率／每筆期望值。
"""
from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ALL_FOUR = 428102
PER_MISSING = -34254


def _load():
    spec = importlib.util.spec_from_file_location(
        "adjudicate", ROOT / "scripts" / "adjudicate_calendar_authoritative.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MOD = _load()


def _months(start=(2016, 1), end=(2021, 12)):
    out, (y, m) = [], start
    while (y, m) <= end:
        out.append(f"{y}{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _fixture(tmp_path: Path, *, unknown_months=(), extra_twse=(), drop_twse=()):
    """造一棵最小的 out/ 樹。

    panel 與權威預設完全一致，另加一個補行交易週六只存在於 panel。
    unknown_months  : 這些月份標成取不到
    extra_twse      : 只存在於權威的日期（＝真缺日）
    drop_twse       : 從權威拿掉的日期
    """
    out = tmp_path / "out"
    out.mkdir(parents=True)
    common = ["2016-01-05", "2016-02-15", "2018-06-20", "2021-09-22"]
    saturday_only_in_panel = "2016-01-30"
    unknown_days = ["2016-01-04", "2016-02-08", "2018-06-18", "2021-09-20"]

    twse = sorted((set(common) | set(extra_twse)) - set(drop_twse))
    (out / "aq_exp_cal_003_twse_sessions.csv").write_text(
        "date,source_month\n" + "".join(f"{d},{d[:4]}{d[5:7]}\n" for d in twse),
        encoding="utf-8")
    (out / "aq_exp_cal_003_panel_sessions.csv").write_text(
        "date\n" + "".join(f"{d}\n" for d in sorted(common + [saturday_only_in_panel])),
        encoding="utf-8")
    with (out / "aq_exp_cal_002_adjudication.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "verdict", "source",
                                           "authoritative_confirmation"])
        w.writeheader()
        for d in unknown_days:
            w.writerow({"date": d, "verdict": "NON_TRADING_DAY",
                        "source": "exchange_calendars XTAI 4.13.2 "
                                  "(third-party, NON-AUTHORITATIVE)",
                        "authoritative_confirmation": ""})

    all_months = _months()
    months = {m: ({"status": "UNKNOWN", "detail": "http 403"} if m in unknown_months
                  else {"status": "OK", "sessions": 1}) for m in all_months}
    unknown_list = sorted(unknown_months)
    (out / "aq_exp_cal_003_fetch_log.json").write_text(json.dumps({
        "endpoint_template": "https://www.twse.com.tw/en/exchangeReport/FMTQIK"
                             "?response=csv&date={ym}01",
        "months_requested": len(all_months), "months": months,
        "months_ok": len(all_months) - len(unknown_list),
        "months_unknown": len(unknown_list), "months_unknown_list": unknown_list,
        "stopped_early": bool(unknown_list), "stop_reason": None,
        "total_sessions": len(twse)}, ensure_ascii=False), encoding="utf-8")
    return tmp_path


# --- 路徑一：權威紀錄齊備 ---------------------------------------------------

def test_full_coverage_upgrades_every_day_to_authoritative(tmp_path):
    built = MOD.build(_fixture(tmp_path))
    a, rows = built["artifact"], built["rows"]
    src = a["authoritative_source"]
    assert src["months_ok"] == 72 and src["months_unknown"] == 0
    assert src["full_coverage"] is True
    assert src["authoritative"] is True

    adj = a["adjudication"]
    assert adj["days_in"] == 4
    assert adj["upgraded_to_authoritative"] == 4
    assert adj["still_third_party"] == 0
    assert adj["not_upgraded_dates"] == []
    assert adj["third_party_used_as_filler"] is False
    assert all(r["source_tier"] == "authoritative" for r in rows)
    assert all("FMTQIK" in r["source"] for r in rows)


def test_full_coverage_with_no_real_missing_day_gives_actual_zero_delta(tmp_path):
    a = MOD.build(_fixture(tmp_path))["artifact"]
    assert a["adjudication"]["real_missing_session"] == 0
    f = a["four_way_intersection"]
    assert f["before"] == ALL_FOUR
    assert f["after"] == ALL_FOUR
    assert f["delta"] == 0
    assert f["is_actual_not_estimated"] is True
    assert f["reference_delta_per_missing_session"] == PER_MISSING


def test_both_directions_of_the_reconciliation_are_listed(tmp_path):
    rec = MOD.build(_fixture(tmp_path))["artifact"]["full_period_reconciliation"]
    # 權威有而 panel 無 = 真缺日；本 fixture 沒有。
    assert rec["authoritative_only_count"] == 0
    assert rec["authoritative_only_dates"] == []
    # panel 有而權威無，必須列出且逐日可檢查是不是補行交易週六。
    assert rec["panel_only_dates"] == ["2016-01-30"]
    assert rec["panel_only_all_saturdays"] is True
    # 數目與預期的 8 個不同時，旗標要落下來，交由報告解釋。
    assert rec["panel_only_matches_expected_makeup_saturdays"] is False


def test_a_real_missing_session_is_not_silently_turned_into_a_delta(tmp_path):
    """真缺日出現時，delta 必須留空等 CAL-001 路徑重算，不得就地估計。"""
    built = MOD.build(_fixture(tmp_path, extra_twse=["2018-06-18"]))
    a = built["artifact"]
    assert a["adjudication"]["real_missing_session"] == 1
    assert a["adjudication"]["real_missing_session_dates"] == ["2018-06-18"]
    assert a["full_period_reconciliation"]["authoritative_only_dates"] == ["2018-06-18"]
    f = a["four_way_intersection"]
    assert f["real_missing_sessions_found"] == 1
    assert f["delta"] is None
    assert f["after"] is None
    assert f["is_actual_not_estimated"] is False
    assert "不估計" in f["calculation_path"]
    verdicts = {r["date"]: r["verdict"] for r in built["rows"]}
    assert verdicts["2018-06-18"] == "REAL_MISSING_SESSION"


# --- 路徑二：部分月份缺漏 ---------------------------------------------------

def test_unknown_month_keeps_those_days_on_the_third_party_tier(tmp_path):
    built = MOD.build(_fixture(tmp_path, unknown_months=("201806", "202109")))
    a, rows = built["artifact"], built["rows"]
    src = a["authoritative_source"]
    assert src["months_ok"] == 70
    assert src["months_unknown"] == 2
    assert src["months_unknown_list"] == ["201806", "202109"]
    assert src["full_coverage"] is False

    adj = a["adjudication"]
    assert adj["upgraded_to_authoritative"] == 2
    assert adj["still_third_party"] == 2
    assert adj["not_upgraded_dates"] == ["2018-06-18", "2021-09-20"]
    assert adj["third_party_used_as_filler"] is False

    by_day = {r["date"]: r for r in rows}
    for day in ("2018-06-18", "2021-09-20"):
        assert by_day[day]["source_tier"] == "third-party"
        assert "NON-AUTHORITATIVE" in by_day[day]["source"]
        assert by_day[day]["note"].startswith("UNKNOWN_MONTH")
    for day in ("2016-01-04", "2016-02-08"):
        assert by_day[day]["source_tier"] == "authoritative"


def test_unknown_month_is_excluded_from_the_reconciliation_window(tmp_path):
    """取不到的月份不得進對帳，否則會把『沒取到』誤算成『真缺日』。"""
    rec = MOD.build(_fixture(tmp_path, unknown_months=("201806",)))[
        "artifact"]["full_period_reconciliation"]
    assert rec["covered_months"] == 71
    assert "2018-06-20" not in rec["authoritative_only_dates"]
    assert "2018-06-20" not in rec["panel_only_dates"]
    assert rec["authoritative_only_count"] == 0


def test_gate_and_layer_are_not_relaxed(tmp_path):
    a = MOD.build(_fixture(tmp_path))["artifact"]
    assert a["execution_authorized"] is False
    assert a["formal_research_gate"] == "BLOCKED_UNCONDITIONALLY"
    assert a["measurement_layer"] == "DATA_LAYER_DIAGNOSTIC"
    for banned in ("win_rate", "payoff_ratio", "expectancy_per_trade"):
        assert banned in a["metrics_not_reported"]


# --- 取數腳本本身 -----------------------------------------------------------

def test_fetcher_month_range_and_block_detection():
    spec = importlib.util.spec_from_file_location(
        "fetcher", ROOT / "scripts" / "fetch_twse_fmtqik.py")
    fetcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fetcher)

    assert len(fetcher.months("201601", "202112")) == 72
    assert fetcher.months("201601", "202112")[0] == "201601"
    assert fetcher.months("201601", "202112")[-1] == "202112"

    good = ('"2021/09 Highlights of Daily Trading"\n"Date",\n"2021/09/01","1",\n'
            ).encode("ms950")
    assert fetcher.classify(200, good)[0] == "OK"
    assert fetcher.parse_dates(good, "202109") == ["2021-09-01"]
    # 不屬於該月的列不得混入。
    assert fetcher.parse_dates(good, "202108") == []
    assert fetcher.classify(403, b"")[0] == "BLOCKED"
    assert fetcher.classify(429, b"")[0] == "BLOCKED"
    assert fetcher.classify(200, "<html>blocked</html>".encode("ms950"))[0] == "BLOCKED"
    assert fetcher.classify(200, "nothing useful".encode("ms950"))[0] == "EMPTY_OR_BAD"


def test_panel_session_list_is_an_aggregate_with_no_row_level_content():
    path = ROOT / "out" / "aq_exp_cal_003_panel_sessions.csv"
    with path.open(encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        rows = list(reader)
    assert header == ["date"]          # 只有日期，沒有 stock_id、沒有價格
    assert len(rows) == 1468
    assert rows[0] == ["2016-01-04"] and rows[-1] == ["2021-12-30"]
