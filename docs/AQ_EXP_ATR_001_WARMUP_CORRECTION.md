# AQ-EXP-ATR-001 — ATR14 暖機差異的實際受影響筆數

task_id: AQ-EXP-ATR-001 / revision 1
狀態：實際數字已算出並通過重建核對；本文件由執行端產出，**不自行驗收**。

本輪只做資料可算性的 membership accounting，不執行策略觸發、不計算任何報酬，
FORMAL_RESEARCH 維持無條件阻擋，未讀 E2/E3、未掃參數、未改 CA accounting／normalizer／queue／workflow。

## 1. 結論

`docs/AQ_EXP_DATA_001_REVISION_2.md` 第 2 節把這個數字記為
「UNKNOWN，範圍 0～399」。實際數字是 **17**，不是上界、不是範圍。

| | 值 |
| --- | --- |
| 實際受影響股票日 | **17** |
| 涉及檔數 | 17（每檔各一天） |
| 年度分佈 | 2016：6、2017：1、2018：2、2019：0、2020：1、2021：7 |
| 原 ATR14 C 總數 | 399（修正後剩 382） |
| 四項交集增量 | **0**（與 PR #8 的論證一致） |

上界之所以是 399 而實際只有 17，原因在 C rows 的 `valid_bar_ordinal` 分佈：
399 筆裡只有 17 筆剛好落在第 14 根有效 bar，其餘 382 筆的有效 bar 數在 1～13，
改成 14 根門檻後依然不足。

| valid_bar_ordinal | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ATR14 C rows | 57 | 45 | 35 | 32 | 31 | 25 | 24 | 24 | 27 | 24 | 21 | 19 | 18 | **17** |

那 17 筆的當日 `valid_observed_bar` 全為 True，所以正式契約在當日確實會接受該 bar
並給出 ATR14；沒有「ordinal 夠但當日 bar 被正式拒絕」的情形需要再扣除。

## 2. 缺陷與判定依據

private producer 要 15 根有效 bar 才給 ATR14
（`atr14_c_reason = WARMUP_INSUFFICIENT_15_VALID_BARS_FOR_14_TR`）；
正式 `Baseline60DExitState` 第一根 TR = high − low，14 根就夠。
因此只有「第 14 根有效 bar 當天」這一層會翻轉，第 13 根以前兩邊都不給。

篩選條件（依 REVISION_2 第 5 節第 2 點）：

```
atr14_issue_c AND valid_bar_ordinal == 14 AND valid_observed_bar == True
```

## 3. 重建與核對

v1 的逐列 parquet 本身不保留 `valid_bar_ordinal` / `valid_observed_bar`，
因此由固定 revision 的 producer 函式（`load_panel` → `add_universe` → `add_c_states`）
對固定 source checkout 重建，再以 `date/stock_id` 一對一接回凍結交付。

| 核對項 | 重建 | 凍結交付 | 結果 |
| --- | --- | --- | --- |
| 母體股票日 | 458,315 | 458,315 | 一致 |
| 母體檔數 | 1,394 | 1,394 | 一致 |
| ATR14 C rows | 399 | 399 | 布林向量逐列相同 |
| LOW20 C rows | 502 | 502 | 布林向量逐列相同 |
| 接回後 ordinal 缺值 | 0 | — | 無漏接 |

producer 身分亦經核對：git blob `fa6b2729…`、SHA256 `16a953ac…`，
與 `out/aq_exp_data_001_r2_manifest.json` 所載一致；
排除名單 SHA256 `379d58f6…` 亦一致。

## 4. 聚合更新（只動 ATR14）

全期 feature 聚合：

| 欄位 | 修正前 | 修正後 | 差 |
| --- | --- | --- | --- |
| numeric_computable | 457,916 | 457,933 | +17 |
| limited_exploration_eligible | 437,419 | 437,435 | +16 |
| issue_C_days | 399 | 382 | −17 |
| known_affected_days | 410 | 393 | −17 |
| indeterminate_days | 457,905 | 457,922 | +17 |
| dominant_problem_class = C | 399 | 382 | −17 |
| dominant_problem_class = B | 20,497 | 20,498 | +1 |
| dominant_problem_class = A | 437,419 | 437,435 | +16 |
| issue_B_days | 20,524 | 20,524 | 0 |

limited 只 +16 而非 +17：17 筆裡有 1 筆同時帶 ATR14 的 B 曝光，
`limited = numeric AND NOT b_any`，所以該筆由 C 轉為 B 主導，沒有取得限制性資格。
該筆的 `b_known` 為 False，因此 evidence_state 由 KNOWN_AFFECTED 轉為 INDETERMINATE。

年度分項見 `out/aq_exp_atr_001_warmup_correction.json` 的 `atr14_yearly_aggregate`。

## 5. 沒有動到的部分

- **四項交集與 baseline 層聚合完全不變。** 17 筆在第 14 根有效 bar 時
  `low20_issue_c` 仍全為 True（LOW20 需要 21 根），因此
  `baseline_all_four_numeric_computable` 維持 428,102，
  `baseline_issue_c_any`、`baseline_limited_exploration_eligible`、
  `baseline_evidence_state` 與年度表皆未變動。這與 PR #8 的論證相符。
- B 依賴曝光未重跑；原母體未重算；`original_row_count` 維持 458,315。
- A（RAW 歷史版本識別）仍適用於全部列，沒有任何列被升級為 VERIFIED。
- bar 幾何（positive OHLC 被當 valid）與共同日曆完整性兩項缺陷未處理，
  本文件不替它們背書。真實受影響數若把那兩項一起修，會與 17 不同。

## 6. 可重現

公開環境（只驗聚合檔自洽與合成契約）：

```bash
python -m pytest tests/test_aq_exp_atr_001.py -q
```

可讀私有逐列與 source 者，額外跑真實核對（否則該項明示 skip，不偽裝已執行）：

```bash
AQ_COVERAGE_ROWS=/path/to/aq_exp_data_001_eligibility_reason_rows.parquet \
AQ_SOURCE_ROOT=/path/to/minervini_picks/data \
AQ_PRODUCER=/path/to/scripts/astraquant_aq_exp_data_001.py \
  python -m pytest tests/test_aq_exp_atr_001.py -q
```

私有逐列內容未複製進本 repo，本文件與 JSON 只保留聚合。
