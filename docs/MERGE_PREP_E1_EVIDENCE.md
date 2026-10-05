# AQ-EXP-MERGE-PREP-001 — E1 證據線四個 Draft PR 的合併前準備

task_id: AQ-EXP-MERGE-PREP-001 / revision 1
狀態：本輪**不合併任何 PR**，只做準備。由執行端產出，不自行驗收。

本輪未改任何既有交付的內容、未改 manifest 本體、未改 producer、未改 queue、未改 workflow。
FORMAL_RESEARCH 維持無條件阻擋。私有逐列內容未進 repo。

依全域凍結令：本文件與 `scripts/merge_postcheck.py` 均未碰
`solb/baseline-60d-exploration-runner-prep`、`src/astraquant/portfolio/strategy_simulator.py`、
`src/astraquant/research/baseline_60d_exploration.py`。
四個待合併 PR 也都沒有觸碰那兩個檔案（逐檔核對過，見 §1 表格）。

本文件撰寫時的參考點：`main` = `f783976320244ae6032ced8bbe80bcbf340d21fb`。
main 若往前走，§2 的乾跑結論需重跑確認。

## 1. 依賴圖與建議合併順序

### 1.1 四個 PR 的實際關係

| PR | head | base | 落後 main | 自身 commit | 改動檔案 |
| --- | --- | --- | --- | --- | --- |
| #8 | `25266f8a` | `main` | 5 | 1 | `docs/AQ_EXP_DATA_001_E1_COVERAGE.md`(M)、`docs/AQ_EXP_DATA_001_REVISION_2.md`(A)、`docs/OWNER_PRIORITY_QUEUE.md`(M)、`out/aq_exp_data_001_r2_manifest.json`(A)、`src/astraquant/research/exploration_data_contract.py`(A)、`tests/test_aq_exp_data_001_r2.py`(A) |
| #9 | `05bfd378` | `main` | 1 | 10 | `docs/SURVIVORSHIP_72_DELISTED.md`(A)、`out/survivorship_e1_universe_contact.json`(A)、`scripts/survivorship_72_scan.py`(A) |
| #10 | `bfbafa31` | `sol4/aq-exp-data-001-r2` | — | 2 | `docs/AQ_EXP_ATR_001_WARMUP_CORRECTION.md`(A)、`out/aq_exp_atr_001_warmup_correction.json`(A)、`out/aq_exp_data_001_r2_manifest.json`(**M**)、`tests/test_aq_exp_atr_001.py`(A) |
| #11 | `2ccc65ed` | `sol4/aq-exp-data-001-r2` | — | 2 | `docs/AQ_EXP_GEOM_001_OHLC_GEOMETRY.md`(A)、`out/aq_exp_geom_001_ohlc_geometry.json`(A)、`tests/test_aq_exp_geom_001.py`(A) |

依賴形狀：

```
main
 ├── #8  (sol4/aq-exp-data-001-r2)
 │     ├── #10 (solc/aq-exp-atr-001)   ← 修改 #8 新增的 manifest
 │     └── #11 (solc/aq-exp-geom-001)  ← 讀 #8 的 manifest，不改
 └── #9  (claude/aq-exp-survivor-001)  ← 與上面三個完全獨立
```

#10 與 #11 的 merge-base 就是 #8 的 head，**不是**平行分支。
#11 不改 manifest，但它的測試會讀 manifest 的 `producer.*` 與 `fixed_inputs.*` 欄位做身分核對，
所以它仍依賴 #8 先進去。

### 1.2 建議順序（只按兩次 main）

1. **#10 → `sol4/aq-exp-data-001-r2`**（base 已正確，乾跑 CLEAN）
2. **#11 → `sol4/aq-exp-data-001-r2`**（乾跑 CLEAN）
3. **#8 → `main`**：此時 sol4 已含 #10 與 #11，一次帶進去
4. **#9 → `main`**（乾跑 CLEAN，與前三者零交集）

這個順序的好處是 manifest 只在 sol4 線內被動一次，main 上看不到任何中間態。

兩個必須先知道的副作用：

