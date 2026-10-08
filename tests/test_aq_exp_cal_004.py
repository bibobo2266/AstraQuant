"""AQ-EXP-CAL-004 — 2017-10 的單次授權補取。

驗收標準第 4 點要求「成功 / 再次被擋」兩條路徑各有測試。
成功路徑驗實際產出；被擋路徑用合成情境驗，證明失敗時不會動到既有數字。

資料層診斷，不報勝率／賠率／每筆期望值。
"""
from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "out" / "aq_exp_cal_003_fetch_log.json"
SESSIONS = ROOT / "out" / "aq_exp_cal_003_twse_sessions.csv"
ART = ROOT / "out" / "aq_exp_cal_003_authoritative_calendar.json"
LEDGER = ROOT / "out" / "aq_exp_cal_003_adjudication.csv"
CAL2_LEDGER = ROOT / "out" / "aq_exp_cal_002_adjudication.csv"
CAL2_ART = ROOT / "out" / "aq_exp_cal_002_external_calendar.json"
RAW = ROOT / "out" / "twse_fmtqik_raw"
DOC = ROOT / "docs" / "AQ_EXP_CAL_003_AUTHORITATIVE_CALENDAR.md"

TARGET_MONTH = "201710"
THREE_DAYS = ["2017-10-04", "2017-10-09", "2017-10-10"]
ALL_FOUR = 428102
PANEL_E1_SESSIONS = 1468


