# AQ-EXP-GEOM-003 — 幾何閘門套進 producer：狀態紀錄

資料層防線。**不報勝率／賠率／每筆期望值，不得用於論斷任何元件有效或無效。**

## 做了什麼
`bibobo2266/tradestation` PR #1（`solc/aq-exp-geom-003`，head `f62fdca`）把 AQ-EXP-GEOM-002 的閘門套進
`scripts/astraquant_aq_exp_data_001.py`（基準 blob `fa6b2729`），三個插入點全接：

| # | 位置 | 行 |
|---|---|---|
| 1 | 模組層 `_passes_ohlc_geometry()` | 78 |
| 2 | `add_universe()` 的 `current_valid` | 158 |
| 3 | `add_c_states()` 的 `valid_close` | 181 |

diff 37 行新增、0 行刪除；tradestation 側同 PR 新增 25 支測試。原 patch 檔 hunk 行數標頭有誤（`git apply` 拒收），
以內容比對手動插入。

## AstraQuant 側既有量化結果
本 repo **零個既有檔案被修改**（本 PR 只新增本文件）；tradestation PR #1 對 `private/` 下所有輸出檔的改動為 0。
**消失的數字：無。**

以 `merge_postcheck.py --strict` 對 tradestation 現存私有逐列 parquet（`AQ_COVERAGE_ROWS`）核對：
**35 PASS / 0 FAIL / 1 SKIP**（L1 30、L2 5）。母體 458,315 列／1,394 檔、四項交集 428,102、
ATR14 C 399→382（受影響 17）、幾何違反 0、倖存者 410 全部與契約一致。

## 未能由執行端完成的部分（卡住項）
**L3「來源重建核對」為 SKIP**：需要私有 `minervini_picks` 來源與 producer 重跑，執行端的 token 範圍
（AstraQuant／tradestation 的 Contents＋Pull requests）涵蓋不到；producer workflow 只在 push 到 main 時觸發，
執行端無 Actions 權限。因此「套用後 panel 重建出的數字仍不變」**在合併前沒有實測**，這份紀錄只證明：
patch 的靜態內容與既有輸出皆未動、閘門行為由 25 支測試釘住。

**決定性的檢查在合併後**：workflow 會自動重跑並覆蓋
`private/astraquant/aq_exp_data_001_e1_coverage_v1/`；若輸出相同，會印 `No private coverage changes.` 且不產生 commit。
若產生了 `audit: persist AQ-EXP-DATA-001 private coverage` commit，即代表數字變了——依 GEOM-002 規格
「須先停下查明，不得自行調整」。屆時 AstraQuant 側以 `AQ_COVERAGE_ROWS` 指向新 parquet 重跑
`merge_postcheck.py --strict`（含 L3）即可定案。

## tradestation 既有測試
逐 candidate 目錄跑（pinned numpy 2.3.5／pandas 2.2.3），本 PR 前後相同：185 passed／3 failed。
3 個失敗為 `candidates/settlement_clock_v2` 的 `test_postponement_*`，在 main 上就存在
（`ClockBlocked: trade session absent or not yet known`），與 producer 無關，未更動。