- **第 1、2 步會把 PR #8 的 diff 撐大。** 合併 #10、#11 之後，#8 的 diff 從 6 個檔變成 12 個檔。
  Owner 在第 3 步按下去之前應該**重讀一次 #8 的最終 diff**，不要照著舊的審查印象按。
- **不要直接把 #10 或 #11 合進 main。** 它們的 commit 鏈裡含著 #8，直接合會把 #8
  連帶拖進 main，而且 #8 的審查狀態會被跳過。若 Owner 想先放 #8 進 main，
  那就必須把 #10、#11 的 base 改指到 main，順序與結果等價但多兩個動作。

### 1.3 另一種順序（若 Owner 想先讓 main 拿到 #8）

`#8 → main` → 把 #10、#11 的 base 改為 `main` → `#10 → main` → `#11 → main` → `#9 → main`。
乾跑同樣 CLEAN。代價是 main 上會短暫出現「manifest 的 `real_feature_delta` 尚未填入」的中間態，
期間若有人跑 `scripts/merge_postcheck.py --strict` 會 FAIL。不建議，但不是錯的。

## 2. 衝突清單（本機乾跑，未推、未合併）

全部用 `git merge --no-commit --no-ff` 乾跑後 `git merge --abort`，沒有任何推送。

### 2.1 兩兩乾跑

