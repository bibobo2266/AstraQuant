# AQ-EXP-MERGE-PREP-001 — E1 證據線十四個 Draft PR 的合併前準備

task_id: AQ-EXP-MERGE-PREP-001 / revision 4
狀態：本輪**不合併任何 PR**，只做準備。由執行端產出，不自行驗收。

revision 4 的改動：revision 3 是十二個 PR 的版本，`#17`／`#18` 把倖存者線延長為
`#18 → #17 → #16 → #9 → main`，現在是十四個。r3 的 `539 passed` **作廢，合併輪不得套用**。
本版以十四個 PR 的現行 head 重做乾跑，並新增 §2.5 處理 `#18` 帶進來的新交集面。
§1、§2 整段汰換，§3 之後重新驗證後不變。

未改任何 PR 的內容 —— 本輪沒有為了讓乾跑過而動任何一行。
未改 manifest 本體、未改 producer、未改 queue。FORMAL_RESEARCH 維持無條件阻擋。

參考點：`main` = `6b60b05`。main 若再往前走，§2 需重跑確認。

## 1. 依賴圖與建議合併順序

### 1.1 四疊 stack 與現行 head

```
資料／證據線                                 倖存者線
main ← #8   sol4/aq-exp-data-001-r2          main ← #9   claude/aq-exp-survivor-001
       ↑ #10 solc/aq-exp-atr-001                    ↑ #16 solc/aq-exp-survivor-002
       ↑ #11 solc/aq-exp-geom-001                        ↑ #17 solc/aq-exp-survivor-003
       ↑ #13 solc/aq-exp-cal-001                              ↑ #18 solc/aq-exp-survivor-004
            ↑ #14 solc/aq-exp-cal-002
                 ↑ #15 solc/aq-exp-cal-003   runner 線
                                             main ← #4  solb/baseline-60d-simulator-integration
main ← #12  solc/aq-exp-merge-prep-001              ↑ #5  solb/prepared-run-eligibility-evidence
            獨立                                          ↑ #7  solb/baseline-60d-exploration-runner-prep
```

| PR | head（現行） | base |
| --- | --- | --- |
| #4 | `4d69eca9` | `main` |
| #5 | `aee7387a` | `solb/baseline-60d-simulator-integration` |
| #7 | `7bab63fb` | `solb/prepared-run-eligibility-evidence` |
| #8 | `25266f8a` | `main` |
| #9 | `05bfd378` | `main` |
| #10 | `bfbafa31` | `sol4/aq-exp-data-001-r2` |
| #11 | `2ccc65ed` | `sol4/aq-exp-data-001-r2` |
| #12 | `f090d96b` | `main` |
| #13 | `bb2fb943` | `sol4/aq-exp-data-001-r2` |
| #14 | `9f3b5979` | `solc/aq-exp-cal-001` |
| #15 | `773d4709` | `solc/aq-exp-cal-002` |
| #16 | `7e58989d` | `claude/aq-exp-survivor-001` |
| #17 | `ddbe1ae4` | `solc/aq-exp-survivor-002` |
| #18 | `311165ec` | `solc/aq-exp-survivor-003` |

### 1.2 建議順序

四疊各自由深到淺，互不相依：

- **資料線**：`#10 → #11 → #15 → #14 → #13 → #8 → main`
- **倖存者線**：`#18 → #17 → #16 → #9 → main`
- **runner 線**：`#7 → #5 → #4 → main`
- `#12` 獨立

兩個必須先知道的副作用（四疊都適用）：

- **先合深層會把淺層 PR 的 diff 撐大。** 倖存者線尤其明顯：#16／#17／#18 全進 #9 之後，
  #9 的 diff 會從 3 個檔長到 12 個檔，其中包含對 #9 自己交付的
  `docs/SURVIVORSHIP_72_DELISTED.md` 的修改。按下 #9 之前應重讀其最終 diff。
- **不要直接把深層 PR 合進 main。** 它們的 commit 鏈含著上游。

## 2. 衝突清單（以十四個 PR 的現行 head 重做）

全部用 `git merge --no-commit --no-ff` 乾跑後 `git merge --abort`，未推送、未合併。
**沒有為了讓乾跑過而更動任何 PR 的內容。**

### 2.1 兩兩乾跑

