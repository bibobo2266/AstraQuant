# AQ-EXP-GEOM-002 — producer 的獨立幾何閘門（規格 + 測試 + patch）

task_id: AQ-EXP-GEOM-002 / revision 1
狀態：規格、參考實作、測試、patch 已交付。**patch 本輪不實際套用。**
本文件由執行端產出，不自行驗收。

**量尺**：資料層防線。不報勝率／賠率／每筆期望值，不得用於論斷任何元件有效或無效。

**main 變乾淨不等於可以開始論斷任何元件有效或無效。**

## 1. 這條閘門要解決什麼

producer 目前的有效性判定有兩處，**兩處都完全依賴上游的 `tradability.valid_ohlc`**：

```python
# add_universe()
current_valid = observed_trade & valid_ohlc & close > 0 & Trading_money notna

# add_c_states()
valid_close   = observed_trade & valid_ohlc & isfinite(close) & close > 0
```

裡面沒有任何一條檢查 `high`／`low`／`open`／`close` 的相對關係。
整條幾何防線掛在**一個欄位**上。

AQ-EXP-GEOM-001 已量到：母體 458,315 列內實際幾何違反 **0 列**，
上游攔截率 100%。所以這不是在修已實現的錯誤，**是把單點防線變成兩點**。

> **48,518 列是條件式的爆炸半徑，不是實際受影響列數。**
> 它的意思是「若 `valid_ohlc` 退化為恆真，會有 48,518 列、290 檔
> 進入候選篩選」。目前實際受影響是 0 列。
> 因此套用本閘門後，**所有既有量化結果應紋風不動**——
> 把「數字改變」當成驗收標準會是錯的標準。

## 2. 四條斷言

| # | 判定式 | 違反時的旗標 |
| --- | --- | --- |
| 1 | `high >= low` | `high_lt_low` |
| 2 | `high >= max(open, close)` | `high_lt_max_open_close` |
| 3 | `low <= min(open, close)` | `low_gt_min_open_close` |
| 4 | `open`／`high`／`low`／`close` 皆為**有限正值** | `non_finite_or_non_positive` |

失敗時的行為，逐條寫死：

- **任一條不成立 → 該列判為無效**，不是警告、不是降級。
- **fail-closed**：不得以推估、鄰列、前後值或任何方式填補。
  壞列不會被鄰列補成合格，好列也不會被鄰列拖累（有測試釘住）。
- **欄位缺失一律視同不成立**：欄位不存在、值為 `NaN`／`null`／非數值字串、
  `±inf`，全部判為不合格。缺欄不丟例外而是整欄視為 `NaN`，
  因為 fail-closed 的語意是「拿不到就當不成立」，不是「拿不到就中止判定」。
- **零振幅 bar 合法**：`high == low == open == close` 是漲跌停鎖死，
  不是幾何違反，必須放行。

## 3. 獨立性（本輪的全部意義）

**新閘門不得讀取或依賴 `valid_ohlc`。**

若閘門內部仍引用上游欄位，那麼上游退化時閘門也跟著退化，
單點還是單點，這一輪就白做了。

實作上的保證：

- `passes_geometry()` 只讀 `open`／`high`／`low`／`close` 四欄。
- 原始碼中**不出現** `valid_ohlc`、`observed_trade`、`Trading_money`
  （docstring 說明為何不依賴者除外）。
- 把 `valid_ohlc` 欄整個從輸入拿掉，判定結果必須逐列相同。

以上三點都有測試斷言，見 §5。

## 4. 參考實作與 patch

| 交付物 | 位置 | 性質 |
| --- | --- | --- |
| 參考實作 | `src/astraquant/data/ohlc_geometry_gate.py` | 可執行、可測試，與 patch 邏輯一致 |
| patch | `docs/AQ_EXP_GEOM_002_GATE_PATCH.diff` | 可直接套用到 tradestation 的 producer |
| 測試 | `tests/test_ohlc_geometry_gate.py` | 10 項、16 個案例 |

**patch 的套用位置**（目標 `bibobo2266/tradestation` 的
`scripts/astraquant_aq_exp_data_001.py`，基準 revision `20162dc7`、
blob `fa6b2729`、sha256 `16a953ac`）：

