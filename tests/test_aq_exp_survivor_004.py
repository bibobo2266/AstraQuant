"""AQ-EXP-SURVIVOR-004 — terminal 判定窗的文件更正。

驗收標準：① 不得更動任何既有量化結果 ② 更正處全部列出
③ 文件中不再有未標註判定窗的裸「74 檔」E1 敘述。

文件更正作業，不報任何績效指標。
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs" / "SOURCE_TERMINAL_COVERAGE_AUDIT.md"
SURV = ROOT / "docs" / "SURVIVORSHIP_72_DELISTED.md"
MASTER = ROOT / "docs" / "MASTER_PROGRESS.md"
CONTACT = ROOT / "out" / "survivorship_e1_universe_contact.json"
SEQ = ROOT / "out" / "survivorship_74_sequence_end.csv"

E1_END = "2021-12-30"
TOTAL, INSIDE, OUTSIDE = 74, 42, 32

# 同一段落裡只要出現其中一個標記，就算有標註判定窗。
MARKERS = ("判定窗", "E1 內", "E1_INSIDE", "E1 之後", "2015–2026", "42 檔")


def _paragraphs(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").split("\n\n")


# --- 驗收 ③：不得再有未標註的裸「74 檔」-----------------------------------

def test_no_unannotated_bare_74_narrative_anywhere_in_docs():
    offenders = []
    for path in sorted((ROOT / "docs").glob("*.md")):
        for para in _paragraphs(path):
            if "74 檔" in para or "74 unmodeled" in para:
                if not any(m in para for m in MARKERS):
                    offenders.append(f"{path.name}: {para.strip().splitlines()[0][:80]}")
    assert offenders == [], offenders


# --- 稽核文件的新欄位 -------------------------------------------------------

def test_audit_table_has_the_terminal_window_column():
    text = AUDIT.read_text(encoding="utf-8")
    section = text.split("## Unmodeled terminal securities", 1)[1].split("\n## ", 1)[0]
    header = next(l for l in section.splitlines() if l.startswith("| Ticker |"))
    assert header.rstrip().endswith("| Terminal window |")
    assert header.count("|") == 8                      # 7 欄
    separator = next(l for l in section.splitlines() if re.fullmatch(r"\|[\-: |]+\|", l.strip()))
    assert separator.count("|") == 8


def test_every_unmodeled_row_is_labelled_and_the_split_matches_the_dates():
    text = AUDIT.read_text(encoding="utf-8")
    section = text.split("## Unmodeled terminal securities", 1)[1].split("\n## ", 1)[0]
    rows = re.findall(r"^\|\s*(\d{4})\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|.*\|\s*(E1_\w+)\s*\|$",
                      section, re.M)
    assert len(rows) == TOTAL
    inside = [t for t, d, w in rows if w == "E1_INSIDE"]
    outside = [t for t, d, w in rows if w == "E1_OUTSIDE"]
    assert len(inside) == INSIDE and len(outside) == OUTSIDE
    # 標籤必須由 Last RAW 與 E1 期末推導，不得手工指定。
    for ticker, day, window in rows:
        assert window == ("E1_INSIDE" if day <= E1_END else "E1_OUTSIDE"), ticker
    assert f"**{INSIDE} E1_INSIDE / {OUTSIDE} E1_OUTSIDE**" in section


def test_generator_reproduces_the_same_column():
    """產生器必須跟著改，否則下次重產會把欄位洗掉。"""
    src = (ROOT / "scripts" / "source_terminal_coverage_audit.py").read_text(encoding="utf-8")
    assert 'E1_END = pd.Timestamp("2021-12-30")' in src
    assert "Terminal window |" in src
    assert '"E1_INSIDE"' in src and '"E1_OUTSIDE"' in src


def test_existing_parser_still_reads_74_rows():
    """既有 regex 只吃前兩欄，新增欄位不得破壞它。"""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "survivorship_scan", ROOT / "scripts" / "survivorship_72_scan.py")
    scan = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scan)
    assert len(scan.unmodeled_tickers()) == TOTAL


def test_window_split_agrees_with_survivor_003(): 
    with SEQ.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    early = [r for r in rows if r["sequence_class"] == "ENDS_EARLY"]
    at_end = [r for r in rows if r["sequence_class"] == "ENDS_AT_PERIOD_END"]
    assert len(early) == INSIDE and len(at_end) == OUTSIDE


# --- 驗收 ②：更正處全部列出 ------------------------------------------------

def test_correction_record_is_kept_and_lists_both_rounds():
    text = SURV.read_text(encoding="utf-8")
    assert "口徑更正紀錄" in text
    assert "72 → 74" in text                                     # 第一次正名
    assert "E1 內 42 檔" in text or "E1 內真正有序列終止事件的是 42 檔" in text
    assert "第二次口徑更正" in text
    assert "不得單獨使用裸的「74 檔」" in text


def test_master_progress_is_corrected():
    text = MASTER.read_text(encoding="utf-8")
    assert "terminal judgment window 2015-2026" in text
    assert "42 are E1_INSIDE and 32 are E1_OUTSIDE" in text


def test_conservative_note_sits_next_to_the_413_figure():
    text = SURV.read_text(encoding="utf-8")
    para = next(p for p in _paragraphs(SURV) if "母體口徑註記" in p)
    assert "413" in para and "偏保守" in para
    assert "不重算" in para and "不刪除" in para
    assert "413" in text and "0.089%" in text


# --- 驗收 ①：不得更動任何既有量化結果 --------------------------------------

@pytest.mark.parametrize(
    "key,expected",
    [("universe_rows", 458315), ("universe_stocks", 1394),
     ("days_within_holding_period_of_last_raw", 410),
     ("at_risk_ticker_lifetime_universe_days", 8465),
     ("ever_in_universe_stock_days", 15797)],
)
def test_quantitative_results_are_untouched(key, expected):
    data = json.loads(CONTACT.read_text(encoding="utf-8"))
    assert data[key] == expected


def test_headline_numbers_still_present_in_the_prose():
    text = SURV.read_text(encoding="utf-8")
    for figure in ("410", "413", "0.089%", "1.847%", "8,465", "15,797", "21 檔"):
        assert figure in text, figure