| 目標 ← 來源 | 結果 |
| --- | --- |
| `#14` ← #15 ／ `#13` ← #14 ／ `#8` ← #13 | CLEAN ／ CLEAN ／ CLEAN |
| `#8` ← #10 ／ `#8` ← #11 ／ `main` ← #8 | CLEAN ／ CLEAN ／ CLEAN |
| `#17` ← #18 ／ `#16` ← #17 ／ `#9` ← #16 | CLEAN ／ CLEAN ／ CLEAN |
| `main` ← #9 | CLEAN |
| `#5` ← #7 ／ `#4` ← #5 ／ `main` ← #4 | CLEAN ／ CLEAN ／ CLEAN |
| `main` ← #12 | CLEAN |

### 2.2 四疊整串乾跑

- 資料線 `#13 → #14 → #15 → #10 → #11` 疊進 #8：**五步全 CLEAN**
- 倖存者線 `#16 → #17 → #18` 疊進 #9：**三步全 CLEAN**
- runner 線 `#7 → #5 → #4`：**CLEAN**
- 四疊再加 `#12` 全部併進 main：**四步全 CLEAN**

**十四個 PR 併進同一棵樹後，零衝突檔案、零衝突行段。**
該樹上 `pytest -q` = **564 passed, 9 skipped**；帶齊三層輸入跑
`scripts/merge_postcheck.py --strict` = **PASS 48 / FAIL 0 / SKIP 0**。

r3 的 `539 passed` 不含 #17／#18，已作廢。

### 2.3 被多個 PR 同時觸碰的檔案

| 檔案 | PR | 性質 |
| --- | --- | --- |
| `src/astraquant/portfolio/strategy_simulator.py` | #4／#5／#7 | runner stack 內先後修改 |
| `docs/BASELINE_60D_BREAKOUT_READINESS.md` | #4／#7 | 同上 |
| `src/astraquant/research/config_engine.py` | #4／#5 | 同上 |
| `tests/test_baseline_60d_simulator_integration.py` | #4／#5 | 同上 |
| `out/aq_exp_data_001_r2_manifest.json` | #8／#10 | 資料線 stack 內 |
| **`docs/SURVIVORSHIP_72_DELISTED.md`** | **#9／#18** | **倖存者線 stack 內（新）** |
| **`docs/AQ_EXP_SURVIVOR_003_SEQUENCE_END.md`** | **#17／#18** | **倖存者線 stack 內（新）** |

### 2.4 #18 帶進來的新交集面（r3 未涵蓋）

`#18` 動到 `scripts/source_terminal_coverage_audit.py` 與四份 docs，其中兩份與
`#9`／`#17` 的原始交付重疊。逐一確認其性質：

| 檔案 | 誰新增 | 誰修改 | 判定 |
| --- | --- | --- | --- |
| `docs/SURVIVORSHIP_72_DELISTED.md` | #9（add） | #18（mod） | **stack 內順序依賴** |
| `docs/AQ_EXP_SURVIVOR_003_SEQUENCE_END.md` | #17（add） | #18（mod） | **stack 內順序依賴** |
| `docs/SOURCE_TERMINAL_COVERAGE_AUDIT.md` | main 既有 | 僅 #18 | 無交集 |
| `docs/MASTER_PROGRESS.md` | main 既有 | 僅 #18 | 無交集 |
| `scripts/source_terminal_coverage_audit.py` | main 既有 | 僅 #18 | 無交集 |

**判定依據不是「看起來像」，是祖先關係**。用 `git merge-base --is-ancestor` 逐對驗證：

```
#9  是 #18 的祖先 ✓      #17 是 #18 的祖先 ✓      #16 是 #17 的祖先 ✓
#9  是 #16 的祖先 ✓      #8  是 #13/#14/#15 的祖先 ✓
#4  是 #5/#7 的祖先 ✓    #5  是 #7 的祖先 ✓
```

每一組共同檔案的兩個 PR 都在同一條 stack 上、且前者是後者的祖先，
因此 git 看到的是同一條線上的先後兩次修改，**不是兩個分支各改一份**。
四疊之間零交集：`MASTER_PROGRESS.md`、`SOURCE_TERMINAL_COVERAGE_AUDIT.md` 與其產生器
只被 #18 碰，沒有任何其他疊觸及。

