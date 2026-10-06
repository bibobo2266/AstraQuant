"""AQ-EXP-SURVIVOR-002 step 0 — 74 檔未建模下市股清單的匯出。

這份檔案的用途是交給專案外的第三方取證，所以只有代號與一個布林欄，
不含任何私有逐列內容。測試釘住列數、子集、排序與去重。
"""
from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TICKERS = ROOT / "out" / "survivorship_74_tickers.csv"
CONTACT = ROOT / "out" / "survivorship_e1_universe_contact.json"
AUDIT = ROOT / "docs" / "SOURCE_TERMINAL_COVERAGE_AUDIT.md"

EXPECTED_TOTAL = 74
EXPECTED_AT_RISK = 21
MODELED = {"6286", "5305", "2823", "4141"}


@pytest.fixture(scope="module")
def rows():
    with TICKERS.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == ["ticker", "at_risk_21"]
        return list(reader)


def test_row_count_is_exactly_74(rows):
    assert len(rows) == EXPECTED_TOTAL


def test_tickers_are_sorted_and_unique(rows):
    tickers = [r["ticker"] for r in rows]
    assert tickers == sorted(tickers)
    assert len(set(tickers)) == EXPECTED_TOTAL
    assert all(t.isdigit() and len(t) == 4 for t in tickers)


def test_matches_the_audit_unmodeled_section(rows):
    """74 = 稽核文件的 78 檔 RAW-terminal 減去已建模 4 檔。"""
    spec = importlib.util.spec_from_file_location(
        "survivorship_scan", ROOT / "scripts" / "survivorship_72_scan.py")
    scan = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scan)
    derived = sorted(set(scan.unmodeled_tickers()["stock_id"].astype(str)))
    assert derived == [r["ticker"] for r in rows]
    assert len(derived) == EXPECTED_TOTAL
    # 已建模的 4 檔不得混入。
    assert MODELED.isdisjoint(set(derived))
    assert len(derived) + len(MODELED) == 78


def test_at_risk_flag_matches_the_contact_artifact(rows):
    at_risk = {r["ticker"] for r in rows if r["at_risk_21"] == "true"}
    assert len(at_risk) == EXPECTED_AT_RISK
    recorded = set(json.loads(CONTACT.read_text(encoding="utf-8"))["at_risk_tickers"])
    assert at_risk == recorded
    assert at_risk <= {r["ticker"] for r in rows}
    assert {r["at_risk_21"] for r in rows} == {"true", "false"}


def test_export_carries_no_private_row_content():
    text = TICKERS.read_text(encoding="utf-8")
    for banned in ("date", "close", "Trading_money", "last_raw", "exit_gap"):
        assert banned not in text
    # 只有兩欄，沒有日期、價格或任何逐列欄位。
    assert text.splitlines()[0] == "ticker,at_risk_21"
