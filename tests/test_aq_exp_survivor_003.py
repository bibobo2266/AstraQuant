"""AQ-EXP-SURVIVOR-003 — 74 檔的 terminal 成因分類。

驗收標準第 4 點要求涵蓋「序列結束於期末」與「序列提早結束」兩條路徑，兩者都在這裡。
全部只讀 repo 內的聚合檔，不需私有資料、不需網路。

資料層診斷，不含勝率／賠率／每筆期望值。
"""
from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "out" / "aq_exp_survivor_003_sequence_end.json"
TABLE = ROOT / "out" / "survivorship_74_sequence_end.csv"
TICKERS = ROOT / "out" / "survivorship_74_tickers.csv"

PERIOD_END = "2021-12-30"
MANIFEST_PERIOD_END = "2021-12-31"
TOTAL = 74
AT_PERIOD_END = 32
ENDS_EARLY = 42
ALL_FOUR = 428102
LATE21 = ["1507", "1592", "1701", "2443", "2809", "2841", "2888", "2936", "3202",
          "3426", "3454", "3536", "4945", "4987", "6172", "6288", "6747", "6806",
          "8427", "8480", "9188"]


@pytest.fixture(scope="module")
def art():
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rows():
    with TABLE.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_every_ticker_has_a_last_panel_row(rows, art):
    assert len(rows) == TOTAL
    assert art["coverage"] == {"tickers_in": TOTAL, "with_last_panel_row": TOTAL,
                               "unknown": 0, "unknown_tickers": []}
    assert all(r["last_panel_row"] for r in rows)
    # 與 step 0 的清單必須是同一組代號。
    with TICKERS.open(encoding="utf-8") as fh:
        step0 = sorted(r["ticker"] for r in csv.DictReader(fh))
    assert sorted(r["ticker"] for r in rows) == step0


def test_thresholds_are_written_down_and_have_no_tolerance_window(art):
    th = art["thresholds_fixed_at_issue_time"]
    assert th["panel_last_observed_row"] == PERIOD_END
    assert th["manifest_period_end"] == MANIFEST_PERIOD_END
    assert th["ENDS_AT_PERIOD_END"] == f"last_panel_row == {PERIOD_END}"
    assert th["ENDS_EARLY"] == f"last_panel_row < {PERIOD_END}"
    assert th["no_tolerance_window"] is True


def test_classification_follows_the_written_threshold(rows, art):
    """路徑一與路徑二：逐列重算分類，必須與記錄完全一致。"""
    recomputed = {"ENDS_AT_PERIOD_END": 0, "ENDS_EARLY": 0, "UNKNOWN": 0}
    for r in rows:
        day = r["last_panel_row"]
        expected = "ENDS_AT_PERIOD_END" if day == PERIOD_END else "ENDS_EARLY"
        assert r["sequence_class"] == expected, r["ticker"]
        assert day <= PERIOD_END, r["ticker"]
        recomputed[expected] += 1
    assert recomputed["ENDS_AT_PERIOD_END"] == AT_PERIOD_END
    assert recomputed["ENDS_EARLY"] == ENDS_EARLY
    assert recomputed["ENDS_AT_PERIOD_END"] + recomputed["ENDS_EARLY"] == TOTAL
    assert {k: v for k, v in art["classification"].items() if k in recomputed} == recomputed


def test_path_ends_at_period_end_always_has_source_data_beyond_e1(rows):
    """序列結束於期末的那一類，稽核 last_raw 必須落在 E1 之後，否則分類有問題。"""
    at_end = [r for r in rows if r["sequence_class"] == "ENDS_AT_PERIOD_END"]
    assert len(at_end) == AT_PERIOD_END
    assert all(r["last_raw_after_e1"] == "true" for r in at_end)
    assert all(r["audit_last_raw"] > PERIOD_END for r in at_end)


def test_path_ends_early_matches_the_source_exactly(rows, art):
    """序列提早結束的那一類，panel 終點必須與來源的 last_raw 完全相同 —— 這是 (b) 的否證。"""
    early = [r for r in rows if r["sequence_class"] == "ENDS_EARLY"]
    assert len(early) == ENDS_EARLY
    assert all(r["last_raw_after_e1"] == "false" for r in early)
    for r in early:
        assert r["last_valid_close"] == r["audit_last_raw"], r["ticker"]
    gap = art["coverage_gap_test"]
    assert gap["candidates_found"] == 0
    assert gap["all_42_early_tickers_panel_end_equals_last_raw"] is True


def test_late21_verdict_is_explicit_and_adds_up(rows, art):
    v = art["late21_verdict"]
    assert sorted(v["tickers"]) == sorted(LATE21)
    b = v["breakdown"]
    assert b["neither_a_nor_b"]["count"] + b["points_to_a"]["count"] + b["points_to_b"]["count"] == 21
    assert v["ends_at_period_end"] == b["neither_a_nor_b"]["count"] == 19
    assert v["ends_early"] == b["points_to_a"]["count"] == 2
    assert b["points_to_b"]["count"] == 0
    assert v["ends_early_tickers"] == ["1592", "6172"]
    # 表格與結論必須對得上。
    in21 = {r["ticker"]: r for r in rows if r["in_late21_set"] == "true"}
    assert len(in21) == 21
    early = sorted(t for t, r in in21.items() if r["sequence_class"] == "ENDS_EARLY")
    assert early == ["1592", "6172"]


def test_b_impact_is_an_actual_zero_with_a_calculation_path(art):
    imp = art["b_impact"]
    assert imp["verdict_b_ticker_count"] == 0
    assert imp["affected_stock_days"] == 0
    assert imp["four_way_intersection_before"] == ALL_FOUR
    assert imp["four_way_intersection_after"] == ALL_FOUR
    assert imp["four_way_delta"] == 0
    assert imp["is_actual_not_estimated"] is True
    assert "空集合" in imp["calculation_path"]


def test_no_external_delisting_data_was_used(art):
    assert art["external_delisting_data_used"] is False
    text = ARTIFACT.read_text(encoding="utf-8")
    # 外部回收格式的欄位名不得出現在判定依據裡。
    for banned in ("delisting_date", "event_type", "source_url",
                   "announcement_date", "evidence_snippet"):
        assert banned not in text


def test_table_only_carries_tickers_and_dates(rows):
    fields = set(rows[0])
    assert fields == {"ticker", "last_panel_row", "last_valid_close", "audit_last_raw",
                      "sequence_class", "last_raw_after_e1", "in_late21_set", "at_risk_21"}
    for r in rows:
        assert r["ticker"].isdigit() and len(r["ticker"]) == 4
        for key in ("last_panel_row", "last_valid_close", "audit_last_raw"):
            dt.date.fromisoformat(r[key])     # 只有日期，沒有價格、沒有成交金額


def test_layer_and_gate_are_not_relaxed(art):
    assert art["measurement_layer"] == "DATA_LAYER_DIAGNOSTIC"
    assert art["execution_authorized"] is False
    assert art["formal_research_gate"] == "BLOCKED_UNCONDITIONALLY"
    for banned in ("win_rate", "payoff_ratio", "expectancy_per_trade"):
        assert banned in art["metrics_not_reported"]
