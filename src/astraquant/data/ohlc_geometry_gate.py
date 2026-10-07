"""AQ-EXP-GEOM-002 — OHLC 幾何閘門的參考實作。

目的只有一個：把「bar 幾何是否可信」這條防線從**一個點**變成**兩個點**。

目前 producer 的有效性判定完全依賴上游的 `tradability.valid_ohlc`：

    current_valid = observed_trade & valid_ohlc & close > 0 & Trading_money notna

AQ-EXP-GEOM-001 量到該欄目前擋得乾淨（母體內幾何違反 0 列），但那是**單點**。
本模組提供一條與之獨立的判定，供 producer 與 `valid_ohlc` 並用。

**獨立性是本模組的全部意義。**
`passes_geometry()` 只讀 `open` / `high` / `low` / `close` 四欄，
**不讀、不接受、也不得引用 `valid_ohlc`**。若新閘門內部仍引用它，等於沒做。
`tests/test_ohlc_geometry_gate.py` 以測試釘住這一點。

本模組是**參考實作**，與 `docs/AQ_EXP_GEOM_002_GATE_PATCH.diff` 的邏輯一致；
本輪**不實際套用**到 tradestation 的 producer。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# 四條斷言。任一不成立 → 該列判為無效，fail-closed。
ASSERTIONS = (
    "high >= low",
    "high >= max(open, close)",
    "low <= min(open, close)",
    "open/high/low/close are all finite and strictly positive",
)

OHLC_COLUMNS = ("open", "high", "low", "close")

# producer 的台股欄位命名：max 是最高價、min 是最低價。
PRODUCER_COLUMN_MAP = {"open": "open", "high": "max", "low": "min", "close": "close"}


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    """取出一欄並轉成數值。非數值、缺欄、NaN、null 一律成為 NaN。

    缺欄不丟例外而是回傳整欄 NaN，因為 fail-closed 的語意是
    「拿不到就當不成立」，不是「拿不到就中止判定」。
    """
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def geometry_failures(
    frame: pd.DataFrame, columns: dict[str, str] | None = None
) -> pd.DataFrame:
    """逐條回傳每一列是否違反該條斷言（True = 違反）。

    `columns` 把本模組的語意名對應到實際欄名，預設為 producer 的命名
    （`high` → `max`、`low` → `min`）。
    """
    cols = dict(PRODUCER_COLUMN_MAP if columns is None else columns)
    o = _numeric(frame, cols["open"])
    h = _numeric(frame, cols["high"])
    l = _numeric(frame, cols["low"])
    c = _numeric(frame, cols["close"])

    finite_positive = (
        np.isfinite(o) & np.isfinite(h) & np.isfinite(l) & np.isfinite(c)
        & o.gt(0) & h.gt(0) & l.gt(0) & c.gt(0)
    )
    # 缺值會讓比較結果是 NaN；fillna(True) 讓「算不出來」等同「違反」。
    return pd.DataFrame(
        {
            "high_lt_low": h.lt(l).where(finite_positive, True).fillna(True),
            "high_lt_max_open_close": h.lt(np.maximum(o, c)).where(finite_positive, True).fillna(True),
            "low_gt_min_open_close": l.gt(np.minimum(o, c)).where(finite_positive, True).fillna(True),
            "non_finite_or_non_positive": ~finite_positive.fillna(False),
        },
        index=frame.index,
    ).astype(bool)


def passes_geometry(
    frame: pd.DataFrame, columns: dict[str, str] | None = None
) -> pd.Series:
    """True 表示該列的 OHLC 幾何合格。

    fail-closed：任何一條不成立、任何一欄缺失或非數值，一律 False。
    不以推估或鄰列填補，不讀 `valid_ohlc`。
    """
    failures = geometry_failures(frame, columns)
    return ~failures.any(axis=1)


def failure_summary(
    frame: pd.DataFrame, columns: dict[str, str] | None = None
) -> dict[str, int]:
    """各條斷言的違反列數，另附去重後的總數。診斷用，不參與判定。"""
    failures = geometry_failures(frame, columns)
    summary = {name: int(failures[name].sum()) for name in failures.columns}
    summary["any_failure"] = int(failures.any(axis=1).sum())
    return summary