唯一會變成真衝突的情境，是合併前又有人往某疊的中間層推新 commit 去改上面那些檔案；
屆時應在該疊內部解、讓下游 rebase，不要在 main 側解。

### 2.5 合併輪三個既有條件在最終樹上的複驗

| 條件 | 複驗結果 |
| --- | --- |
| CAL-003 workflow 形態 | `on.push` 無殘留、sentinel 檔不存在、`workflow_dispatch` 保留、檔頭 72 次對外請求註記在位 |
| 「真缺日 0」的覆蓋範圍 | 合併當時：月份 OK **71**、UNKNOWN `201710`、仍 third-party **3 天**。合併後由 AQ-EXP-CAL-004 補齊為 **72/72、third-party 0 天**，見 §5 第 2 條 |
| 「74 檔」判定窗標註 | 未標註的裸「74 檔」敘述 **0 處**；稽核表 `Terminal window` 欄位 **42 E1_INSIDE / 32 E1_OUTSIDE** |

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

以下沒有一項因為這十四個 PR 合併而完成。不要在合併紀錄裡把它們寫成已完成。

1. **runner 線只有合成 fixture。** #4／#5／#7 的 src 凍結已由 Owner 解除、三個 PR 皆已 ACCEPTED，
   但 runner 至今只跑過 deterministic synthetic fixture，沒有真實 parquet 整合驗收，
   也沒有真實 E1／E2／E3。合併它們不等於 runner 可以跑真實資料。
2. ~~**日曆完整性的「真缺日 0」只覆蓋 71/72 個月。**~~ **已解決（AQ-EXP-CAL-004）。**
   合併當時 `2017-10` 回傳阻擋頁、標 UNKNOWN，三天仍為 third-party，覆蓋 71/72。
   Owner 其後授權單次補取，取數成功：**覆蓋 72/72、104 天全部 authoritative、
   third-party 0 天、真缺日仍為 0、四項交集 428,102 不變**。
   此條保留為更正紀錄，不要刪除——合併紀錄中若引用「71/72」須一併標明已補齊。
3. **E1 倖存者的既有曝光量是以過大母體算出的。** `#17` 確認 E1 內真正有序列終止事件的是
   **42 檔**，不是 74 檔（判定窗 2015–2026）。既有的 413 股票日 / 0.089% 以全 74 檔為母體，
   **方向偏保守**，`#18` 已就地加註、數字未重算。合併紀錄不得把 413 / 0.089% 當成 E1 曝光量引用。
4. **producer 仍沒有獨立的幾何閘門。** #11 量到的 0 是上游
   `tradability.valid_ohlc` 一個欄位撐住的，爆炸半徑 48,518 列 / 290 檔。
   建議的兩條解法（producer 加斷言、回歸測試釘住攔截率）只有後者隨 #11 進去，
   前者未執行。
5. **`tradability.valid_ohlc` 本身未獨立稽核。** #11 把它當給定值。
6. **B 依賴曝光與原母體未重跑。** #10 只動 ATR14 的 C／numeric／limited／evidence／reason，
   B 曝光 20,524 與母體 458,315 都是沿用 v1 的值。
7. **21 檔下市事件未查證。** `data/research/terminal_events.csv` 仍待補，
   PR #9 只做到接觸面清點，沒有做事件歸類。
8. **PR #9 §7 的縮減比例仍用 lifetime 口徑**（54%，8,465/15,797）。
   主口徑已改為 60 日窗，同一比較在 60 日窗下是 410/413 ≈ 99.3%。
   這不影響 §7 的建議方向（只查 21 檔），反而更支持它，但兩個口徑並存在同一份文件裡。
   PR #9 已用完兩輪修改額度，列為已知限制。
9. **A2 的 manifest 註記未執行**（見 §3.3），若要做需另開 PR。
10. **沒有任何策略效果數字。** FORMAL_RESEARCH 全程無條件阻擋，這十四個 PR 全是
   資料可算性的 membership accounting，不含勝率、賠率、期望值或任何報酬口徑。

## 6. 本輪沒有做的事

- 沒有合併任何 PR，沒有推送任何既有分支
- 沒有修改任何既有交付的內容，沒有改 manifest 本體
- 沒有改 producer、queue、workflow
- 沒有碰凍結的 solb 分支與那兩個 src 檔
- 乾跑合併全部在本機進行並已 abort，遠端狀態未變
