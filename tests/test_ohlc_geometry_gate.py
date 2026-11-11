"""AQ-EXP-GEOM-002 — OHLC 幾何閘門。

涵蓋：乾淨路徑、四條斷言各自的違反、欄位缺失、以及
**`valid_ohlc` 恆為 True 的退化情境** —— 那是本閘門存在的全部理由。

資料層防線，不報勝率／賠率／每筆期望值。
"""
from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from astraquant.data import ohlc_geometry_gate as gate

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "docs" / "AQ_EXP_GEOM_002_GATE_PATCH.diff"
SPEC = ROOT / "docs" / "AQ_EXP_GEOM_002_GEOMETRY_GATE.md"

COLS = {"open": "open", "high": "max", "low": "min", "close": "close"}


def bars(rows):
    return pd.DataFrame(rows, columns=["open", "max", "min", "close"])


CLEAN = bars([
    [100.0, 103.0, 97.0, 101.0],
    [50.0, 50.0, 50.0, 50.0],      # 漲跌停鎖死：零振幅合法
    [10.5, 11.0, 10.0, 10.0],      # 收在最低
    [10.0, 11.0, 10.0, 11.0],      # 開在最低、收在最高
])


# --- 乾淨路徑 ---------------------------------------------------------------

def test_clean_path_passes_every_row_unchanged():
    ok = gate.passes_geometry(CLEAN, COLS)
    assert ok.tolist() == [True, True, True, True]
    assert gate.failure_summary(CLEAN, COLS)["any_failure"] == 0
    # 閘門不得改動輸入。
    before = CLEAN.copy()
    gate.passes_geometry(CLEAN, COLS)
    pd.testing.assert_frame_equal(CLEAN, before)


def test_zero_range_bar_is_legal():
    """漲跌停鎖死 high == low == open == close 不是幾何違反。"""
    sealed = bars([[42.0, 42.0, 42.0, 42.0]])
    assert gate.passes_geometry(sealed, COLS).tolist() == [True]


# --- 四條斷言各自的違反 -----------------------------------------------------

@pytest.mark.parametrize(
    "row,flag",
    [
        ([100.0, 90.0, 99.0, 100.0], "high_lt_low"),               # high < low
        ([100.0, 95.0, 90.0, 100.0], "high_lt_max_open_close"),    # high < max(open, close)
        ([100.0, 110.0, 105.0, 100.0], "low_gt_min_open_close"),   # low > min(open, close)
        ([0.0, 103.0, 97.0, 101.0], "non_finite_or_non_positive"), # open = 0
        ([100.0, 103.0, -1.0, 101.0], "non_finite_or_non_positive"),
        ([100.0, np.inf, 97.0, 101.0], "non_finite_or_non_positive"),
    ],
)
def test_each_assertion_catches_its_own_violation(row, flag):
    frame = bars([row])
    assert gate.passes_geometry(frame, COLS).tolist() == [False]
    failures = gate.geometry_failures(frame, COLS)
    assert bool(failures[flag].iloc[0]), flag


def test_the_four_assertions_are_documented_and_complete():
    assert len(gate.ASSERTIONS) == 4
    failures = gate.geometry_failures(CLEAN, COLS)
    assert list(failures.columns) == [
        "high_lt_low", "high_lt_max_open_close",
        "low_gt_min_open_close", "non_finite_or_non_positive",
    ]


def test_pr8_example_row_is_rejected():
    """REVISION_2 舉的 high 90 / open-close 100 / low 99，必須被擋。"""
    frame = bars([[100.0, 90.0, 99.0, 100.0]])
    assert gate.passes_geometry(frame, COLS).tolist() == [False]


# --- 欄位缺失路徑 -----------------------------------------------------------

@pytest.mark.parametrize("missing", ["open", "max", "min", "close"])
def test_missing_column_is_fail_closed(missing):
    frame = CLEAN.drop(columns=[missing])
    assert gate.passes_geometry(frame, COLS).tolist() == [False] * len(CLEAN)


@pytest.mark.parametrize("bad", [np.nan, None, "", "n/a"])
def test_non_numeric_or_null_value_is_fail_closed(bad):
    frame = bars([[100.0, 103.0, 97.0, 101.0]]).astype(object)
    frame.loc[0, "max"] = bad
    assert gate.passes_geometry(frame, COLS).tolist() == [False]


def test_failure_never_borrows_from_a_neighbouring_row():
    """fail-closed：壞列不得被鄰列補成合格，好列也不得被鄰列拖累。"""
    frame = bars([
        [100.0, 103.0, 97.0, 101.0],
        [100.0, 90.0, 99.0, 100.0],
        [100.0, 103.0, 97.0, 101.0],
    ])
    assert gate.passes_geometry(frame, COLS).tolist() == [True, False, True]


# --- valid_ohlc 退化情境：本閘門存在的理由 ---------------------------------

def test_gate_still_rejects_when_valid_ohlc_is_always_true():
    """上游 flag 退化為恆真時，新閘門仍須擋下違反列。"""
    frame = bars([
        [100.0, 103.0, 97.0, 101.0],
        [100.0, 90.0, 99.0, 100.0],
        [100.0, 95.0, 90.0, 100.0],
        [0.0, 103.0, 97.0, 101.0],
    ])
    frame["valid_ohlc"] = True          # 上游說全部合格
    frame["observed_trade"] = True
    # 舊判定（只看上游）會全部放行。
    legacy = frame["observed_trade"] & frame["valid_ohlc"] & frame["close"].gt(0)
    assert legacy.tolist() == [True, True, True, True]
    # 新閘門不受影響。
    assert gate.passes_geometry(frame, COLS).tolist() == [True, False, False, False]
    # 兩者並用才是本輪要的結果。
    assert (legacy & gate.passes_geometry(frame, COLS)).tolist() == [True, False, False, False]


def test_gate_does_not_read_valid_ohlc_at_all():
    """獨立性：新閘門不得引用上游欄位，否則單點沒有變成兩點。"""
    import ast

    source = inspect.getsource(gate)
    tree = ast.parse(source)
    # 把 docstring 與註解剝掉之後，程式碼本體不得出現上游欄位名。
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body.pop(0)
    code = ast.unparse(tree)
    assert "valid_ohlc" not in code
    assert "observed_trade" not in code
    assert "Trading_money" not in code
    # 把欄位整個拿掉，判定結果必須完全一樣。
    with_flag = bars([[100.0, 90.0, 99.0, 100.0], [100.0, 103.0, 97.0, 101.0]])
    with_flag["valid_ohlc"] = [True, False]
    without = with_flag.drop(columns=["valid_ohlc"])
    assert gate.passes_geometry(with_flag, COLS).tolist() == \
           gate.passes_geometry(without, COLS).tolist() == [False, True]


# --- patch 與規格 -----------------------------------------------------------

def test_patch_exists_and_names_both_insertion_points():
    text = PATCH.read_text(encoding="utf-8")
    assert "scripts/astraquant_aq_exp_data_001.py" in text
    # producer 有兩處依賴 valid_ohlc，兩處都要接上閘門。
    assert "def add_universe" in text and "def add_c_states" in text
    assert "current_valid" in text and "valid_close" in text
    assert "_passes_ohlc_geometry" in text


def test_spec_marks_48518_as_conditional():
    text = SPEC.read_text(encoding="utf-8")
    assert "48,518" in text
    window = text[max(0, text.index("48,518") - 400): text.index("48,518") + 400]
    assert "條件式" in window
    assert "非實際受影響列數" in window or "不是實際受影響" in window
    assert "不實際套用" in text