1. **模組層**：新增 `_passes_ohlc_geometry()`，放在 `def load_panel` 之前。
2. **`add_universe()` 的 `current_valid`**（原始第 119–124 行）：
   在 `& x["valid_ohlc"]` 之後插入 `& _passes_ohlc_geometry(x)`。
3. **`add_c_states()` 的 `valid_close`**（原始第 141–146 行）：同樣插入一行。

**兩個判定都要接。** 只改 `add_universe` 會讓 `add_c_states` 留下另一個單點，
而後者正是 `valid_bar_ordinal` 與四個 feature 的 C 判定所依賴的那一條。

patch 只做加法——在既有的 `&` 鏈上多串一個條件，沒有刪除或改寫任何既有判定，
所以 `valid_ohlc` 仍然有效，兩條防線並用。

## 5. 測試涵蓋

`tests/test_ohlc_geometry_gate.py`，**10 項全過**。

| 路徑 | 測試 |
| --- | --- |
| 乾淨路徑 | `test_clean_path_passes_every_row_unchanged` —— 全部放行，且閘門不改動輸入 |
| 零振幅 bar | `test_zero_range_bar_is_legal` |
| 四條斷言 | `test_each_assertion_catches_its_own_violation`，6 個參數化案例逐條命中對應旗標 |
| PR #8 的例子 | `test_pr8_example_row_is_rejected` —— `high 90 / open-close 100 / low 99` |
| 欄位缺失 | `test_missing_column_is_fail_closed`（四欄各一）、`test_non_numeric_or_null_value_is_fail_closed`（`NaN`／`None`／空字串／非數字字串） |
| 不向鄰列借值 | `test_failure_never_borrows_from_a_neighbouring_row` |
| **`valid_ohlc` 退化情境** | `test_gate_still_rejects_when_valid_ohlc_is_always_true` |
| **獨立性** | `test_gate_does_not_read_valid_ohlc_at_all` |
| patch 可套用性 | `test_patch_exists_and_names_both_insertion_points` |
| 48,518 的標註 | `test_spec_marks_48518_as_conditional` |

退化情境那一支是本閘門存在的理由，所以寫得具體：
把 `valid_ohlc` 設為恆真，先確認**舊判定會把四列全部放行**，
再確認新閘門擋下其中三列，最後確認兩者並用的結果正是想要的。

獨立性那一支做兩件事：掃原始碼確認不出現上游欄位名，
並把 `valid_ohlc` 欄整個拿掉驗證結果逐列相同。

## 6. 既有量化結果：完全未變動

本輪只新增三個檔案（參考實作、測試、patch），**沒有修改任何既有檔案**。
比照 SURVIVOR-004 的做法逐檔比對數字：

**消失的數字：無。**

母體 458,315 / 1,394 檔、四項交集 428,102、ATR14 的 17、幾何的 0、
日曆的 0、倖存者的 410 / 413 / 0.089%，全部未被觸及。
`merge_postcheck.py --strict` 維持 **48 PASS / 0 FAIL / 0 SKIP**。

這正是預期結果：閘門還沒套進 producer，而就算套了，依 §1 的理由也不該改變任何數字。

## 7. 這輪缺什麼

- **patch 沒有套用，producer 目前仍是單點防線。** 套用屬另一輪。
  Owner 已開放 tradestation 的寫入權限，但本輪驗收標準第 4 條明寫
  「不實際套用」，所以本輪不動。
- **沒有在真實資料上跑過套用後的 producer。** §4 列的四步驗證屬另一輪。
- **`tradability.valid_ohlc` 本身仍未獨立稽核。** 本閘門讓它不再是唯一防線，
  但沒有回答「它自己對不對」。
- **真實資料接上後會先動的數字**：套用本閘門後預期四項交集 428,102 不動。
  若哪天動了，先動的會是
  `INPUT_MISSING_OR_SUSPENDED_IN_120_COMMON_ROWS`（目前 28,451），
  再連動四項交集 —— 而那會表示上游 flag 與幾何判定開始不一致，是警訊不是進展。