| 目標 ← 來源 | 結果 |
| --- | --- |
| `main` ← #8 | CLEAN |
| `main` ← #9 | CLEAN |
| `sol4`(#8) ← #10 | CLEAN |
| `sol4`(#8) ← #11 | CLEAN |

### 2.2 依建議順序整串乾跑

`main` ← #8 ← #10 ← #11 ← #9：**四步全部 CLEAN，零衝突檔案、零衝突行段。**

### 2.3 被多個 PR 同時觸碰的檔案

**只有一個**：`out/aq_exp_data_001_r2_manifest.json`，由 #8 新增、由 #10 修改。

這不是衝突，是**順序依賴**。#10 的 merge-base 正是 #8 的 head `25266f8a`，
所以 git 看到的是同一條線上的先後兩次修改，不是兩個分支各改一份。
#10 對該檔的改動只有 6 行增、3 行減，全部落在
`findings.atr14_min_bars` 這一個物件裡（新增 `real_feature_delta: 17`、
`real_feature_delta_status`、`real_feature_delta_source`、`real_feature_delta_note`，
並把 `findings.real_counts_recomputed` 改為 `"ATR14_WARMUP_ONLY"`），
沒有碰 `denominator`、`producer`、`fixed_inputs`、`evidence`、`limitations` 任何一欄。

**唯一會變成真衝突的情境**：若在合併前又有人往 `sol4/aq-exp-data-001-r2`
推新 commit 去改 `findings` 區塊。目前沒有，但 #8 若要再補審查意見就會發生。
屆時的解法是在 sol4 上直接改、讓 #10 rebase，不要在 main 側解。

其餘 10 個檔案各自只被一個 PR 觸碰，沒有重疊。

### 2.4 與凍結路徑的交集

四個 PR 沒有任何一個觸碰 `src/astraquant/portfolio/strategy_simulator.py` 或
`src/astraquant/research/baseline_60d_exploration.py`。
#8 新增的 `src/astraquant/research/exploration_data_contract.py` 是另一個檔，不在凍結清單內。
合併這四個 PR **不會**與 PR #7 的 src 改動相撞——但也**不會**解除那條線的阻塞，見 §5。

## 3. period_end 定稿方案（只提方案，本輪不執行）

### 3.1 事實

- `out/aq_exp_data_001_r2_manifest.json` 的 `denominator.period_end` = `2021-12-31`
- 凍結母體實際最後一列 = `2021-12-30`
- 差一日的原因：2021-12-31 當日沒有通過門檻的列，不是資料缺漏

### 3.2 影響面實測

`2021-12-31` 不是 manifest 的筆誤，而是 **E1 epoch 的定義值**，散佈在：

- `docs/` 19 個檔案
- `out/` 8 個 artifact
- 測試至少 4 處，含 `tests/test_epoch_governance.py`（兩處直接寫
  `period_end=date(2021, 12, 31)`）、`tests/test_causal_raw_v2_integration.py`、
  `tests/test_contact_registry.py`
- 固定於 commit `8226478d` 的私有交付 summary 本身也帶 `2021-12-31`，**而且改不了**

### 3.3 方案 A（建議）：保留 manifest，用註記說明差異

manifest 宣告的是 **epoch 邊界**，`2021-12-30` 是**對資料的觀察**。兩者語意不同，
不是同一個欄位的兩個候選值，所以不該用「改掉其中一個」來處理。

A 又分兩段，建議先做 A1、A2 視需要再說：

- **A1（零成本，合併後即成立）**：PR #9 的 `docs/SURVIVORSHIP_72_DELISTED.md` §3 已明寫差異，
  `out/survivorship_e1_universe_contact.json` 也同時輸出 `manifest_period_end` 與
  `e1_end_observed` 兩個欄位。`scripts/merge_postcheck.py` 的 L1 層把這兩個值都釘住。
  **合併 #9 之後這件事就已經有文字與機器兩層紀錄，不需要再動任何檔案。**
- **A2（可選，需另開 PR）**：在 manifest 的 `denominator` 裡增加一個純描述性欄位，
  例如 `last_observed_row_date: "2021-12-30"` 與一行 note。這是新增欄位、不改既有值，
  不影響任何現有斷言。但它會動到一份已被 #8 審查過的檔案，所以必須獨立成 PR 走審查，
  不要塞進這次合併。

### 3.4 方案 B（不建議）：把 manifest 改成 2021-12-30

需要同時處理的事：

1. `tests/test_epoch_governance.py` 的兩處硬編碼要改，等於動到 epoch 治理層
2. 19 個 docs 與 8 個 out artifact 的 E1 期間敘述會與 manifest 不一致
3. 固定於 `8226478d` 的私有交付無法修改，manifest 會與它所描述的那份交付對不上
4. `docs/CONTACT_REGISTRY.md` 等既有登錄的覆蓋期間要連帶重登

成本遠大於收益，而且它解決的是一個不存在的問題——manifest 沒有寫錯，
只是沒有同時記錄「觀察到的最後一列」。**建議不要採用。**

### 3.5 對已凍結交付與既有測試的影響彙總

| 方案 | 改既有值 | 動測試 | 與 `8226478d` 一致 | 合併這四個 PR 需要先做 |
| --- | --- | --- | --- | --- |
| A1 | 否 | 否 | 是 | 否（合併 #9 即生效） |
| A2 | 否（只新增欄位） | 否 | 是 | 否（可事後另開 PR） |
| B | 是 | 是，含 epoch 治理 | **否** | 是，且會擋住合併 |

## 4. 合併後必須仍為真的斷言

寫成可執行腳本：`scripts/merge_postcheck.py`。三層，缺輸入的層一律 SKIP 並寫明缺什麼，
不會把 SKIP 當成通過；有任何 FAIL 時回傳碼 1。

```bash
# 公開環境（無私有資料）
python3 scripts/merge_postcheck.py

# 合併完成後，Owner 的完整驗證
AQ_COVERAGE_ROWS=/path/aq_exp_data_001_eligibility_reason_rows.parquet \
AQ_SOURCE_ROOT=/path/minervini_picks/data \
AQ_PRODUCER=/path/scripts/astraquant_aq_exp_data_001.py \
  python3 scripts/merge_postcheck.py --strict
```

釘住的數字：

| 數字 | 意義 | 驗在哪一層 |
| --- | --- | --- |
| 458,315 | 原母體股票日 | L1 manifest / 三份 artifact 交叉、L2 逐列、L3 重建 |
| 1,394 | 原母體檔數 | L1、L2、L3 |
| 428,102 | 四項交集 numeric_computable | L1 三處、L2、L3（ATR 修正後仍須相同） |
| 399 | ATR14 C rows（v1） | L1 兩處交叉、L2 |
| 502 | LOW20 C rows（v1） | L1、L2 |
| 17 | ATR14 暖機修正受影響列 | L1 manifest + artifact、L3 重算 |
| 457,933 / 437,435 / 382 | ATR14 修正後 numeric / limited / issue_C | L1、L3 |
| 0 | 幾何違反落在母體內 | L1、L3 |
| 0 | 幾何壞列通過 `valid_ohlc` | L1、L3（這是上游攔截率的回歸閘門） |
| 410 | 倖存者 60 日窗（＝持有期）內股票日 | L1、L3 重跑 scan |
| 2021-12-31 / 2021-12-30 | manifest 宣告值 / 母體實際最後一列，兩者都要在 | L1 |

另外還釘了三條**跨檔一致性**，單看任何一份 artifact 都看不出來的那種：

- 三份 artifact 記錄的母體列數必須是同一個值
- #10 與 #11 各自記錄的「ATR14 v1 issue_C」必須相等（都是 399）
- #11 記錄的 MA120 `numeric_computable` 必須等於四項交集（MA120 是最窄的一項；
  哪天不等就表示 baseline 有問題）

在模擬合併樹（main ← #8 ← #10 ← #11 ← #9）上帶齊三層輸入實跑的結果：
**PASS 48 / FAIL 0 / SKIP 0**。在尚未合併的 main 上跑則是 SKIP 6、回傳碼 0，
加 `--strict` 會轉成 FAIL——這是刻意的，合併後若有人漏了某個 artifact 會被抓出來。

## 5. 合併後**仍未**解決的事項

以下沒有一項因為這四個 PR 合併而完成。不要在合併紀錄裡把它們寫成已完成。

1. **PR #7 / `solb` 的 src 凍結未解除。** `src/astraquant/portfolio/strategy_simulator.py`
   與 `src/astraquant/research/baseline_60d_exploration.py` 仍在凍結狀態，
   exploration runner 那條線整條停著。這四個 PR 不碰那兩個檔，所以合併它們
   **既不會解除也不會惡化**，但也不要誤以為合併之後路就通了。等 Owner 裁定。
2. **共同日曆完整性缺陷未量化。** `REVISION_2` 列出的三項缺陷裡，ATR14 暖機門檻
   由 #10 算成 17、OHLC 幾何由 #11 算成 0，**日曆完整性那一項到現在還是 UNKNOWN**。
3. **producer 仍沒有獨立的幾何閘門。** #11 量到的 0 是上游
   `tradability.valid_ohlc` 一個欄位撐住的，爆炸半徑 48,518 列 / 290 檔。
   建議的兩條解法（producer 加斷言、回歸測試釘住攔截率）只有後者隨 #11 進去，
   前者未執行。
4. **`tradability.valid_ohlc` 本身未獨立稽核。** #11 把它當給定值。
5. **B 依賴曝光與原母體未重跑。** #10 只動 ATR14 的 C／numeric／limited／evidence／reason，
   B 曝光 20,524 與母體 458,315 都是沿用 v1 的值。
6. **21 檔下市事件未查證。** `data/research/terminal_events.csv` 仍待補，
   PR #9 只做到接觸面清點，沒有做事件歸類。
7. **PR #9 §7 的縮減比例仍用 lifetime 口徑**（54%，8,465/15,797）。
   主口徑已改為 60 日窗，同一比較在 60 日窗下是 410/413 ≈ 99.3%。
   這不影響 §7 的建議方向（只查 21 檔），反而更支持它，但兩個口徑並存在同一份文件裡。
   PR #9 已用完兩輪修改額度，列為已知限制。
8. **A2 的 manifest 註記未執行**（見 §3.3），若要做需另開 PR。
9. **沒有任何策略效果數字。** FORMAL_RESEARCH 全程無條件阻擋，這四個 PR 全是
   資料可算性的 membership accounting，不含勝率、賠率、期望值或任何報酬口徑。

## 6. 本輪沒有做的事

- 沒有合併任何 PR，沒有推送任何既有分支
- 沒有修改任何既有交付的內容，沒有改 manifest 本體
- 沒有改 producer、queue、workflow
- 沒有碰凍結的 solb 分支與那兩個 src 檔
- 乾跑合併全部在本機進行並已 abort，遠端狀態未變