@pytest.fixture(scope="module")
def log():
    return json.loads(LOG.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def art():
    return json.loads(ART.read_text(encoding="utf-8"))


def _fetcher():
    spec = importlib.util.spec_from_file_location(
        "fetcher", ROOT / "scripts" / "fetch_twse_fmtqik.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- 成功路徑 ---------------------------------------------------------------

def test_target_month_was_retrieved_and_coverage_is_now_complete(log, art):
    assert log["months"][TARGET_MONTH]["status"] == "OK"
    assert log["months_ok"] == 72
    assert log["months_unknown_list"] == []
    assert art["authoritative_source"]["months_ok"] == 72
    assert art["authoritative_source"]["months_unknown_list"] == []
    assert art["authoritative_source"]["full_coverage"] is True


def test_the_retry_merged_instead_of_overwriting(log):
    """補取單月不得洗掉先前 71 個月——這是本輪最大的操作風險。"""
    assert log.get("merged_with_prior_run") is True
    assert log.get("this_run_months") == [TARGET_MONTH]
    assert len(log["months"]) == 72
    assert len(list(RAW.glob("FMTQIK_*.csv"))) == 72
    assert (RAW / f"FMTQIK_{TARGET_MONTH}.csv").exists()
    # 其他月份的狀態必須原封不動。
    assert all(v["status"] == "OK" for m, v in log["months"].items())


def test_three_days_upgraded_to_authoritative(art):
    with LEDGER.open(encoding="utf-8") as fh:
        rows = {r["date"]: r for r in csv.DictReader(fh)}
    for day in THREE_DAYS:
        assert rows[day]["source_tier"] == "authoritative", day
        assert "FMTQIK 2017-10" in rows[day]["source"], day
        assert rows[day]["verdict"] == "NON_TRADING_DAY", day
    assert sum(1 for r in rows.values() if r["source_tier"] != "authoritative") == 0
    assert art["adjudication"]["still_third_party"] == 0
    assert art["adjudication"]["upgraded_to_authoritative"] == 104
    assert art["adjudication"]["not_upgraded_dates"] == []


def test_both_reconciliation_directions_are_zero_over_all_72_months(art):
    rec = art["full_period_reconciliation"]
    assert rec["covered_months"] == 72
    assert rec["authoritative_only_count"] == 0      # 真缺日
    assert rec["authoritative_only_dates"] == []
    assert rec["panel_only_count"] == 0
    assert rec["panel_sessions_in_covered_months"] == PANEL_E1_SESSIONS
    assert rec["authoritative_sessions_in_covered_months"] == PANEL_E1_SESSIONS


def test_no_real_missing_session_so_four_way_is_unchanged(art):
    """驗收 2：預期真缺日 0、四項交集不變。非 0 時必須先停下回報。"""
    assert art["adjudication"]["real_missing_session"] == 0
    f = art["four_way_intersection"]
    assert f["before"] == ALL_FOUR
    assert f["after"] == ALL_FOUR
    assert f["delta"] == 0
    assert f["is_actual_not_estimated"] is True


def test_sessions_file_grew_only_by_the_target_month():
    with SESSIONS.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == PANEL_E1_SESSIONS
    assert len({r["date"] for r in rows}) == PANEL_E1_SESSIONS   # 無重複
    oct17 = [r for r in rows if r["source_month"] == TARGET_MONTH]
    assert len(oct17) == 19
    assert all(r["date"].startswith("2017-10") for r in oct17)


def test_documents_record_the_correction_without_erasing_history():
    text = DOC.read_text(encoding="utf-8")
    assert "72/72" in text and "104/104" in text
    # 更正紀錄必須保留原值，不得直接抹掉。
    assert "71/72" in text and "CAL-004" in text
    assert "授權未被用在任何其他月份或端點" in text
    merge_prep = (ROOT / "docs" / "MERGE_PREP_E1_EVIDENCE.md").read_text(encoding="utf-8")
    assert "已解決（AQ-EXP-CAL-004）" in merge_prep
    assert "71/72" in merge_prep                                  # 原紀錄保留


# --- 驗收 5：CAL-002 的既有數字不得被動 ------------------------------------

def test_cal_002_artifacts_are_untouched():
    cal2 = json.loads(CAL2_ART.read_text(encoding="utf-8"))
    assert cal2["adjudication"]["unknown_weekdays_in"] == 104
    assert cal2["adjudication"]["resolved_non_trading_day"] == 104
    assert cal2["adjudication"]["resolved_real_missing_session"] == 0
    assert cal2["cross_check"]["panel_e1_sessions"] == PANEL_E1_SESSIONS
    assert cal2["four_way_intersection"]["delta"] == 0
    with CAL2_LEDGER.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    # CAL-002 的帳本仍是它自己那輪的第三方紀錄，不因本輪而改寫。
    assert len(rows) == 104
    assert all("NON-AUTHORITATIVE" in r["source"] for r in rows)


# --- 被擋路徑（合成）-------------------------------------------------------

def test_block_detection_still_classifies_a_challenge_page_as_blocked():
    fetcher = _fetcher()
    assert fetcher.classify(403, b"")[0] == "BLOCKED"
    assert fetcher.classify(429, b"")[0] == "BLOCKED"
    assert fetcher.classify(200, "<html>blocked</html>".encode("ms950"))[0] == "BLOCKED"


def test_merge_keeps_prior_months_when_the_retry_is_blocked(tmp_path, monkeypatch):
    """被擋路徑：補取失敗時，既有 71 個月與 sessions 一列都不能少。"""
    fetcher = _fetcher()
    prior_months = {f"2016{m:02d}": {"status": "OK", "sessions": 20} for m in range(1, 13)}
    prior_log = {"months_requested": 13, "months": prior_months,
                 "months_ok": 12, "months_unknown": 1,
                 "months_unknown_list": [TARGET_MONTH],
                 "endpoint_template": "x", "stopped_early": False, "stop_reason": None}
    prior_rows = [("2016-01-05", "201601"), ("2016-02-15", "201602")]

    log_path = tmp_path / "log.json"
    sess_path = tmp_path / "sessions.csv"
    log_path.write_text(json.dumps(prior_log), encoding="utf-8")
    sess_path.write_text("date,source_month\n" + "".join(f"{d},{m}\n" for d, m in prior_rows),
                         encoding="utf-8")
    monkeypatch.setattr(fetcher, "LOG", log_path)
    monkeypatch.setattr(fetcher, "SESSIONS", sess_path)
    monkeypatch.setattr(fetcher, "RAW_DIR", tmp_path / "raw")

    def blocked(url, timeout=0):          # 模擬再次被擋
        raise RuntimeError("simulated block")

    monkeypatch.setattr(fetcher.urllib.request, "urlopen", blocked)
    monkeypatch.setattr(
        fetcher.sys, "argv",
        ["x", "--start", TARGET_MONTH, "--end", TARGET_MONTH,
         "--interval", "0", "--merge-existing"])
    fetcher.main()

    after = json.loads(log_path.read_text(encoding="utf-8"))
    assert after["months_ok"] == 12                       # 既有月份一個都沒少
    assert TARGET_MONTH in after["months_unknown_list"]   # 目標月仍 UNKNOWN
    assert after["months"][TARGET_MONTH]["status"] == "UNKNOWN"
    rows = sess_path.read_text(encoding="utf-8").splitlines()[1:]
    assert len(rows) == len(prior_rows)                   # sessions 一列都沒少


def test_single_authorisation_was_not_spent_twice(log):
    """授權限一次請求。log 必須顯示本輪只跑了目標月，沒有第二次嘗試。"""
    assert log.get("this_run_months") == [TARGET_MONTH]
    assert log.get("stopped_early") is False
    assert log["months"][TARGET_MONTH]["status"] == "OK"
